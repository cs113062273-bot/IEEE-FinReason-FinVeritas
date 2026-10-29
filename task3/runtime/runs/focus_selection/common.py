"""Frozen666 baseline and independent supplied-source parser."""
import importlib.util,json,hashlib,sys
from pathlib import Path
WORK=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
ROOT=WORK/'core/source'
BEST=WORK/'DELIVERY/task3_R15_plan_best_provisional_97_94_20261015'
MODEL=WORK/'runs/task3_post_r15_candidates_feedback_20261015'
spec=importlib.util.spec_from_file_location('frozen_r15_source_helpers',WORK/'runs/dimensional_strategies/experiments.py')
parent=importlib.util.module_from_spec(spec);spec.loader.exec_module(parent)
raw=parent.raw;previous=parent.previous
raw.xml=previous.ownership.s.closed_xml
rows=parent.rows;read=parent.read;sha=parent.sha;same=parent.same;save=parent.save
def parsed(row):
    cache=WORK/'runs/task3_after_r15_20261015/cache'/(row['id']+'.json')
    if cache.exists():return read(cache)
    return raw.source_parse(row['query'])
def augment_external_metadata(p):
    from normalized_metadata import augment
    return augment(p)
