"""One compatible numeric fact per complete financial aspect in source rules.

C8 already normalizes rounded duplicates. Previously the later source rules
parsed the raw instance again and could reject those same facts as conflicting
or count repeated evidence. Share C8's accuracy policy with that decision path.
Original XML remains unchanged and all representatives are reported facts.
"""
from collections import defaultdict
from decimal import Decimal
from types import SimpleNamespace

from task3.round6_source_interval import accuracy
from source_equations import aspect


def normalize(parsed):
    if parsed.get('duplicate_context_ids') or parsed.get('duplicate_unit_ids'):
        return parsed
    groups=defaultdict(list)
    for i,f in enumerate(parsed['facts']):
        frame=aspect(f)
        groups[(f['QName'],frame) if frame is not None else ('unresolved',i)].append((i,f))
    kept=[];proofs=[];removed=0
    for entries in groups.values():
        if len(entries)==1:
            kept.extend(entries);continue
        intervals=[];by_rank=defaultdict(set);ranked=[]
        for i,f in entries:
            try:
                d,bounds,detail=accuracy(SimpleNamespace(
                    source={'raw_xml':f.get('raw_xml','')},decimals=f.get('decimals'),value=Decimal(f['value'])))
            except (ValueError,OverflowError,ArithmeticError):
                break
            rank=float('inf') if d is None else d
            intervals.append(bounds);by_rank[rank].add(Decimal(f['value']))
            ranked.append((rank,i,f,detail))
        else:
            if (all(len(values)==1 for values in by_rank.values())
                and max(v[0] for v in intervals)<=min(v[1] for v in intervals)):
                best=max(t[0] for t in ranked)
                winner=min((t for t in ranked if t[0]==best),key=lambda t:(
                    t[2]['context_ref'],t[2]['unit_ref'],t[2].get('raw_xml','')))
                rank,i,f,detail=winner
                # The raw attribute remains auditable; only its numerical
                # precision equivalent is exposed to downstream arithmetic.
                representative={**f,'decimals':detail['inferred_decimals']}
                kept.append((min(j for j,q in entries),representative))
                removed+=len(entries)-1
                proofs.append({'concept':f['QName'],'context_refs':sorted({q['context_ref'] for j,q in entries}),
                    'source_values':sorted({q['value'] for j,q in entries}),
                    'source_fact_count':len(entries),'selected_context':f['context_ref'],
                    'selected_source_value':f['value'],'selected_accuracy':detail})
                continue
        # Inconsistent values, equal-precision conflicts, unknown accuracy and
        # opaque contexts remain blockers rather than being silently dropped.
        kept.extend(entries)
    if not removed:return parsed
    return {**parsed,'facts':[f for i,f in sorted(kept,key=lambda t:t[0])],
            'source_fact_normalization':{'removed_repeated_facts':removed,
                'compatible_source_groups':proofs,'different_aspects_merged':False,
                'original_instance_changed':False,'missing_values_inferred':False}}


def install(core):
    before=core.engine.raw.source_parse
    def source_parse(query):
        return normalize(before(query))
    core.engine.raw.source_parse=source_parse
