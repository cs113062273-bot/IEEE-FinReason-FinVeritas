"""Frozen E15 baseline and prior independent source parsers, read-only."""
import importlib.util, sys, json, hashlib
from pathlib import Path
WORK=Path(__file__).resolve().parents[2]; OUT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('three_candidate_source_helpers',WORK/'runs/scope_support/common.py')
prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)
ROOT=prior.ROOT; BEST=prior.BEST; MODEL=WORK/'runs/i15_feedback_20261015'
raw=prior.raw; previous=prior.previous; parent=prior.parent
rows=prior.rows; read=prior.read; sha=prior.sha; same=prior.same; save=prior.save; parsed=prior.parsed; member_labels=prior.member_labels
LINK=raw.LINK; XLINK=raw.XLINK
local=lambda q:q.split('}')[-1]
# The frozen label helper imports common by name. Bind only its parser global
# when loading it under this experiment's separate module namespace.
member_labels.__globals__['raw']=raw
