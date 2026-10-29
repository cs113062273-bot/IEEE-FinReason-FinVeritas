"""Translate finite arithmetic assignments into a DAG; never execute statements."""
import ast,copy
from src.task1.program_reexecution import parse_number,FUNCTIONS

def compile_program(proposal):
    if not isinstance(proposal,dict):raise ValueError('proposal object')
    text=proposal.get('final_expression','')
    if not isinstance(text,str) or len(text)>2048:raise ValueError('source bound')
    text=text.replace('^','**');tree=ast.parse(text,mode='exec')
    if any(not isinstance(s,(ast.Assign,ast.Expr)) for s in tree.body):raise ValueError('unsupported program statement')
    if not any(isinstance(s,ast.Assign) for s in tree.body):return proposal,{'compiled':False}
    if len(tree.body)>32 or sum(1 for _ in ast.walk(tree))>512:raise ValueError('straight-line size bound')
    out=copy.deepcopy(proposal);steps=out.setdefault('steps',{})
    if not isinstance(steps,dict) or not isinstance(out.get('variables',{}),dict):raise ValueError('binding object')
    original_steps=list(steps);used=set(steps)|set(out.get('variables',{}))|FUNCTIONS;bindings={};proofs=[]
    class Expression(ast.NodeTransformer):
        def __init__(self,source=text):self.source=source
        def visit_Name(self,node):
            return ast.copy_location(ast.Name(bindings.get(node.id,node.id),ast.Load()),node)
        def visit_Constant(self,node):
            if type(node.value) not in {int,float}:raise ValueError('nonnumeric program literal')
            q=parse_number(ast.get_source_segment(self.source,node))
            return ast.copy_location(ast.BinOp(ast.Constant(q.numerator),ast.Div(),ast.Constant(q.denominator)),node)
    final=None
    for index,statement in enumerate(tree.body):
        if isinstance(statement,ast.Assign) and len(statement.targets)==1 and isinstance(statement.targets[0],ast.Name):
            name=statement.targets[0].id
            if not name[0].isalpha() or name in FUNCTIONS:raise ValueError('assignment name')
            expression=ast.unparse(Expression().visit(statement.value));new='derived_'+str(index)
            while new in used:new='derived_'+new
            used.add(new);steps[new]=expression;bindings[name]=new;final=new
            proofs.append({'source_assignment':ast.get_source_segment(text,statement),'original_name':name,'dag_name':new,'expression':expression})
        elif isinstance(statement,ast.Expr) and index==len(tree.body)-1:
            final=ast.unparse(Expression().visit(statement.value))
        else:raise ValueError('only simple arithmetic assignments and a final expression are supported')
    if len(steps)+len(out.get('variables',{}))>96:raise ValueError('expanded binding bound')
    checkpoint_errors={}
    for key in original_steps:
        source=str(steps[key]).replace('^','**')
        try:
            if len(source)>2048:raise ValueError('checkpoint expression bound')
            tree=ast.parse(source,mode='eval')
            if sum(1 for _ in ast.walk(tree))>256:raise ValueError('checkpoint AST bound')
            steps[key]=ast.unparse(Expression(source).visit(tree.body))
        except (ValueError,SyntaxError,RecursionError) as exc:checkpoint_errors[key]=type(exc).__name__
    out['final_expression']=final
    return out,{'compiled':True,'method':'AST assignment to immutable DAG; no exec/eval','assignments':proofs,'checkpoint_errors':checkpoint_errors,'semantic_verified':False}


# Lower numeric Python and/or to pure conditional expressions, without eval.
def lower_logic(proposal):
    out=copy.deepcopy(proposal);proofs=[]
    def lower(source):
        if not isinstance(source,str) or len(source)>2048:raise ValueError('expression bound')
        source=source.replace('^','**');tree=ast.parse(source,mode='eval')
        if sum(1 for _ in ast.walk(tree))>192:raise ValueError('source AST bound')
        if not any(isinstance(n,ast.BoolOp) for n in ast.walk(tree)):return source
        class Rewrite(ast.NodeTransformer):
            def visit_Constant(self,node):
                if type(node.value) not in {int,float}:raise ValueError('numeric operands required')
                q=parse_number(ast.get_source_segment(source,node))
                return ast.BinOp(ast.Constant(q.numerator),ast.Div(),ast.Constant(q.denominator))
            def visit_BoolOp(self,node):
                if not 2<=len(node.values)<=4:raise ValueError('numeric logic arity bound')
                args=[self.visit(v) for v in node.values];result=args[-1]
                for value in reversed(args[:-1]):
                    test=ast.Compare(value,[ast.NotEq()],[ast.Constant(0)])
                    result=ast.IfExp(test,result,value) if isinstance(node.op,ast.And) else ast.IfExp(test,value,result)
                return result
        lowered=Rewrite().visit(tree)
        if sum(1 for _ in ast.walk(lowered))>256:raise ValueError('lowered AST bound')
        result=ast.unparse(lowered)
        if len(result)>2048:raise ValueError('lowered expression bound')
        proofs.append({'source':source,'lowered':result,'meaning':'numeric truth-value selection, equivalent to Python and/or for pure real-number operands'})
        return result
    out['final_expression']=lower(out['final_expression'])
    errors={}
    for key,raw in out.get('steps',{}).items():
        try:out['steps'][key]=lower(str(raw))
        except (ValueError,SyntaxError,RecursionError) as exc:errors[key]=type(exc).__name__
    return out,{'rewrites':proofs,'checkpoint_errors':errors,'semantic_verified':False}
