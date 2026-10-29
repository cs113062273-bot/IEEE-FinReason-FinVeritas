"""Fresh lxml DRS/fact join; no old 0117 adapter selections imported.

Original 10093 monetary member sum with an already bound one-axis focus.
Notes-overlap applicability is reported, never silently overridden.
"""
from collections import defaultdict
from decimal import Decimal
from lxml import etree as E
from helpers import *
X='http://www.w3.org/1999/xlink';L='http://www.xbrl.org/2003/linkbase';DT='http://xbrl.org/2005/xbrldt';DI='http://xbrl.org/2006/xbrldi';XI='http://www.xbrl.org/2003/instance'
def xml(s):return E.fromstring(s.strip().encode(),E.XMLParser(resolve_entities=False,no_network=True,huge_tree=True))
def expand(s,ns):
    a,sep,b=s.partition(':');return '{'+ns[a if sep else None]+'}'+(b if sep else a)
def drs(parts):
    schema=xml(parts['Schema document']);inst=xml(parts['Instance document']);ns={**schema.nsmap,**inst.nsmap};defs=xml(parts['Definition linkbase document']);roles={};arcs=[]
    for r in schema.iter('{'+L+'}roleType'):
        desc=r.find('{'+L+'}definition');roles[r.get('roleURI')]=desc.text if desc is not None else ''
    for link in defs.iter('{'+L+'}definitionLink'):
        role=link.get('{'+X+'}role');locs={}
        for n in link.findall('{'+L+'}loc'):
            prefix,sep,name=n.get('{'+X+'}href','').split('#')[-1].partition('_')
            if sep and prefix in ns:locs[n.get('{'+X+'}label')]='{'+ns[prefix]+'}'+name
        for n in link.findall('{'+L+'}definitionArc'):
            a,b=locs.get(n.get('{'+X+'}from')),locs.get(n.get('{'+X+'}to'))
            if a and b:
                arcs.append({'role':role,'kind':n.get('{'+X+'}arcrole','').split('/')[-1],'parent':a,'child':b,'next_role':n.get('{'+DT+'}targetRole',role),'usable':n.get('{'+DT+'}usable','true') not in ['false','0'],'closed':n.get('{'+DT+'}closed') in ['true','1'],'use':n.get('use','optional'),'priority':int(n.get('priority','0')),'xml':E.tostring(n,encoding='unicode')})
    effective=[];groups=defaultdict(list)
    for a in arcs:groups[(a['role'],a['kind'],a['parent'],a['child'])].append(a)
    for aa in groups.values():
        top=max(a['priority'] for a in aa);active=[a for a in aa if a['priority']==top]
        if any(a['use']=='prohibited' for a in active):continue
        effective.append(active[0])
    graph=defaultdict(list)
    for a in effective:graph[(a['role'],a['kind'],a['parent'])].append(a)
    def walk(role,node,kind,seen=frozenset()):
        if (role,node,kind) in seen:return {}
        result={node:[]}
        for arc in graph[(role,kind,node)]:
            for k,path in walk(arc['next_role'],arc['child'],kind,seen|{(role,node,kind)}).items():result.setdefault(k,[arc]+path)
        return result
    def unusable_members(role,node,seen=frozenset()):
        # Usability excludes a member, never the descendant traversal.
        if (role,node) in seen:return set()
        blocked=set()
        for arc in graph[(role,'domain-member',node)]:
            if not arc['usable']:blocked.add(arc['child'])
            blocked|=unusable_members(arc['next_role'],arc['child'],seen|{(role,node)})
        return blocked
    cubes=[]
    for a in effective:
        if a['kind']!='all':continue
        axes={}
        for b in graph[(a['next_role'],'hypercube-dimension',a['child'])]:
            members={};domains=set();blocked=set()
            for c in graph[(b['next_role'],'dimension-domain',b['child'])]:
                domains.add(c['child'])
                if not c['usable']:blocked.add(c['child'])
                blocked|=unusable_members(c['next_role'],c['child'])
                for m,path in walk(c['next_role'],c['child'],'domain-member').items():members.setdefault(m,[b,c]+path)
            members={m:path for m,path in members.items() if m not in blocked}
            defaults={c['child'] for c in effective if c['kind']=='dimension-default' and c['parent']==b['child']}
            axes[b['child']]={'members':members,'domains':domains,'defaults':defaults}
        cubes.append({'role':a['role'],'description':roles.get(a['role'],''),'cube':a['child'],'primary':walk(a['role'],a['parent'],'domain-member'),'axes':axes,'closed':a['closed'],'has_arc':a})
    return cubes
def statement(c):
    role=c['role'].lower();description=c['description']
    banned=['parenthetical','equity','deficit','stockholders','capital','investment','changes','shareholder','convertible','preferred','temporaryequity','redeemable','netproceedsfromallsources','membersinterest']
    return '- Statement -' in description and not any(x in role for x in banned)
def inside(f,c):
    if f['QName'] not in c['primary']:return False
    dims=ds(f)
    if c['closed'] and set(dims)-set(c['axes']):return False
    for axis,spec in c['axes'].items():
        member=dims.get(axis)
        if member is None:
            if len(spec['defaults'])!=1:return False
            member=next(iter(spec['defaults']))
        if member not in spec['members']:return False
    return True
def metadata(p):
    from normalized_metadata import metadata_or_supplied
    return metadata_or_supplied(p)
def bridged_focus(p):
    from normalized_metadata import catalog
    from source_financial_semantics import bridged_focus as source_bridges
    parts,provenance=catalog().bind(p,labels=True)
    try:
        return source_bridges(p,parts if parts is not None else p['parts'])
    except (E.XMLSyntaxError,KeyError):
        return []
def sums(p,focus,parts):
    from task3.exact_arithmetic import sum_values as exact_sum
    cc=drs(parts);ff=prev.fs(p);base=ds(focus);result=[]
    if len(base)!=1:return []
    for cube in cc:
        if not statement(cube) or not inside(focus,cube):continue
        for axis,spec in cube['axes'].items():
            if axis in base:continue
            candidates=[f for f in ff if set(ds(f))==set(base)|{axis} and all(ds(f).get(a)==m for a,m in base.items()) and frame(f,axis)==frame(focus)]
            included=[f for f in candidates if inside(f,cube)];excluded=[f for f in candidates if not inside(f,cube)]
            notes=[f for f in included if any('- Disclosure -' in c['description'] and set(ds(f))<=set(c['axes']) and inside(f,c) for c in cc)]
            result.append({'role':cube['role'],'description':cube['description'],'axis':axis,'fixed_dimensions':base,'focus':focus,'included_facts':included,'excluded_source_facts':excluded,'member_paths':{ds(f)[axis]:spec['members'][ds(f)[axis]] for f in included},'calculated':str(exact_sum(map(val,included))) if included else None,'empty_sum_not_accepted_as_zero':not bool(included),'notes_max':str(max(map(val,notes))) if notes else None,'notes_overlap_guard_passed':not notes or max(map(val,notes))>val(focus),'formula':'DQC.US.0117.10093 member_sums = sum(member_facts); weights all +1','ancestor_suppression':False,'statement_DRS_membership_independently_checked':True})
    return result
def main():
    row=next(r for r in rows(ROOT/'data/raw/task3/development_inputs.jsonl') if r['id']=='DEV3_000198');p=raw.source_parse(row['query']);focus=next(f for f in prev.fs(p) if f['context_ref']=='c-19');parts,provenance=metadata(p)
    original=sums(p,focus,p['parts']);full=sums(p,focus,parts)
    calc=xml(p['parts']['Calculation linkbase document']);weighted=list(calc.iter('{'+L+'}calculationArc'))
    result={'id':row['id'],'known_Q1':'610517000','known_wrong_Q2':'610517000','original_rule_sha256':sha(ROOT/'resources/task3_dqc0117/DQC_0117.xule'),'query_sha256':hashlib.sha256(row['query'].encode()).hexdigest(),'supplied_calculation_arc_count':len(weighted),'supplied_scope':original,'original_public_full_DRS_scope':full,'external_metadata':provenance,'all_customer_sum':str(sum(val(f) for f in prev.fs(p) if len(ds(f))==2 and any(local(a)=='MajorCustomersAxis' for a in ds(f)) and any(local(m)=='AssetManagement1Member' for m in ds(f).values()))),'supported_nonempty_statement_sums':sorted({r['calculated'] for r in full if r['calculated'] is not None}),'full_original_assertion_applicable':False,'Q2_gold_proved':False}
    dump(O/'198_independent_calculations.json',result);(O/'198_original_query.txt').write_text(row['query'],encoding='utf-8');print(json.dumps({k:v for k,v in result.items() if k not in ['supplied_scope','original_public_full_DRS_scope']}),flush=True)
if __name__=='__main__':main()
