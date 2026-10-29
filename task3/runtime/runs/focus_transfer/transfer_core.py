"""Replace only the two named selector slots; preserve the original chain."""
from decimal import Decimal


def install(core):
    import source_rules_v2
    import source_rules_v4
    from source_focus import legal_tax_entity, continuing_revolver
    source_rules_v2.kansas = legal_tax_entity
    source_rules_v4.flourish = continuing_revolver

    def infer(query, *, output_id, exclusions):
        from task3.period_semantics import normalize_query
        query, normalization = normalize_query(query)
        before = len(core.native_records)
        value, events, c8, programs = core.engine.infer(query, None, exclusions, output_id=output_id)
        parsed = core.engine.raw.source_parse(query)
        proposal = core.apply(parsed)
        if proposal:
            incumbents = [f for f in core.engine.cn.prev.fs(parsed)
                          if Decimal(f['value']) == Decimal(value['extracted_value']) and Decimal(f['value']) < 0
                          and core.engine.raw.eligibility_0015(f, parsed['parts'], exclusions)['subset_eligible'] is True]
            blocked = (proposal.get('retain_eligible_negative_incumbent') and incumbents
                       and Decimal(proposal['new']['extracted_value']) != Decimal(value['extracted_value']))
            if blocked:
                events.append({'rule': 'retain_eligible_incumbent_over_ambiguous_single_owner', 'changed': False,
                               'incumbent_source_facts': incumbents, 'declined_proposal': proposal})
            else:
                updated = {**value, **proposal['new']}
                events.append({'rule': proposal.get('rule', proposal.get('mode')), 'changed': not core.engine.same(value, updated),
                               'source_evidence': proposal})
                value = updated
        value = {k:value[k] for k in ('id', 'extracted_value', 'calculated_value')}
        assert value['id'] == output_id
        return value, {'period_normalization': normalization, 'events': events, 'programs': programs,
                       'c8_value': c8, 'fresh_native': core.native_records[before:]}, parsed
    core.infer = infer
