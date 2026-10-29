"""Optional strict supplied-DRS DQC0117 adapter; R4/R5 remain unchanged.

Public DQC0117 9574/10093 selections plus explicit cube/default witnesses.
This certifies a supplied-document subset, not a complete imported DTS.
"""
from collections import defaultdict
from decimal import Decimal,localcontext
import hashlib
import re

from task3.dqc_statement_sum import _document,_locators
from task3.round4_dimensional import statement_role_eligibility,RULE_SHA,CONSTANT_SHA
from task3.round6_dqc0126 import alignment,indexed_facts,_round,verify_sources,ROOT
from task3.round4_statement import decimals_rank
from task3.dimensional_sum import AXES,DIM,XBRLDT
from task3.parser import format_number,split_sections
from task3.xml_core import LINK,XLINK,XBRLI,XBRLDI,attr,tag_parts,expanded,_safe_xml
from task3.exact_arithmetic import add as exact_add,product as exact_product,sum_values as exact_sum


def effective_drs(query,filing):
    root=_document(query,filing,'Definition linkbase document')
    graph=defaultdict(list);descriptions={};warnings=[];groups=defaultdict(list)
    digest=hashlib.sha256(split_sections(query).get('Definition linkbase document','').encode()).hexdigest()
    if root is None:return graph,descriptions,['definition document unavailable'],digest
    ignored={f'{{{XLINK}}}{s}' for s in ('from','to','type','title','show','actuate')}
    ignored|={'priority','use','order'}
    for link in root.iter('{'+LINK+'}definitionLink'):
        role=attr(link,'role',XLINK);locs=_locators(link,filing)
        descriptions[role]=filing.role_definitions.get(role) or attr(link,'title',XLINK)
        for arc in link:
            if tag_parts(arc)!=(LINK,'definitionArc'):continue
            relationship=attr(arc,'arcrole',XLINK)
            if not relationship.startswith(DIM):continue
            parent,child=locs.get(attr(arc,'from',XLINK)),locs.get(attr(arc,'to',XLINK))
            try:priority=int(attr(arc,'priority') or '0')
            except ValueError:warnings.append('invalid definition priority:'+role);continue
            if not parent or not child:warnings.append('unresolved definition locator:'+role);continue
            if attr(arc,'use') not in {'','optional','prohibited'}:warnings.append('unsupported definition use:'+role);continue
            equivalence=tuple(sorted((k,v) for k,v in arc.attrib.items() if k not in ignored))
            node={'role':role,'kind':relationship[len(DIM):],'parent':parent,'child':child,
                  'next_role':attr(arc,'targetRole',XBRLDT) or role,'usable':attr(arc,'usable',XBRLDT) not in {'false','0'},
                  'closed':attr(arc,'closed',XBRLDT) in {'true','1'},'contextElement':attr(arc,'contextElement',XBRLDT),
                  'priority':priority,'prohibited':attr(arc,'use')=='prohibited','source_line':arc.sourceline,
                  'definition_sha256':digest}
            groups[(role,node['kind'],parent,child,equivalence)].append(node)
    for arcs in groups.values():
        priority=max(a['priority'] for a in arcs);highest=[a for a in arcs if a['priority']==priority]
        if any(a['prohibited'] for a in highest):continue
        # Equivalent optional arcs describe one effective relationship.
        arc=highest[0];graph[(arc['role'],arc['kind'],arc['parent'])].append(arc)
    return graph,descriptions,warnings,digest


def _walk(graph,role,node,kind='domain-member',active=frozenset()):
    state=(role,node,kind)
    if state in active:return {node},[],['DRS cycle']
    nodes={node};arcs=[];errors=[]
    for arc in graph[(role,kind,node)]:
        children,paths,failures=_walk(graph,arc['next_role'],arc['child'],kind,active|{state})
        nodes|=children;arcs.extend([arc,*paths]);errors.extend(failures)
    return nodes,arcs,errors


def cubes(query,filing):
    graph,descriptions,warnings,digest=effective_drs(query,filing)
    instance=_safe_xml(split_sections(query).get('Instance document',''),'Instance document',filing.namespaces,[],allow_complete_prefix=True)
    locations={}
    if instance is not None:
        for element in instance.iter('{'+XBRLI+'}context'):
            places={}
            for child in element.iter():
                if tag_parts(child) not in {(XBRLDI,'explicitMember'),(XBRLDI,'typedMember')}:continue
                axis=expanded(attr(child,'dimension'),child.nsmap)
                containers=[tag_parts(p)[1] for p in child.iterancestors() if tag_parts(p) in {(XBRLI,'segment'),(XBRLI,'scenario')}]
                if axis and len(containers)==1:places[axis]=containers[0]
            locations[attr(element,'id')]=places
    defaults=defaultdict(set)
    for (role,kind,axis),arcs in list(graph.items()):
        if kind=='dimension-default':defaults[axis].update(a['child'] for a in arcs)
    result=[]
    bases=defaultdict(list)
    for (role,kind,primary),arcs in list(graph.items()):
        if kind in {'all','notAll'}:
            for arc in arcs:bases[(role,arc['child'])].append(arc)
    for (role,cube),has_arcs in bases.items():
        primary=set();negative=set();axes={};paths=[];errors=list(warnings);closed=True;context_elements=set()
        for has in has_arcs:
            members,prims,failures=_walk(graph,has['role'],has['parent'])
            (primary if has['kind']=='all' else negative).update(members)
            paths.extend([has,*prims]);errors.extend(failures);closed &= has['closed']
            context_elements.add(has['contextElement'])
            for axis_arc in graph[(has['next_role'],'hypercube-dimension',cube)]:
                axis=axis_arc['child'];paths.append(axis_arc)
                spec=axes.setdefault(axis,{'domains':set(),'members':set(),'unusable':set(),'ancestors':defaultdict(set)})
                domain_arcs=graph[(axis_arc['next_role'],'dimension-domain',axis)]
                if not domain_arcs:errors.append('dimension domain unavailable:'+axis)
                for domain_arc in domain_arcs:
                    domain=domain_arc['child'];spec['domains'].add(domain);paths.append(domain_arc)
                    members,member_arcs,failures=_walk(graph,domain_arc['next_role'],domain)
                    spec['members']|=members;paths.extend(member_arcs);errors.extend(failures)
                    if not domain_arc['usable']:spec['unusable'].add(domain)
                    for arc in member_arcs:
                        spec['ancestors'][arc['child']].add(arc['parent'])
                        if not arc['usable']:spec['unusable'].add(arc['child'])
                for member in spec['members']:
                    ancestors=set();pending=list(spec['ancestors'][member])
                    while pending:
                        ancestor=pending.pop()
                        if ancestor in ancestors:continue
                        ancestors.add(ancestor);pending.extend(spec['ancestors'][ancestor]-ancestors)
                    spec['ancestors'][member]=ancestors
                values=defaults[axis]
                spec['default']=next(iter(values)) if len(values)==1 else None
                spec['default_conflict']=len(values)>1
        if len(context_elements)!=1 or next(iter(context_elements)) not in {'segment','scenario'}:
            errors.append('cube contextElement not uniquely supplied')
        result.append({'role':role,'cube':cube,'description':descriptions.get(role,''),
                       'primary':primary-negative,'axes':axes,'closed':closed,'arcs':paths,
                       'contextElement':next(iter(context_elements)) if len(context_elements)==1 else None,
                       'locations':locations,'errors':sorted(set(errors)),'source_sha256':digest})
    return result


def membership(filing,fact,cube):
    context=filing.contexts.get(fact.context)
    if context is None or fact.concept not in cube['primary']:return False,['concept outside cube primary scope']
    dims=dict(context.dimensions);unknown=[]
    if cube['closed'] and set(dims)-set(cube['axes']):return False,['extra dimension outside closed cube']
    for axis,spec in cube['axes'].items():
        if spec['default_conflict']:return False,['conflicting dimension default']
        member=dims.get(axis)
        if member is None:
            member=spec['default']
            if member is None:unknown.append('missing supplied default:'+axis);continue
        elif cube['locations'].get(fact.context,{}).get(axis)!=cube['contextElement']:
            return False,['reported dimension contextElement mismatch or unbound literal location']
        if not isinstance(member,str):return False,['typed dimension outside this explicit-DRS subset']
        if member not in spec['members'] or member in spec['unusable']:return False,['unusable or outside-domain member:'+str(member)]
    return (None,unknown) if unknown else (not cube['errors'],cube['errors'])


def _cube_facts(filing,facts,cube,parent,axes_filter):
    frame=alignment(filing,parent,include_dimensions=False);matching=[];unknown=[]
    for fact in facts:
        if fact.concept!=parent.concept or alignment(filing,fact,include_dimensions=False)!=frame:continue
        dims=dict(filing.contexts[fact.context].dimensions)
        if not axes_filter(dims):continue
        inside,reason=membership(filing,fact,cube)
        if inside:matching.append(fact)
        elif inside is None:unknown.append({'fact_index':fact.index,'reasons':reason})
    return matching,unknown


def _tolerance_violation(parent,total,selected):
    decimals=[decimals_rank(f.decimals) for f in selected]
    if not decimals or any(d is None for d in decimals):return None,{'reason':'unknown member decimals'}
    minimum=min(decimals);minimum=min(minimum,Decimal(5))
    target_decimals=decimals_rank(parent.decimals)
    if target_decimals is None or target_decimals.is_infinite():target_decimals=minimum
    precision=min(target_decimals,minimum)
    difference=exact_add(_round(total,precision),_round(parent.value,precision).copy_negate()).copy_abs()
    threshold=exact_product(Decimal((0,(1,),-int(precision))),Decimal(2))
    return difference>threshold,{'precision':str(precision),'rounded_difference':format_number(difference),
                                 'tolerance':format_number(threshold),'source_function':'tolerance_for_decimals_comp'}


def candidates(query,filing,parent,*,duplicate_policy='xule_default',allow_inferred_statement=False):
    """DQC0117 per-parent candidates with literal 9574/10093 axis selections."""
    verify_sources()
    if hashlib.sha256((ROOT/'resources/task3_dqc0117/DQC_0117.xule').read_bytes()).hexdigest()!=RULE_SHA:
        raise ValueError('Pinned DQC0117 generic source changed')
    context=filing.contexts.get(parent.context);unit=filing.units.get(parent.unit)
    if (context is None or unit is None or unit.denominator or len(unit.numerator)!=1
            or not unit.numerator[0].startswith('{http://www.xbrl.org/2003/iso4217}')):return []
    base=dict(context.dimensions)
    if len(base)>1:return []
    if base and next(iter(base)).partition('}')[2] not in AXES:return []
    source_cubes=cubes(query,filing);facts,index_proof=indexed_facts(filing,duplicate_policy)
    output=[]
    for cube in source_cubes:
        role_allowed,role_reason=statement_role_eligibility(cube['role'],cube['description'],cube['cube'],allow_inferred_uri=allow_inferred_statement)
        if not role_allowed:continue
        if base and not set(base)<=set(cube['axes']):continue
        parent_inside,parent_reason=membership(filing,parent,cube)
        if parent.concept not in cube['primary']:continue
        for axis,spec in cube['axes'].items():
            if axis in base:continue
            if not base and axis.partition('}')[2] not in AXES:continue
            if base and axis.partition('}')[2]=='LegalEntityAxis':continue
            rule='DQC.US.0117.10093' if base else 'DQC.US.0117.9574'
            blockers=list(cube['errors'])
            if parent.index not in {f.index for f in facts}:blockers.append('requested total removed by duplicate-indexing policy')
            if not parent_inside:blockers.extend(parent_reason)
            if not base and spec['default'] not in spec['domains']:blockers.append('9574 total is not at a supplied axis-domain default')
            allowed=set(base)|{axis}
            visible,unknown=_cube_facts(filing,facts,cube,parent,
                lambda d:axis in d and set(d)==allowed and all(d.get(a)==m for a,m in base.items()))
            if unknown:blockers.append('member cube membership unresolved')
            if base:
                # Source first(Dim2Dimensions) cannot be assumed when a single
                # supplied cube actually has several competing second axes.
                alternatives={a for fact in facts if fact.concept==parent.concept and
                    alignment(filing,fact,include_dimensions=False)==alignment(filing,parent,include_dimensions=False)
                    and membership(filing,fact,cube)[0] and len(filing.contexts[fact.context].dimensions)==2
                    and all(dict(filing.contexts[fact.context].dimensions).get(a)==m for a,m in base.items())
                    for a in dict(filing.contexts[fact.context].dimensions) if a not in base}
                if alternatives!={axis}:blockers.append('second-axis first(set) selection is ambiguous or absent')
            grouped=defaultdict(list)
            for fact in visible:grouped[dict(filing.contexts[fact.context].dimensions)[axis]].append(fact)
            if any(len({f.value for f in fs})>1 for fs in grouped.values()):blockers.append('conflicting reported member duplicates')
            selected=[];suppressed=[]
            for member,fs in grouped.items():
                # 10093 lacks the ancestor suppression used only in 9574.
                if not base and (spec['ancestors'][member]-spec['domains'])&set(grouped):suppressed.append(member);continue
                selected.append(min(fs,key=lambda f:f.index))
            if not selected:blockers.append('no nonnil member facts')
            # Covered-dims discovers deeper breakdowns, while the square
            # subtotal query requires exactly the explicitly filtered axes.
            deeper,unknown_deeper=_cube_facts(filing,facts,cube,parent,
                lambda d:axis in d and set(d)>allowed and all(d.get(a)==m for a,m in base.items()))
            if unknown_deeper:blockers.append('deeper-detail cube membership unresolved')
            for fact in deeper:
                member=dict(filing.contexts[fact.context].dimensions)[axis]
                if member not in grouped:blockers.append('deeper breakdown has no reported axis subtotal:'+str(member))
            notes=[];parenthetical=[];notes_unknown=[]
            for other in source_cubes:
                notes_cube='- Disclosure -' in other['description']
                paren_cube='- Statement -' in other['description'] and 'parenthetical' in other['role'].lower()
                if not notes_cube and not paren_cube:continue
                # Native @cube factsets only bind dimensions of that cube;
                # an open cube does not turn every extra context dimension
                # into a DRS axis for a wildcard query.
                if not allowed <= set(other['axes']):continue
                matched,undecided=_cube_facts(filing,facts,other,parent,
                    lambda d:axis in d and set(d)==allowed and all(d.get(a)==m for a,m in base.items()))
                if notes_cube:notes.extend(matched);notes_unknown.extend(undecided)
                if paren_cube and not base:parenthetical.extend(matched);notes_unknown.extend(undecided)
            if notes_unknown:blockers.append('notes/parenthetical cube applicability unresolved')
            notes_max=max((fact.value for fact in notes),default=None)
            if notes_max is not None and notes_max<=parent.value:blockers.append('notes overlap values do not exceed total')
            if parenthetical:blockers.append('9574 parenthetical overlap')
            total=exact_sum(fact.value for fact in selected)
            # This public 606 condition needs the broader cube/calculation
            # exception; it remains explicit instead of inventing a remainder.
            if not base and axis.partition('}')[2]=='ProductOrServiceAxis' and parent.concept.partition('}')[2] in {
                'RevenueFromContractWithCustomerExcludingAssessedTax','RevenueFromContractWithCustomerIncludingAssessedTax'}:
                blockers.append('606 revenue exception not fully certified by this subset')
            violation,tolerance=_tolerance_violation(parent,total,selected)
            if violation is None:blockers.append('tolerance comparison unresolved')
            applicable=not blockers
            output.append({'rule_family':'0117','rule':rule,'rule_subset':rule,'role':cube['role'],'cube':cube['cube'],
                'axis':axis,'fixed_dimensions':sorted(base.items()),'value':format_number(total),'parent':parent.evidence(filing),
                'statement_role_gate':role_reason,'statement_role_inferred':'inference' in role_reason,
                'applicable':applicable,'eligible':applicable,'violates':bool(violation) if applicable else False,
                'ambiguous':any('ambig' in b or 'conflict' in b for b in blockers),'blockers':sorted(set(blockers)),
                'cube_applicability_proven':bool(parent_inside) and not unknown and not cube['errors'],
                'contextElement':cube['contextElement'],'supplied_contextElement_alignment_checked':True,
                'source_dimension_default':spec['default'],'reported_members':[f.evidence(filing) for f in selected],
                'suppressed_descendants':sorted(suppressed),'ancestor_suppression_applied':not bool(base),
                'second_axis_eligible11_required':not bool(base),'deeper_details':len(deeper),
                'notes_max':format_number(notes_max) if notes_max is not None else None,
                'notes_fact_indexes':[f.index for f in notes],'notes_unknown':notes_unknown,
                'parenthetical_fact_indexes':[f.index for f in parenthetical],
                'tolerance':tolerance,'indexing':index_proof,'definition_arcs':cube['arcs'],
                'source_rule_sha256':RULE_SHA,'source_constant_sha256':CONSTANT_SHA,'definition_sha256':cube['source_sha256'],
                'full_DTS_Xule_implementation':False,'period_policy':'asked period; DEI document duration unproved',
                'missing_zero_fact_invented':False,'inverse_used':False,'accuracy_verified':False})
    return output
