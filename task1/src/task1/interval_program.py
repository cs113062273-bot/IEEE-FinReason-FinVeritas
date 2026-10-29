"""Bounded rational enclosures for proposed programs with fractional powers.

An integer nth-root proves the enclosure; an independent Decimal executor
checks the rendered answer. This establishes arithmetic only, not semantics.
"""
import ast,math
from decimal import Decimal,localcontext
from fractions import Fraction
from src.common.fraction_budget import checked,binary,power
from src.common.arithmetic import format_value
from src.task1.program_reexecution import parse_number,FUNCTIONS
from src.task1.proposal_normalization import normalize

MAX_ROOT_BITS=48000
CALLS=FUNCTIONS|{'sqrt'}

def nth_floor(value,degree):
    if not 2<=degree<=64 or value<0 or value.bit_length()>MAX_ROOT_BITS:raise ValueError('integer-root resource bound')
    if degree==2:return math.isqrt(value)
    if value<2:return value
    guess=1<<((value.bit_length()+degree-1)//degree)
    for _ in range(256):
        next_guess=((degree-1)*guess+value//(guess**(degree-1)))//degree
        if next_guess>=guess:
            if not guess**degree<=value<(guess+1)**degree:raise ValueError('integer-root residual disagreement')
            return guess
        guess=next_guess
    raise ValueError('integer-root iteration bound')

def root_bounds(value,degree,digits):
    value=checked(value)
    if value<0 or not 2<=degree<=64:raise ValueError('positive real bounded roots only')
    numerator=nth_floor(value.numerator,degree);denominator=nth_floor(value.denominator,degree)
    if numerator**degree==value.numerator and denominator**degree==value.denominator:
        exact=Fraction(numerator,denominator);return exact,exact
    if not 24<=digits<=120:raise ValueError('root precision bound')
    if value.numerator.bit_length()+math.ceil(digits*degree*math.log2(10))>MAX_ROOT_BITS:raise ValueError('projected scaled-root size bound')
    scale=10**digits;scaled=value.numerator*scale**degree//value.denominator
    floor=nth_floor(scaled,degree)
    return checked(Fraction(floor,scale)),checked(Fraction(floor+1,scale))

def point(q):return checked(q),checked(q)
def plus(a,b):return binary(a[0],b[0],'+'),binary(a[1],b[1],'+')
def minus(a,b):return binary(a[0],b[1],'-'),binary(a[1],b[0],'-')
def times(a,b):
    products=[binary(x,y,'*') for x in a for y in b];return min(products),max(products)
def divide(a,b):
    if b[0]<=0<=b[1]:raise ZeroDivisionError('interval denominator includes zero')
    return times(a,(binary(Fraction(1),b[1],'/'),binary(Fraction(1),b[0],'/')))

class Program:
    def __init__(self,proposal,source_values):
        self.variables={};self.steps={}
        for name,value in proposal.get('variables',{}).items():
            if not name.isidentifier() or name in CALLS:raise ValueError('source identifier')
            q=parse_number(value)
            if q not in source_values:raise ValueError('source-number witness missing')
            self.variables[name]=q
        for name,expression in proposal.get('steps',{}).items():
            if not name.isidentifier() or name in self.variables or name in CALLS:raise ValueError('conflicting step identifier')
            self.steps[name]=self.parse(str(expression))
        if len(self.variables)+len(self.steps)>96:raise ValueError('binding bound')
        self.final=self.parse(proposal['final_expression'])

    @staticmethod
    def parse(text):
        if not isinstance(text,str) or len(text)>2048:raise ValueError('expression bound')
        text=text.replace('^','**');tree=ast.parse(text,mode='eval')
        if sum(1 for _ in ast.walk(tree))>256:raise ValueError('AST bound')
        # Numeric literal strings are recovered before float conversion.
        for node in ast.walk(tree):
            if isinstance(node,ast.Constant):
                if type(node.value) not in {int,float}:raise ValueError('nonnumeric literal')
                node.exact_fraction=parse_number(ast.get_source_segment(text,node))
        return tree.body

    def evaluate(self,*,digits=48,decimal=False):
        cache={name:(self.as_decimal(value) if decimal else point(value)) for name,value in self.variables.items()};active=set();roots=[]
        def resolve(name):
            if name in cache:return cache[name]
            aliases=[s for s in self.steps if s.removesuffix('_trace')==name]
            canonical=name if name in self.steps else aliases[0] if len(aliases)==1 else None
            if canonical is None or canonical in active:raise ValueError('missing/cyclic dependency')
            if canonical not in cache:
                active.add(canonical);cache[canonical]=visit(self.steps[canonical]);active.remove(canonical)
            cache[name]=cache[canonical];return cache[name]
        def exponent(base,exp):
            if exp[0]!=exp[1]:raise ValueError('uncertain exponent')
            q=exp[0]
            if abs(q.numerator)>128 or q.denominator>64:raise ValueError('power bound')
            if q<0:return divide(point(Fraction(1)),exponent(base,point(-q)))
            if q.denominator==1:
                values=[power(v,q,max_exponent=128) for v in base]
                if base[0]<=0<=base[1] and q>0 and q.numerator%2==0:values.append(Fraction(0))
                return min(values),max(values)
            if base[0]<0:raise ValueError('negative fractional base')
            if len(roots)>=32:raise ValueError('root operation bound')
            low=power(base[0],Fraction(q.numerator),max_exponent=128)
            high=power(base[1],Fraction(q.numerator),max_exponent=128)
            result=root_bounds(low,q.denominator,digits)[0],root_bounds(high,q.denominator,digits)[1]
            roots.append({'power':str(q),'base_lower':str(base[0]),'base_upper':str(base[1]),'result_lower':str(result[0]),'result_upper':str(result[1])})
            return result
        def visit(node):
            if isinstance(node,ast.Constant):return self.as_decimal(node.exact_fraction) if decimal else point(node.exact_fraction)
            if isinstance(node,ast.Name):return resolve(node.id)
            if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.USub,ast.UAdd)):
                x=visit(node.operand)
                return (-x if decimal else (-x[1],-x[0])) if isinstance(node.op,ast.USub) else x
            if isinstance(node,ast.BinOp):
                a,b=visit(node.left),visit(node.right)
                if isinstance(node.op,ast.Add):return a+b if decimal else plus(a,b)
                if isinstance(node.op,ast.Sub):return a-b if decimal else minus(a,b)
                if isinstance(node.op,ast.Mult):return a*b if decimal else times(a,b)
                if isinstance(node.op,ast.Div):return a/b if decimal else divide(a,b)
                if isinstance(node.op,ast.Pow):return a**b if decimal else exponent(a,b)
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and not node.keywords:
                name=node.func.id;args=[visit(x) for x in node.args]
                if name=='sqrt' and len(args)==1:return args[0].sqrt() if decimal else exponent(args[0],point(Fraction(1,2)))
                if name in {'min','max'} and 1<=len(args)<=4:
                    fn=min if name=='min' else max
                    return fn(args) if decimal else (fn(a[0] for a in args),fn(a[1] for a in args))
                if name=='abs' and len(args)==1:
                    a=args[0]
                    if decimal:return abs(a)
                    return (Fraction(0) if a[0]<=0<=a[1] else min(abs(a[0]),abs(a[1])),max(abs(a[0]),abs(a[1])))
                if name in {'floor','ceil'} and len(args)==1:
                    fn=math.floor if name=='floor' else math.ceil
                    return Decimal(fn(args[0])) if decimal else (Fraction(fn(args[0][0])),Fraction(fn(args[0][1])))
            raise ValueError('unsupported interval AST '+type(node).__name__)
        return visit(self.final),cache,roots

    @staticmethod
    def as_decimal(value):return Decimal(value.numerator)/Decimal(value.denominator)

def solve(proposal,source_values,spec):
    if spec['type']!='decimal' or spec['rounding']['mode']!='half_up':raise ValueError('finite decimal rounding required')
    proposal,_=normalize(proposal,spec);program=Program(proposal,source_values)
    if not 0<=spec['rounding']['decimal_places']<=24:raise ValueError('output decimal-place bound')
    for digits in [48,80,120]:
        interval,values,roots=program.evaluate(digits=digits)
        lower,upper=(format_value(v,spec) for v in interval)
        if lower!=upper:continue
        # A different arithmetic implementation checks the rendered result.
        source_digits=max((len(str(abs(v.numerator)))+len(str(v.denominator)) for v in program.variables.values()),default=1)
        with localcontext() as ctx:
            ctx.prec=min(4500,source_digits+180)
            independent,_,_=program.evaluate(decimal=True)
            if not independent.is_finite() or format_value(parse_number(str(independent)),spec)!=lower:raise ValueError('independent Decimal disagreement')
        return lower,{'arithmetic_method':'rational root enclosures plus independent Decimal','precision_digits':digits,
                       'lower_bound':str(interval[0]),'upper_bound':str(interval[1]),'rounded_value':lower,
                       'roots':roots,'arithmetic_verified':True,'semantic_verified':False}
    raise ValueError('rounding not proved at bounded precision')
