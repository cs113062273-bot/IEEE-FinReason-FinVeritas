"""Bounded exact reexecution of proposed arithmetic programs.

Exact decimal literals, named intermediate DAGs, and bounded conditionals are
compiled to the existing restricted arithmetic AST. This checks a proposed
program, not its financial meaning. Unsupported programs remain diagnostics;
the production always-answer layer still supplies a prediction.
"""
import ast
from fractions import Fraction
import re

from src.common.arithmetic import execute
from src.common.fraction_budget import checked,binary
from src.task1.hidden_program import execute as independent_execute

FUNCTIONS={'min','max','abs','floor','ceil','gt','ge','lt','geom'}


def parse_number(value):
    """Bound exponent text before Fraction allocates decimal powers."""
    if isinstance(value,bool):raise ValueError('boolean is not a numeric input')
    if isinstance(value,Fraction):return checked(value)
    text=str(value).strip()
    if len(text)>2048:raise ValueError('numeric literal length bound')
    exponent=re.search(r'[eE]([-+]?\d+)$',text)
    if exponent and abs(int(exponent[1]))>4000:raise ValueError('decimal exponent resource bound')
    return checked(Fraction(text))


def source_number_witnesses(body):
    """Literal and explicitly normalized values with original evidence.

    No derived financial quantity or guessed missing input becomes a witness.
    Accounting parentheses, comma groups, percent/bp and explicit magnitudes
    are representation changes. They do not establish the model's role choice.
    """
    result={}
    pattern=r'(?<![\w.])(?:\(\s*)?[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:/\d+)?(?:\s*\))?(?!\w|\.\d)'
    def add(value,source,start,end,kind):
        value=checked(value)
        result.setdefault(value,[]).append({'source':source,'start':start,'end':end,'normalization':kind,'value':str(value)})
    for m in re.finditer(pattern,body):
        text=m[0].strip();accounting=text.startswith('(') and text.endswith(')')
        try:
            value=parse_number(text.strip('() ').replace(',',''))
            if accounting:value=-abs(value)
            add(value,m[0],m.start(),m.end(),'accounting sign' if accounting else 'literal')
            tail=body[m.end():]
            unit=re.match(r'\s*(%|percent\b|bps?\b|basis\s+points?\b|(?:USD\s+)?(?:thousand|million|billion)\b)',tail,re.I)
            if unit:
                word=unit[1].lower()
                if word=='%' or word=='percent':factor=Fraction(1,100)
                elif re.fullmatch(r'bps?|basis\s+points?',word):factor=Fraction(1,10000)
                else:
                    magnitude=word.split()[-1];factor=Fraction({'thousand':1000,'million':1000000,'billion':1000000000}[magnitude])
                add(binary(value,factor,'*'),body[m.start():m.end()+unit.end()],m.start(),m.end()+unit.end(),'explicit unit scale')
        except (ValueError,ZeroDivisionError):continue
    for word,value in [('zero',0),('one',1),('two',2)]:
        for m in re.finditer(r'\b'+word+r'\b',body,re.I):add(Fraction(value),m[0],m.start(),m.end(),'explicit number word')
    return result


def exact_expression(source,values):
    if not isinstance(source,str) or len(source)>2048:raise ValueError('expression size/type')
    source=source.replace('^','**')
    tree=ast.parse(source,mode='eval')
    if sum(1 for _ in ast.walk(tree))>256:raise ValueError('expression node bound')
    def number(node):
        if type(node.value) not in {int,float}:raise ValueError('nonnumeric literal')
        q=parse_number(ast.get_source_segment(source,node))
        return ast.BinOp(ast.Constant(q.numerator),ast.Div(),ast.Constant(q.denominator))
    def value(node):return execute(ast.unparse(visit(node)),values)
    def condition(node):
        if isinstance(node,ast.Compare) and len(node.ops)==len(node.comparators)==1:
            left,right=value(node.left),value(node.comparators[0]);op=node.ops[0]
            if isinstance(op,ast.Lt):return left<right
            if isinstance(op,ast.LtE):return left<=right
            if isinstance(op,ast.Gt):return left>right
            if isinstance(op,ast.GtE):return left>=right
            if isinstance(op,ast.Eq):return left==right
            if isinstance(op,ast.NotEq):return left!=right
        raise ValueError('unsupported conditional predicate')
    def visit(node):
        if isinstance(node,ast.Constant):return number(node)
        if isinstance(node,ast.Name) and node.id in values:return node
        if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.UAdd,ast.USub)):
            return ast.UnaryOp(node.op,visit(node.operand))
        if isinstance(node,ast.BinOp) and isinstance(node.op,(ast.Add,ast.Sub,ast.Mult,ast.Div,ast.Pow)):
            return ast.BinOp(visit(node.left),node.op,visit(node.right))
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in FUNCTIONS and not node.keywords:
            return ast.Call(node.func,[visit(a) for a in node.args],[])
        if isinstance(node,ast.IfExp):
            # Visit both arms structurally first, including the unused branch;
            # dangerous syntax cannot hide behind a false condition.
            yes,no=visit(node.body),visit(node.orelse)
            return yes if condition(node.test) else no
        raise ValueError('unsupported program AST: '+type(node).__name__)
    normalized=ast.unparse(visit(tree.body));result=execute(normalized,values)
    check=independent_execute(source,values)
    if result!=check:raise ValueError('independent reexecution disagreement')
    return result,normalized


def reexecute(proposal,source_values):
    if not isinstance(proposal,dict):raise ValueError('program object required')
    variables,steps=proposal.get('variables',{}),proposal.get('steps',{})
    if not isinstance(variables,dict) or not isinstance(steps,dict) or len(variables)+len(steps)>96:raise ValueError('program mapping bound')
    if any(not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*',name) or name in FUNCTIONS for name in steps):raise ValueError('intermediate identifier')
    values={};proofs={};active=set()
    for name,value in variables.items():
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*',name) or name in FUNCTIONS:raise ValueError('variable identifier')
        q=parse_number(value)
        if q not in source_values:raise ValueError('variable lacks a source-number witness')
        values[name]=q
    if set(values)&set(steps):raise ValueError('conflicting source and intermediate names')
    def resolve(name):
        if name in values:return values[name]
        aliases=[key for key in steps if key.removesuffix('_trace')==name]
        canonical=name if name in steps else aliases[0] if len(aliases)==1 else None
        if canonical is None or canonical in active:raise ValueError('missing or cyclic intermediate '+name)
        if canonical in values:values[name]=values[canonical];return values[name]
        active.add(canonical);expression=str(steps[canonical])
        evaluate(expression)
        result,normalized=exact_expression(expression,values)
        values[canonical]=result;values[name]=result;proofs[canonical]={'expression':expression,'normalized':normalized,'exact_value':str(result)}
        active.remove(canonical);return result
    def evaluate(expression):
        tree=ast.parse(expression.replace('^','**'),mode='eval')
        for node in ast.walk(tree):
            if isinstance(node,ast.Name) and node.id not in FUNCTIONS:resolve(node.id)
        return exact_expression(expression,values)
    final,normalized=evaluate(proposal['final_expression'])
    return {'value':final,'normalized_final':normalized,'intermediate_proofs':proofs,'values':values}
