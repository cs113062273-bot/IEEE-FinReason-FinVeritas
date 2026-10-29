"""Typed rendering and conservative surface matching for trained programs.

The sidecar contains input/output contracts from public training QUESTIONS,
never labels or numeric answers. Programs still come from the active registry.
No reordering or word substitution is used to guess a parameter's role.
"""
from __future__ import annotations
import copy,hashlib,json,re
from fractions import Fraction
from pathlib import Path
from src.common.arithmetic import format_value,execute,exact_text
from src.common.fraction_budget import binary
from src.task1.hidden_program import execute as independent_execute
from src.task1.program_reexecution import parse_number

NUMBER=re.compile(r'(?<![\w.])[-+−]?\d+(?:,\d{3})*(?:\.\d+)?(?:[eE][-+]?\d{1,3})?(?:/\d+)?(?!\w|\.\d|,\d)')
SIDECAR=Path(__file__).resolve().parents[2]/'data/processed/task1_registry_contracts.json'

def surface(text):
    return re.sub(r'\s+',' ',text.translate(str.maketrans({'−':'-','’':"'",'‘':"'",'“':'"','”':'"'}))).strip().casefold()

def bind_surface(question):
    body=question.split('\n\nAnswer format:')[0]
    bindings=[]
    for m in NUMBER.finditer(body):
        raw=m[0];value=parse_number(raw.replace(',','').replace('−','-'))
        bindings.append({'name':'x'+str(len(bindings)),'text':raw,'start':m.start(),'end':m.end(),'value':value})
    return surface(NUMBER.sub('#',body)),bindings

# Only representation changes with an explicit, shared meaning are convertible.
UNITS={'usd':('money',Fraction(1)),'usd_million':('money',Fraction(10**6)),
       'usd_thousand':('money',Fraction(10**3)),'usd_billion':('money',Fraction(10**9)),
       'ratio':('rate',Fraction(1)),'percent':('rate',Fraction(1,100)),
       'basis_point':('rate',Fraction(1,10000))}

def conversion(source,target):
    if source['type']!=target['type']:raise ValueError('result type changed')
    if source['type']=='enum':
        if set(source['allowed_values'])!=set(target['allowed_values']):raise ValueError('enum domain changed')
        return Fraction(1)
    a,b=source['unit'],target['unit']
    if a==b:return Fraction(1)
    if a not in UNITS or b not in UNITS or UNITS[a][0]!=UNITS[b][0]:raise ValueError('incompatible result units')
    return UNITS[a][1]/UNITS[b][1]

def slot_mapping(reference,requested):
    mapping={};used=set()
    for slot in requested:
        candidates=[]
        for source in reference:
            if source['slot_id'] in used or surface(source['description'])!=surface(slot['description']):continue
            try:factor=conversion(source['result_spec'],slot['result_spec'])
            except ValueError:continue
            candidates.append((source['slot_id'],factor))
        if len(candidates)!=1:raise ValueError('checkpoint meaning is missing or ambiguous')
        sid,factor=candidates[0];used.add(sid);mapping[slot['slot_id']]=(sid,factor)
    return mapping

class Contracts:
    def __init__(self,registry,path=SIDECAR):
        self.entries={};self.ambiguous=set();self.sha256=None
        if not path.exists():return
        raw=path.read_bytes();self.sha256=hashlib.sha256(raw).hexdigest();data=json.loads(raw)
        for signature,contract in data['contracts'].items():
            if signature not in registry:continue
            key=surface(signature)
            if key in self.entries and self.entries[key][0]!=signature:self.ambiguous.add(key)
            else:self.entries[key]=(signature,contract)

    def match(self,question,registry):
        key,bindings=bind_surface(question['question'])
        if key in self.ambiguous or key not in self.entries:return None
        signature,contract=self.entries[key];program=registry[signature]
        if len(bindings)!=program['numeric_bindings']:return None
        factor=conversion(contract['answer_spec'],question['answer_spec'])
        slots=slot_mapping(contract['trace_spec']['slots'],question['trace_spec']['slots'])
        return signature,bindings,contract,factor,slots

    def solve(self,question,registry,*,use_reviewed=True):
        try:matched=self.match(question,registry)
        except (ValueError,KeyError,TypeError,ZeroDivisionError,OverflowError):return None
        if matched is None:return None
        signature,bindings,contract,factor,slots=matched;program=registry[signature]
        if use_reviewed:
            from src.task1.formulas import reviewed_program
            reviewed=reviewed_program(program['template_id'])
            if reviewed is not None:program={**program,**reviewed}
        values={b['name']:b['value'] for b in bindings};proofs=[]
        def evaluate(expression):
            value=execute(expression,values)
            if independent_execute(expression,values)!=value:raise ValueError('interpreter disagreement')
            return value
        def render(expression,enum,spec,scale):
            if expression:
                value=evaluate(expression)
                if spec['type']=='enum':
                    result='true' if value else 'false'
                    if result not in spec['allowed_values']:raise ValueError('Boolean enum outside domain')
                    return result
                return format_value(binary(value,scale,'*'),spec)
            if enum:
                value=evaluate(enum['expression']);result=enum['labels']['positive' if value>0 else 'negative' if value<0 else 'zero']
                if result not in spec['allowed_values']:raise ValueError('enum outside domain')
                return result
            raise ValueError('missing executable target')
        try:
            for name,expression in program.get('dag',[]):
                values[name]=evaluate(expression);proofs.append({'name':name,'expression':expression,'exact_value':str(values[name])})
            final=render(program.get('final'),program.get('enum'),question['answer_spec'],factor)
            steps=[]
            for slot in question['trace_spec']['slots']:
                sid,scale=slots[slot['slot_id']]
                steps.append({'slot_id':slot['slot_id'],'value':render(program.get('slots',{}).get(sid),program.get('slot_enums',{}).get(sid),slot['result_spec'],scale)})
            prediction={'schema_version':'finreason.task1.prediction/1.0.0','dataset_version':question['dataset_version'],
                        'case_id':question['case_id'],'final_answer':{'value':final},'steps':steps}
            return prediction,{'strategy':'typed_registry_surface','template_id':program['template_id'],'contract_sha256':self.sha256,
                'signature_sha256':hashlib.sha256(signature.encode()).hexdigest(),'final_conversion':str(factor),
                'slot_mapping':{sid:{'source_slot':source,'conversion':str(scale)} for sid,(source,scale) in slots.items()},
                'bindings':[{**b,'value':str(b['value'])} for b in bindings],'intermediates':proofs,
                'arithmetic_verified':True,'matching_policy':'same lexical skeleton, case/whitespace/typography and numeric representation only'}
        except (ValueError,KeyError,TypeError,SyntaxError,ZeroDivisionError,OverflowError):return None

    def solve_canonical(self,question,registry,predictor):
        """Use existing scenario solvers on the exact matched original wording.

        Reconstruct only the numeric bindings; no stored answers or source
        case IDs exist in the contract metadata. Render from unrounded values.
        """
        try:
            matched=self.match(question,registry)
            if matched is None:return None
            signature,bindings,contract,factor,mapping=matched
            parts=signature.split('#')
            if len(parts)!=len(bindings)+1:return None
            body=parts[0]+''.join(exact_text(b['value'])+tail for b,tail in zip(bindings,parts[1:]))
            canonical={**question,**copy.deepcopy(contract),'question':body}
            if canonical['answer_spec']['type']=='decimal':canonical['answer_spec']['rounding']={'mode':'exact'}
            for s in canonical['trace_spec']['slots']:
                if s['result_spec']['type']=='decimal':s['result_spec']['rounding']={'mode':'exact'}
            native,source_audit=predictor(canonical)
            if native['final_answer'] is None:return None
            def render(raw,spec,scale):
                if spec['type']=='enum':
                    if raw not in spec['allowed_values']:raise ValueError('enum domain')
                    return raw
                return format_value(binary(parse_number(raw),scale,'*'),spec)
            values={s['slot_id']:s['value'] for s in native['steps']};steps=[]
            for slot in question['trace_spec']['slots']:
                source,scale=mapping[slot['slot_id']]
                steps.append({'slot_id':slot['slot_id'],'value':render(values[source],slot['result_spec'],scale)})
            prediction={**native,'case_id':question['case_id'],'dataset_version':question['dataset_version'],
                        'final_answer':{'value':render(native['final_answer']['value'],question['answer_spec'],factor)},'steps':steps}
            audit={'strategy':'typed_canonical_scenario','source_strategy':source_audit['strategy'],'template_id':registry[signature]['template_id'],
                   'contract_sha256':self.sha256,'signature_sha256':hashlib.sha256(signature.encode()).hexdigest(),'final_conversion':str(factor),
                   'canonical_question':body,'canonical_exact_prediction':native,
                   'bindings':[{**b,'value':str(b['value'])} for b in bindings],
                   'slot_mapping':{sid:{'source_slot':source,'conversion':str(scale)} for sid,(source,scale) in mapping.items()}}
            return prediction,audit
        except (ValueError,KeyError,IndexError,TypeError,SyntaxError,ZeroDivisionError,OverflowError,RecursionError):return None
