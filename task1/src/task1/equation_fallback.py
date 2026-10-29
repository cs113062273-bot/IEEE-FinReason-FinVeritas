"""Bounded question-to-equation fallback for explicitly disclosed programs.

Unlike the scenario catalog this accepts a new arithmetic composition without
a family entry. Its language is deliberately small: named numeric declarations,
named arithmetic equations, and an unambiguous requested variable. It abstains
on unsupported prose, ambiguous units/checkpoints and nonlinear inverse tasks.
No gold, model API, arbitrary eval, imports, attribute access or file I/O.
"""
from __future__ import annotations

import ast
import re
from fractions import Fraction
from typing import Any, Mapping

from src.common.arithmetic import execute, format_value
from src.task1.hidden_program import execute as independent_execute

DIMLESS = (0, 0, 0)
MONEY, COUNT, TIME = (1, 0, 0), (0, 1, 0), (0, 0, 1)
UNITS = {
    "usd": (MONEY, Fraction(1)), "dollars": (MONEY, Fraction(1)),
    "usd million": (MONEY, Fraction(10**6)), "usd_million": (MONEY, Fraction(10**6)),
    "million usd": (MONEY, Fraction(10**6)),
    "usd thousand": (MONEY, Fraction(10**3)), "usd_thousand": (MONEY, Fraction(10**3)),
    "thousand usd": (MONEY, Fraction(10**3)),
    "usd billion": (MONEY, Fraction(10**9)), "usd_billion": (MONEY, Fraction(10**9)),
    "billion usd": (MONEY, Fraction(10**9)),
    "count": (COUNT, Fraction(1)), "shares": (COUNT, Fraction(1)), "tokens": (COUNT, Fraction(1)), "credits": (COUNT, Fraction(1)),
    "days": (TIME, Fraction(1)), "years": (TIME, Fraction(365)),
    "ratio": (DIMLESS, Fraction(1)), "fraction": (DIMLESS, Fraction(1)), "decimal rate": (DIMLESS, Fraction(1)), "dimensionless": (DIMLESS, Fraction(1)),
    "percent": (DIMLESS, Fraction(1,100)), "%": (DIMLESS, Fraction(1,100)),
    "percentage points": (DIMLESS, Fraction(1,100)),
    "bp": (DIMLESS, Fraction(1,10000)), "bps": (DIMLESS, Fraction(1,10000)), "basis points": (DIMLESS, Fraction(1,10000)),
    "usd_per_count": ((1,-1,0), Fraction(1)), "usd_per_year": ((1,0,-1), Fraction(1,365)),
    "times_per_year": ((0,0,-1), Fraction(1,365)),
}
ASSIGNMENT = re.compile(r"\b([A-Za-z][A-Za-z0-9_]*)\s*=\s*(?!=)")
LITERAL = re.compile(r"^([-+]?\d+(?:\.\d+)?(?:/\d+)?)\s*([A-Za-z_% ]*)$")
FUNCTIONS = {"min", "max", "abs", "floor", "ceil", "gt", "ge", "lt", "geom"}
RATE_UNITS={"percent","%","percentage points","bp","bps","basis points"}
RATIO_UNITS={"ratio","fraction","decimal rate"}


def _constant(node: ast.AST, known: Mapping[str,Fraction]) -> Fraction | None:
    """Inspect constants without evaluating powers, calls or arbitrary AST."""
    if isinstance(node,ast.Constant) and type(node.value) is int:return Fraction(node.value)
    if isinstance(node,ast.Name):return known.get(node.id)
    if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.USub,ast.UAdd)):
        value=_constant(node.operand,known)
        return -value if value is not None and isinstance(node.op,ast.USub) else value
    if isinstance(node,ast.BinOp) and isinstance(node.op,(ast.Add,ast.Sub,ast.Mult,ast.Div)):
        left,right=_constant(node.left,known),_constant(node.right,known)
        if left is None or right is None:return None
        if isinstance(node.op,ast.Add):return left+right
        if isinstance(node.op,ast.Sub):return left-right
        if isinstance(node.op,ast.Mult):return left*right
        if right:return left/right
    return None


def _rate_mode(name: str, unit: str, expressions: Mapping[str,str], known: Mapping[str,Fraction]) -> str:
    """Choose one explicit representation, refusing mixed/double conversions."""
    expected=10000 if unit in {"bp","bps","basis points"} else 100
    uses=[]
    for expression in expressions.values():
        tree=ast.parse(expression,mode="eval")
        parents={child:node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        for occurrence in ast.walk(tree):
            if not isinstance(occurrence,ast.Name) or occurrence.id!=name:continue
            conversions=[];small_multiplier=False;child=occurrence
            while child in parents:
                parent=parents[child]
                if isinstance(parent,ast.BinOp):
                    if isinstance(parent.op,ast.Div) and child is parent.left:
                        denominator=_constant(parent.right,known)
                        if denominator in {100,10000}:conversions.append(int(denominator))
                    if isinstance(parent.op,ast.Mult):
                        other=parent.right if child is parent.left else parent.left
                        if _constant(other,known) in {Fraction(1,100),Fraction(1,10000)}:small_multiplier=True
                child=parent
            if len(conversions)>1 or conversions and conversions[0]!=expected:
                raise ValueError("double or wrong rate conversion")
            if unit in RATIO_UNITS and conversions:
                raise ValueError("fractional ratio divided as percentage points")
            if small_multiplier and unit in RATE_UNITS and unit!="percentage points":
                raise ValueError("ambiguous implicit rate conversion multiplier")
            uses.append(bool(conversions))
    if unit in RATIO_UNITS:return "ratio"
    if uses and any(uses) and not all(uses):raise ValueError("mixed rate representations")
    if unit=="percentage points" or uses and all(uses):
        return "raw_basis_points" if expected==10000 else "raw_percentage_points"
    return "ratio"


def _representation(expression: str, representations: Mapping[str,str], dimensions, known):
    tree=ast.parse(expression,mode="eval").body
    if isinstance(tree,ast.Name):return representations.get(tree.id,"ratio")
    if isinstance(tree,ast.BinOp) and isinstance(tree.op,ast.Mult):
        for scalar,other in ((tree.left,tree.right),(tree.right,tree.left)):
            value=_constant(scalar,known)
            if value in {100,10000} and _dimension(ast.unparse(other),dimensions,known)==DIMLESS:
                return "raw_percentage_points" if value==100 else "raw_basis_points"
    if isinstance(tree,ast.BinOp) and isinstance(tree.op,(ast.Add,ast.Sub)):
        def part(node):return representations.get(node.id,"ratio") if isinstance(node,ast.Name) else "ratio"
        left,right=part(tree.left),part(tree.right)
        if left==right:return left
    return "ratio"


def _canonical_factor(representation: str) -> Fraction:
    return Fraction(1,100) if representation=="raw_percentage_points" else Fraction(1,10000) if representation=="raw_basis_points" else Fraction(1)


def _source_expression(text: str) -> str:
    # Replace decimal constants with exact rational integer expressions before
    # executing the stricter common interpreter, never with binary floats.
    text = text.strip().replace("^", "**").replace("×", "*").replace("÷", "/")
    for words,operator in (("divided by","/"),("multiplied by","*"),("times","*"),("plus","+"),("minus","-")):
        text=re.sub(rf"\b{words}\b",operator,text,flags=re.I)
    if len(text) > 2048:
        raise ValueError("expression size bound")
    return re.sub(r"(?<![\w.])\d+\.\d+(?![\w.])", lambda m: f"({Fraction(m[0]).numerator}/{Fraction(m[0]).denominator})", text)


def _segments(body: str):
    """Split at sentence/semicolon delimiters while retaining decimal points."""
    return list(re.finditer(r"[^;\n]+?(?=(?:[.;](?=\s|$)|\n|$))", body))


def _reverse_equations(body: str) -> list[str]:
    """A sentence after an equation is prose, never part of its expression.

    Reuse the decimal-aware segment splitter instead of consuming through the
    next 'Solve for' sentence. This accepts both period and semicolon endings.
    """
    equations = []
    for segment in _segments(body):
        match = re.search(r'\bEquation\s*:\s*(.+)', segment[0], re.I)
        if match:
            equations.append(match[1].strip())
    return equations


def _assignments(body: str) -> dict[str, tuple[str, int, int]]:
    result = {}
    for segment in _segments(body):
        text = segment[0]
        if re.search(r"\bEquation\s*:", text, re.I):
            continue
        matches = list(ASSIGNMENT.finditer(text))
        for i, match in enumerate(matches):
            end = matches[i+1].start() if i+1 < len(matches) else len(text)
            raw = text[match.end():end]
            expr = raw.strip().rstrip(", ")
            # Ordinary prose between declarations is not executable language.
            expr = re.sub(r",?\s+(?:and|then|let|define|compute|calculate|return)\s*$", "", expr, flags=re.I)
            name = match[1]
            if name in result or name in FUNCTIONS or name.startswith("_"):
                raise ValueError("duplicate/reserved variable declaration")
            start = segment.start()+match.end()+len(raw)-len(raw.lstrip())
            result[name] = (expr, start, start+len(expr))
    if len(result) > 64:
        raise ValueError("program size bound")
    return result


def _unit(text: str):
    normalized = " ".join(text.lower().split())
    if not normalized:
        return DIMLESS, Fraction(1)
    if normalized not in UNITS:
        raise ValueError(f"unsupported unit {normalized}")
    return UNITS[normalized]


def _dimension(expression: str, dimensions: Mapping[str, tuple[int,int,int]], values: Mapping[str, Fraction]):
    tree = ast.parse(expression, mode="eval")
    if sum(1 for _ in ast.walk(tree)) > 256:
        raise ValueError("AST node bound")
    def compatible(a, b, left=None, right=None):
        if a == b:
            return a
        if left is not None and isinstance(left, ast.Constant) and left.value == 0:
            return b
        if right is not None and isinstance(right, ast.Constant) and right.value == 0:
            return a
        raise ValueError("incompatible dimensions")
    def visit(node):
        if isinstance(node, ast.Constant) and type(node.value) is int:
            return DIMLESS
        if isinstance(node, ast.Name) and node.id in dimensions:
            return dimensions[node.id]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub,ast.UAdd)):
            return visit(node.operand)
        if isinstance(node, ast.BinOp):
            a,b = visit(node.left),visit(node.right)
            if isinstance(node.op, (ast.Add,ast.Sub)):
                return compatible(a,b,node.left,node.right)
            if isinstance(node.op, ast.Mult):
                return tuple(x+y for x,y in zip(a,b))
            if isinstance(node.op, ast.Div):
                return tuple(x-y for x,y in zip(a,b))
            if isinstance(node.op, ast.Pow) and b == DIMLESS:
                exponent = execute(ast.unparse(node.right),values)
                if exponent.denominator == 1 and abs(exponent) <= 120:
                    return tuple(x*int(exponent) for x in a)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FUNCTIONS and not node.keywords:
            dims = [visit(item) for item in node.args]
            name = node.func.id
            if name in {"abs", "floor", "ceil"} and len(dims)==1:
                return dims[0]
            if name in {"min", "max", "gt", "ge", "lt"} and len(dims)==2:
                value = compatible(*dims,*node.args)
                return DIMLESS if name in {"gt","ge","lt"} else value
            if name == "geom" and dims == [DIMLESS,DIMLESS]:
                return DIMLESS
        raise ValueError("unsupported dimensional AST")
    return visit(tree.body)


def solve_equations(question: Mapping[str,Any]) -> tuple[dict[str,Any],dict[str,Any]] | None:
    body = question["question"].split("\n\nAnswer format:")[0]
    if len(body)>16000 or question["answer_spec"]["type"]!="decimal":
        return None
    targets = list(re.finditer(r"\b(?:compute|calculate|return|find|solve for)\s+(?:the\s+)?([A-Za-z][A-Za-z0-9_]*)\b",body,re.I))
    if not targets:
        return None
    target = targets[-1][1]
    try:
        declarations = _assignments(body)
        if not declarations:
            return None
        values, dimensions, evidence, expressions, representations = {}, {}, [], {}, {}
        rate_literals={}
        for name,(text,start,end) in declarations.items():
            literal = LITERAL.fullmatch(text)
            if literal:
                dim,scale = _unit(literal[2])
                values[name] = Fraction(literal[1])*scale
                dimensions[name] = dim
                evidence.append({"name":name,"source":text,"start":start,"end":end,"canonical_value":str(values[name]),"unit":literal[2].strip(),"magnitude_scale":str(scale)})
                unit=" ".join(literal[2].lower().split())
                if unit in RATE_UNITS|RATIO_UNITS:rate_literals[name]=(unit,Fraction(literal[1]))
            else:
                expressions[name] = _source_expression(text)
        reverse_sources=_reverse_equations(body)
        all_expressions=dict(expressions)
        for index,equation in enumerate(reverse_sources):
            sides=equation.rstrip(". ").split("=")
            if len(sides)==2:all_expressions[f"reverse_{index}"]=_source_expression(f"({sides[0]})-({sides[1]})")
        for name,(unit,declared) in rate_literals.items():
            mode=_rate_mode(name,unit,all_expressions,{key:value for key,value in values.items() if key not in rate_literals})
            representations[name]=mode
            if mode!="ratio":values[name]=declared
            for item in evidence:
                if item["name"]==name:item.update(rate_representation=mode,execution_value=str(values[name]),declared_value=str(declared))
        active = set()
        executed=[]
        def resolve(name):
            if name in values:
                return values[name]
            if name not in expressions or name in active:
                raise ValueError("unbound name or cyclic dependency")
            active.add(name)
            expression = expressions[name]
            for node in ast.walk(ast.parse(expression,mode="eval")):
                if isinstance(node,ast.Name) and node.id not in FUNCTIONS:
                    resolve(node.id)
                    if node.id in expressions and dimensions[node.id]==DIMLESS and representations.get(node.id) in {"raw_percentage_points","raw_basis_points"}:
                        unit="percent" if representations[node.id]=="raw_percentage_points" else "bps"
                        if _rate_mode(node.id,unit,{name:expression},{})=="ratio":
                            raise ValueError("derived percentage points require explicit fractional conversion")
            dimensions[name] = _dimension(expression,dimensions,values)
            values[name] = execute(expression,values)
            if values[name] != independent_execute(expression,values):
                raise ValueError("independent interpreter disagreement")
            representations[name]=_representation(expression,representations,dimensions,values)
            executed.append(name)
            active.remove(name)
            return values[name]
        reverse = None
        if target not in declarations:
            equations = reverse_sources
            if len(equations)!=1:
                return None
            sides = equations[0].rstrip(". ").split("=")
            if len(sides)!=2:
                return None
            expression = _source_expression(f"({sides[0]})-({sides[1]})")
            for node in ast.walk(ast.parse(expression,mode="eval")):
                if isinstance(node,ast.Name) and node.id not in FUNCTIONS and node.id!=target:
                    resolve(node.id)
            dim, _ = _unit(question["answer_spec"].get("unit","dimensionless"))
            dimensions[target] = dim
            values[target] = Fraction(0)
            _dimension(expression,dimensions,values)
            def residual(x):
                return execute(expression,{**values,target:x})
            f0,f1 = residual(Fraction(0)),residual(Fraction(1))
            slope=f1-f0
            if not slope or residual(Fraction(2)) != f0+2*slope or residual(Fraction(-1)) != f0-slope:
                return None
            # AST derivative-free four-point gate is only a diagnostic; reject
            # powers/branches containing the unknown so adversarial polynomial
            # coincidences cannot masquerade as an affine equation.
            def is_affine(node):
                names={n.id for n in ast.walk(node) if isinstance(n,ast.Name)}
                if target not in names:return True
                if isinstance(node,(ast.Name,ast.UnaryOp)):return all(is_affine(c) for c in ast.iter_child_nodes(node) if isinstance(c,ast.expr))
                if isinstance(node,ast.BinOp):
                    left={n.id for n in ast.walk(node.left) if isinstance(n,ast.Name)}
                    right={n.id for n in ast.walk(node.right) if isinstance(n,ast.Name)}
                    if isinstance(node.op,(ast.Add,ast.Sub)):return is_affine(node.left) and is_affine(node.right)
                    if isinstance(node.op,ast.Mult):return not(target in left and target in right) and is_affine(node.left) and is_affine(node.right)
                    if isinstance(node.op,ast.Div):return target not in right and is_affine(node.left)
                return False
            if not is_affine(ast.parse(expression,mode="eval").body):return None
            values[target]=-f0/slope
            if residual(values[target])!=0 or independent_execute(expression,values)!=0:
                return None
            reverse={"equation":expression,"slope":str(slope),"solution":str(values[target]),"substitution_residual":"0","method":"affine-only exact substitution"}
        final = resolve(target)
        outdim,outscale = _unit(question["answer_spec"].get("unit","dimensionless"))
        if dimensions[target]!=outdim:
            return None
        steps=[]
        if len({slot["slot_id"] for slot in question["trace_spec"]["slots"]})!=len(question["trace_spec"]["slots"]):return None
        for slot in question["trace_spec"]["slots"]:
            name=slot["slot_id"]
            if name.endswith("_trace"):name=name[:-6]
            mentioned=[key for key in declarations if re.search(rf"\b{re.escape(key)}\b",slot.get("description",""))]
            if name in declarations and mentioned and name not in mentioned:return None
            # A checkpoint may use its explicit name or a description that
            # explicitly requests exactly one declared variable.
            if name not in declarations and name!=target:
                if len(mentioned)!=1:return None
                name=mentioned[0]
            value=resolve(name)
            dim,scale=_unit(slot["result_spec"].get("unit","dimensionless"))
            if dimensions[name]!=dim or slot["result_spec"]["type"]!="decimal":return None
            factor=_canonical_factor(representations.get(name,"ratio")) if dim==DIMLESS else Fraction(1)
            steps.append({"slot_id":slot["slot_id"],"value":format_value(value*factor/scale,slot["result_spec"])})
        factor=_canonical_factor(representations.get(target,"ratio")) if outdim==DIMLESS else Fraction(1)
        prediction={"schema_version":"finreason.task1.prediction/1.0.0","dataset_version":question["dataset_version"],"case_id":question["case_id"],"final_answer":{"value":format_value(final*factor/outscale,question["answer_spec"])},"steps":steps}
        audit={"strategy":"bounded_equation_fallback","target":target,"declarations":evidence,"equations":expressions,"dimensions":{name:list(dim) for name,dim in dimensions.items()},"rate_representations":representations,"reverse_verification":reverse,"routing_gate":"explicit named program, unit compatibility, complete named checkpoints","confidence_kind":"bounded syntax gate, not calibrated probability","resolved_equation_nodes":executed,"independent_reexecution_values":len(executed)+(1 if reverse else 0)}
        return prediction,audit
    except (KeyError,ValueError,TypeError,SyntaxError,ZeroDivisionError,OverflowError):
        return None
