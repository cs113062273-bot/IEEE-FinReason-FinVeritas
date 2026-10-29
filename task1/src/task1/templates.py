"""Public-question numeric bindings with stable source spans."""
from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction

NUMBER = re.compile(r"(?<![\w.])[-+]?\d+(?:\.\d+)?(?:/\d+)?(?!\w|\.\d)")


@dataclass(frozen=True)
class Binding:
    name: str
    text: str
    value: Fraction
    start: int
    end: int


def bind(question: str) -> tuple[str, tuple[Binding, ...]]:
    body = question.split("\n\nAnswer format:")[0]
    bindings = tuple(Binding(f"x{i}", m.group(), Fraction(m.group()), m.start(), m.end()) for i, m in enumerate(NUMBER.finditer(body)))
    return NUMBER.sub("#", body), bindings
