"""Infer compact symbolic programs from only the released training labels.

All accepted programs reproduce every available training example. Public
FinChain supplies the operation vocabulary; the organizer rewritten prompts
provide binding schemas. Local-dev and held-out questions never fit programs.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations
from typing import Any, Sequence

from src.common.arithmetic import format_value, execute
from src.task1.templates import bind


@dataclass(frozen=True)
class Candidate:
    expression: str
    values: tuple[Fraction, ...]
    cost: int = 0


def infer_program(questions: Sequence[dict], golds: Sequence[dict]) -> dict[str, Any]:
    bound = [bind(q["question"])[1] for q in questions]
    columns = [tuple(row[i].value for row in bound) for i in range(len(bound[0]))]
    n = len(questions)
    atoms: dict[tuple[Fraction, ...], Candidate] = {}
    for i, col in enumerate(columns):
        atoms.setdefault(col, Candidate(f"x{i}", col))
    for c in (0, 1, 2, 3, 4, 12, 100, 365, 10000):
        vals = (Fraction(c),) * n
        atoms.setdefault(vals, Candidate(str(c), vals))
    base = list(atoms.values())
    numeric_slots=[s for s in questions[0]["trace_spec"]["slots"] if s["result_spec"]["type"]=="decimal"]
    enum_slots=[s for s in questions[0]["trace_spec"]["slots"] if s["result_spec"]["type"]=="enum"]
    targets = {s["slot_id"]: tuple(Fraction(g["slot_values"][s["slot_id"]]) for g in golds) for s in numeric_slots}
    known: dict[str, str] = {}
    pool = dict(atoms)

    def add(expr: str, values: tuple[Fraction, ...], cost: int) -> None:
        if any(abs(v) > 10**100 or v.denominator.bit_length() > 1024 for v in values): return
        previous = pool.get(values)
        candidate = Candidate(expr, values, cost)
        if previous is None or (cost, len(expr)) < (previous.cost, len(previous.expression)):
            pool[values] = candidate

    def binary(a: Candidate, b: Candidate, *, powers: bool = False) -> None:
        cost = a.cost + b.cost + 1
        for op, fn in (("+", lambda x,y:x+y), ("-",lambda x,y:x-y), ("*",lambda x,y:x*y), ("/",lambda x,y:x/y)):
            try: add(f"({a.expression}{op}{b.expression})", tuple(fn(x,y) for x,y in zip(a.values,b.values)), cost)
            except (ZeroDivisionError, OverflowError): pass
        add(f"min({a.expression},{b.expression})", tuple(min(x,y) for x,y in zip(a.values,b.values)), cost)
        add(f"max({a.expression},{b.expression})", tuple(max(x,y) for x,y in zip(a.values,b.values)), cost)
        if powers and all(v.denominator == 1 and abs(v) <= 24 for v in b.values):
            try: add(f"({a.expression}**{b.expression})",tuple(x**int(y) for x,y in zip(a.values,b.values)),cost)
            except (ZeroDivisionError, OverflowError): pass

    def exact_reverse(target: tuple[Fraction,...]) -> str | None:
        if target in pool: return pool[target].expression
        for a in list(pool.values()):
            for op, residual in (("+",tuple(t-x for t,x in zip(target,a.values))),
                                 ("-",tuple(x-t for t,x in zip(target,a.values))),
                                 ("*",tuple(t/x for t,x in zip(target,a.values))) if all(a.values) else ("*",None),
                                 ("/",tuple(x/t for t,x in zip(target,a.values))) if all(target) else ("/",None)):
                b = pool.get(residual) if residual is not None else None
                if b is not None and (op!="/" or all(b.values)):
                    return f"({a.expression}{op}{b.expression})"
        return None

    for a in base:
        add(f"(-{a.expression})", tuple(-v for v in a.values), 1)
        add(f"abs({a.expression})", tuple(abs(v) for v in a.values), 1)
        for b in base: binary(a,b,powers=True)
    # Recognizable closed forms used by the public finance template library.
    varying = [a for a in base if len(set(a.values)) > 1]
    rate_atoms = [Candidate(f"({a.expression}/100)",tuple(v/100 for v in a.values),1) for a in varying]
    amount_atoms = [a for a in varying if max(abs(v) for v in a.values) > 50]
    period_atoms = [a for a in base if all(v.denominator == 1 and 0 <= v <= 40 for v in a.values)]
    for rate in rate_atoms:
        for period in period_atoms:
            try:
                factors = tuple((1+r)**int(t) for r,t in zip(rate.values,period.values))
                fac = Candidate(f"((1+{rate.expression})**{period.expression})",factors,3)
                add(fac.expression,fac.values,fac.cost)
                for amount in amount_atoms:
                    add(f"({amount.expression}*({fac.expression}-1))",tuple(p*(f-1) for p,f in zip(amount.values,factors)),5)
                    add(f"({amount.expression}*{fac.expression})",tuple(p*f for p,f in zip(amount.values,factors)),4)
                    if all(factors): add(f"({amount.expression}/{fac.expression})",tuple(p/f for p,f in zip(amount.values,factors)),4)
                    if all(rate.values) and all(factors):
                        ann = tuple((1-1/f)/r for f,r in zip(factors,rate.values))
                        add(f"({amount.expression}*((1-1/{fac.expression})/{rate.expression}))",tuple(p*a for p,a in zip(amount.values,ann)),7)
            except (ZeroDivisionError, OverflowError): pass
    for _ in range(4):
        found = False
        for slot, target in targets.items():
            if slot in known: continue
            expression = exact_reverse(target)
            if expression is not None:
                known[slot] = expression
                add(expression,target,2)
                base.append(Candidate(expression,target,2))
                found = True
        if not found: break
        for a in base[-len(known):]:
            for b in base: binary(a,b,powers=True); binary(b,a,powers=True)

    answer_spec = questions[0]["answer_spec"]
    gold_final = [g["final_value"] for g in golds]
    def matches(values: tuple[Fraction,...]) -> bool:
        if answer_spec["type"] != "decimal": return False
        return all(format_value(v,answer_spec) == str(g) for v,g in zip(values,gold_final))

    final: str | None = None
    enum: dict[str, Any] | None = None
    if answer_spec["type"] == "decimal":
        for cand in sorted(pool.values(),key=lambda c:(c.cost,len(c.expression))):
            if matches(cand.values): final = cand.expression; break
        if final is None:
            # Rounded labels cannot be reversed exactly. Use one fast rational
            # gate, then verify the complete training vector before accepting.
            first = Fraction(gold_final[0]); rounding = answer_spec["rounding"]
            tolerance = Fraction(1,2*10**rounding.get("decimal_places",12)) if rounding["mode"] != "exact" else Fraction()
            candidates = sorted(pool.values(),key=lambda c:(c.cost,len(c.expression)))
            for a in base:
                if final is not None: break
                for b in candidates:
                    if a.cost+b.cost > 9: continue
                    for op, fn in (("+",lambda x,y:x+y),("-",lambda x,y:x-y),("*",lambda x,y:x*y),("/",lambda x,y:x/y)):
                        try:
                            if abs(fn(a.values[0],b.values[0])-first) > tolerance: continue
                            vals = tuple(fn(x,y) for x,y in zip(a.values,b.values))
                            if matches(vals): final=f"({a.expression}{op}{b.expression})"; break
                        except ZeroDivisionError: pass
                    if final is not None: break
    elif len(set(gold_final)) > 1:
        for cand in sorted(pool.values(),key=lambda c:(c.cost,len(c.expression))):
            labels: dict[str,str] = {}; compatible = True
            for value,label in zip(cand.values,gold_final):
                sign = "positive" if value > 0 else "negative" if value < 0 else "zero"
                if sign in labels and labels[sign] != label: compatible=False;break
                labels[sign]=label
            if compatible:
                enum={"expression":cand.expression,"labels":labels};break
    slot_enums={}
    for slot in enum_slots:
        labels_gold=[g["slot_values"][slot["slot_id"]] for g in golds]
        if len(set(labels_gold)) < 2:continue
        for cand in sorted(pool.values(),key=lambda c:(c.cost,len(c.expression))):
            labels={};compatible=True
            for value,label in zip(cand.values,labels_gold):
                sign="positive" if value>0 else "negative" if value<0 else "zero"
                if sign in labels and labels[sign]!=label:compatible=False;break
                labels[sign]=label
            if compatible:
                slot_enums[slot["slot_id"]]={"expression":cand.expression,"labels":labels};break
    return {"final":final,"enum":enum,"slots":known,"slot_enums":slot_enums,"trained_cases":n,"numeric_bindings":len(bound[0]),"unresolved_slots":sorted(set(targets)-set(known))}
