"""Always-answer fallback: local program proposal, then executable retrieval.

Arithmetic checks do not certify semantic correctness. These answers are
explicitly marked estimates in the audit, including the final neutral prior
when there is no usable evidence. No returned prediction uses a null answer.
The local model is optional infrastructure; its failure never suppresses a row.
"""
from __future__ import annotations

import ast
from collections import Counter
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import re
import urllib.request

from src.common.arithmetic import execute, format_value
from src.common.fraction_budget import checked
from src.task1.hidden_program import execute as second_execute
from src.task1.templates import NUMBER
from src.task1.program_reexecution import reexecute,source_number_witnesses,exact_expression,parse_number
from src.task1.proposal_normalization import normalize
from src.task1.program_compiler import compile_program,lower_logic
from src.task1.interval_program import solve as solve_interval

ROOT=Path(__file__).resolve().parents[2]
MODEL_SHA='d98cdcbd03e17ce47681435b5150e34c1417f50b5c0019dd560e4882c5745785'
PROMPT='''Solve the financial question and ALWAYS give your best answer. Never refuse or output null. If ambiguous, choose the most reasonable interpretation and state it in assumption.
Return one JSON object with variables (name -> numeric STRING copied from a stated input), final_expression (arithmetic using variable names), final_answer (numeric STRING in requested output units, or an allowed enum), steps (requested slot_id -> arithmetic expression), and assumption (short string).
Use exact formulas, correct signs, currency magnitudes, percentages/basis points, fiscal periods, and the exact target. Calculate rather than copy a nearby number. No imports, Python code, attributes or file access. Allowed arithmetic: + - * / ** with bounded integer powers, min,max,abs,floor,ceil,geom. All program literals must be integers; use 1/100 for percentages. For a non-rational operation give your numeric final_answer and set final_expression to the empty string. Steps may be expressions or numeric strings in the slot's declared units. Never omit an answer because a rule is unfamiliar. /no_think'''


def _tokens(text):
    return Counter(re.findall(r'[a-z]+',text.lower()))


def _number(value,spec):
    if spec['type']=='enum':
        allowed=spec['allowed_values']
        if str(value) not in allowed:raise ValueError('value outside declared enum')
        return str(value)
    if isinstance(value,str):value=value.strip().replace(',','')
    return format_value(parse_number(value),spec)


def _model(question):
    # Cache keys deliberately omit case identity. No gold or scored manifest.
    public={k:question[k] for k in ('question','answer_spec','trace_spec')}
    key=hashlib.sha256((MODEL_SHA+PROMPT+json.dumps(public,sort_keys=True)).encode()).hexdigest()
    folder=ROOT/'data/processed/task1_best_effort_cache';path=folder/(key+'.json')
    if path.exists():return json.loads(path.read_text(encoding='utf8')),'cache'
    request={'messages':[{'role':'system','content':PROMPT},{'role':'user','content':json.dumps(public)}],
             'temperature':0,'seed':20261024,'max_tokens':768,'stream':False,
             'reasoning_budget_tokens':0,'chat_template_kwargs':{'enable_thinking':False},
             'response_format':{'type':'json_object'}}
    req=urllib.request.Request('http://127.0.0.1:8771/v1/chat/completions',data=json.dumps(request).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=45) as response:result=json.load(response)
    raw=result['choices'][0]['message']['content']
    try:obj=json.loads(raw)
    except (ValueError,TypeError):obj={}
    record={'proposal':obj,'raw_response':result,'model_sha256':MODEL_SHA,'prompt_sha256':hashlib.sha256(PROMPT.encode()).hexdigest()}
    folder.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(record,ensure_ascii=False)+'\n',encoding='utf8')
    return record,'local_model'


def _execute_program(proposal,witnesses,spec):
    """Preserve supported exact programs; extend only failed executions."""
    diagnostics={};candidate=proposal
    failures=(ValueError,TypeError,KeyError,SyntaxError,ArithmeticError,RecursionError)
    def exact(program):
        result=reexecute(program,witnesses)
        details={k:v for k,v in result.items() if k not in {'value','values'}}
        return result['value'],result['values'],program,{**diagnostics,'program_reexecution':details}
    try:return exact(proposal)
    except failures as exc:diagnostics['original_program_error']=type(exc).__name__+': '+str(exc)
    try:
        candidate,compilation=compile_program(proposal);candidate,logic=lower_logic(candidate)
        diagnostics['program_compilation']={**compilation,'numeric_logic':logic}
        return exact(candidate)
    except failures as exc:diagnostics['extended_program_error']=type(exc).__name__+': '+str(exc)
    # Retain the previous interpreter path for an already supported final
    # expression even when an unrelated optional checkpoint is malformed.
    values={name:parse_number(value) for name,value in proposal.get('variables',{}).items()}
    try:
        value=execute(proposal['final_expression'],values)
        if value!=second_execute(proposal['final_expression'],values):raise ValueError('interpreter disagreement')
        return value,values,proposal,diagnostics
    except failures as exc:diagnostics['legacy_program_error']=type(exc).__name__+': '+str(exc)
    rendered,certificate=solve_interval(candidate,witnesses,spec)
    return parse_number(rendered),values,candidate,{**diagnostics,'interval_program':certificate}


class BestEffort:
    def __init__(self,registry,*,use_local_model=True):
        self.registry=registry;self.use_local_model=use_local_model
        self.index=[(signature,program,_tokens(signature)) for signature,program in registry.items()]

    def _retrieve(self,question):
        body=question['question'].split('\n\nAnswer format:')[0]
        bindings=[]
        for m in NUMBER.finditer(body):
            try:bindings.append(checked(Fraction(m[0])))
            except (ValueError,ZeroDivisionError):continue
        query=_tokens(body);norm=math.sqrt(sum(v*v for v in query.values())) or 1
        ranked=[]
        for signature,program,words in self.index:
            denominator=norm*(math.sqrt(sum(v*v for v in words.values())) or 1)
            cosine=sum(v*words.get(w,0) for w,v in query.items())/denominator
            score=cosine/(1+abs(program['numeric_bindings']-len(bindings)))
            ranked.append((score,signature,program))
        for score,signature,program in sorted(ranked,key=lambda x:(-x[0],x[1]))[:32]:
            if program['numeric_bindings']>len(bindings):continue
            values={f'x{i}':value for i,value in enumerate(bindings[:program['numeric_bindings']])}
            try:
                for name,expression in program.get('dag',[]):values[name]=execute(expression,values)
                if program.get('final'):final=execute(program['final'],values)
                elif program.get('enum'):
                    enum=program['enum'];value=execute(enum['expression'],values)
                    final=enum['labels']['positive' if value>0 else 'negative' if value<0 else 'zero']
                else:continue
                rendered=_number(final,question['answer_spec']);steps={}
                for sid,expression in program.get('slots',{}).items():
                    try:steps[sid]=execute(expression,values)
                    except (ValueError,ZeroDivisionError,OverflowError):pass
                return rendered,steps,{'method':'nearest_executable_program','template_id':program['template_id'],
                                      'similarity':score,'signature_sha256':hashlib.sha256(signature.encode()).hexdigest(),
                                      'binding_mode':'approximate numeric order; semantically unverified'}
            except (ValueError,KeyError,TypeError,SyntaxError,ZeroDivisionError,OverflowError):continue
        # A numeric source proxy is an estimate, never a claimed derivation.
        ordinary=[v for v in bindings if not (v.denominator==1 and 1900<=v<=2100)]
        value=question['answer_spec']['allowed_values'][0] if question['answer_spec']['type']=='enum' else ordinary[0] if ordinary else Fraction(0)
        return _number(value,question['answer_spec']),{}, {'method':'source_literal_estimate' if ordinary else 'neutral_prior_no_usable_input','chosen_value':str(value)}

    def predict(self,question):
        from src.task1.financial_graph import solve_financial_graph
        graph=solve_financial_graph(question,allow_unstated_claims=True)
        if graph is not None:return graph
        from src.task1.currency_graph import solve_cross_quote
        cross=solve_cross_quote(question,allow_output_currency_estimate=True)
        if cross is not None:return cross
        # Explicit named relations precede uncertain model proposals. A failed
        # compilation still reaches the complete-answer fallback below.
        from src.task1.prose_program import solve as solve_prose
        prose=solve_prose(question,allow_implicit_target=True)
        if prose is not None:return prose
        final,steps,fallback=self._retrieve(question)
        audit={'strategy':'best_effort_'+fallback['method'],'answer_status':'estimate','semantic_verified':False,
               'retrieval':fallback,'model_used':False};proposal=None
        if self.use_local_model:
            try:
                record,origin=_model(question);proposal=record['proposal'];variables={}
                audit.update(model_used=True,model_origin=origin,model_sha256=MODEL_SHA,proposal=proposal)
                try:
                    proposal,normalization=normalize(proposal,question['answer_spec'])
                    audit['proposal_normalization']=normalization
                    audit['normalized_proposal']=proposal
                except (ValueError,TypeError,KeyError,RecursionError) as exc:
                    audit['normalization_error']=type(exc).__name__+': '+str(exc)
                if not isinstance(proposal,dict) or not isinstance(proposal.get('variables',{}),dict) or not isinstance(proposal.get('steps',{}),dict):
                    raise ValueError('invalid model object structure')
                if len(proposal.get('variables',{}))>64:raise ValueError('too many model variables')
                witnesses=source_number_witnesses(question['question'].split('\n\nAnswer format:')[0])
                source_values=set(witnesses)
                for name,value in proposal.get('variables',{}).items():
                    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*',name):raise ValueError('invalid variable name')
                    number=parse_number(value)
                    if number not in source_values:raise ValueError('program variable not a source number')
                    variables[name]=number
                expression=proposal.get('final_expression','')
                if expression and question['answer_spec']['type']=='decimal':
                    value,variables,proposal,execution=_execute_program(proposal,witnesses,question['answer_spec'])
                    audit.update(execution);audit['compiled_proposal']=proposal
                    final=_number(value,question['answer_spec'])
                    audit['strategy']='best_effort_local_interval_program' if 'interval_program' in audit else 'best_effort_local_program'
                    audit['arithmetic_verified']=True
                else:
                    final=_number(proposal['final_answer'],question['answer_spec']);audit['strategy']='best_effort_local_answer'
                model_steps={}
                for slot in question['trace_spec']['slots']:
                    raw=proposal.get('steps',{}).get(slot['slot_id'])
                    if raw is None:continue
                    try:model_steps[slot['slot_id']]=exact_expression(str(raw),variables)[0] if slot['result_spec']['type']=='decimal' else raw
                    except (ValueError,SyntaxError,ZeroDivisionError):
                        try:
                            step_program={**proposal,'final_expression':str(raw)}
                            model_steps[slot['slot_id']]=_execute_program(step_program,witnesses,slot['result_spec'])[0]
                        except (ValueError,KeyError,TypeError,SyntaxError,ZeroDivisionError,ArithmeticError):
                            try:model_steps[slot['slot_id']]=parse_number(raw)
                            except (ValueError,TypeError,ZeroDivisionError):pass
                steps={**steps,**model_steps}
            except (OSError,ValueError,TypeError,KeyError,SyntaxError,ArithmeticError,RecursionError) as exc:
                audit['model_error']=type(exc).__name__+': '+str(exc)
                # A malformed program can still carry a usable direct answer.
                if isinstance(proposal,dict):
                    try:
                        final=_number(proposal['final_answer'],question['answer_spec']);audit['strategy']='best_effort_local_answer'
                    except (ValueError,KeyError,TypeError,ZeroDivisionError):pass
        rendered=[]
        for slot in question['trace_spec']['slots']:
            sid=slot['slot_id'];value=steps.get(sid,final)
            try:text=_number(value,slot['result_spec'])
            except (ValueError,TypeError,ZeroDivisionError):
                spec=slot['result_spec'];text=spec['allowed_values'][0] if spec['type']=='enum' else _number(0,spec)
            rendered.append({'slot_id':sid,'value':text})
        prediction={'schema_version':'finreason.task1.prediction/1.0.0','dataset_version':question['dataset_version'],
                    'case_id':question['case_id'],'final_answer':{'value':final},'steps':rendered}
        return prediction,audit
