"""Representational repairs only; later source and AST checks remain required."""
import copy,re
from fractions import Fraction
from src.task1.program_reexecution import parse_number

NUMBER=r'[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?(?:/\d+)?'

def scalar(value):
    if isinstance(value,bool):raise ValueError('boolean is not a source quantity')
    text=str(value).strip().replace(',','')
    if len(text)>256:raise ValueError('numeric text bound')
    percent=text.endswith('%')
    if percent:text=text[:-1].strip()
    if not re.fullmatch(NUMBER,text):raise ValueError('unsupported numeric representation')
    return parse_number(text)/(100 if percent else 1)

def normalize(proposal,answer_spec):
    if not isinstance(proposal,dict):raise ValueError('proposal object required')
    out=copy.deepcopy(proposal);variables=out.get('variables',{});steps=out.get('steps',{})
    if not isinstance(variables,dict) or not isinstance(steps,dict) or len(variables)+len(steps)>96:raise ValueError('mapping bound')
    names=set(variables)|set(steps);renamed={}
    for name in sorted(names):
        if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9_ /%()\-]{1,96}',name) or not re.search('[A-Za-z]',name):raise ValueError('unrepairable name')
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*',name):
            replacement='named_'+re.sub(r'[^A-Za-z0-9_]+','_',name).strip('_')
            if replacement in names or replacement in renamed.values():raise ValueError('colliding normalized names')
            renamed[name]=replacement
    def expression(text):
        if not isinstance(text,str) or len(text)>2048:raise ValueError('expression bound')
        if renamed:
            pattern=r'(?<![A-Za-z0-9_])(?:'+'|'.join(re.escape(n) for n in sorted(renamed,key=len,reverse=True))+r')(?![A-Za-z0-9_])'
            text=re.sub(pattern,lambda m:renamed[m[0]],text)
        # Numeric casts around an already bound scalar are representational;
        # no Python function is executed and nested/arbitrary calls stay invalid.
        text=re.sub(r'\bfloat\(\s*([A-Za-z][A-Za-z0-9_]*)\s*\)',r'\1',text)
        return re.sub(r'(?<![\w.])('+NUMBER+r')\s*%',lambda m:'('+m[1]+'/100)',text)
    new_variables={renamed.get(k,k):str(scalar(v)) for k,v in variables.items()}
    new_steps={}
    for name,raw in steps.items():
        key=renamed.get(name,name)
        if name in variables:
            # Models sometimes repeat a source literal in steps. Remove only
            # an exactly equal literal; conflicting assignments stay invalid.
            if scalar(raw)!=scalar(variables[name]):raise ValueError('conflicting repeated source quantity')
            continue
        new_steps[key]=expression(str(raw))
    out['variables']=new_variables;out['steps']=new_steps
    if out.get('final_expression'):out['final_expression']=expression(out['final_expression'])
    answer=out.get('final_answer')
    if isinstance(answer,str) and answer.strip().endswith('%') and answer_spec['type']=='decimal':
        # Direct final answers follow declared output units, unlike inputs.
        value=scalar(answer)
        if answer_spec['unit']=='percent':value*=100
        elif answer_spec['unit']!='ratio':raise ValueError('percentage answer has incompatible output unit')
        out['final_answer']=str(value)
    return out,{'renamed_variables':renamed,'removed_repeated_source_steps':sorted(set(variables)&set(steps)),
                'semantic_verified':False,'operation':'representation normalization, then original source and AST checks'}
