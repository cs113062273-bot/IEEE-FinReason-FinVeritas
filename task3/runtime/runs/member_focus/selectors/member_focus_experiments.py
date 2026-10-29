"""Opt-in DQC0015 focus experiments: legal secondary taxonomy members.

No case IDs, entity IDs, dates, numeric constants, query hashes, or history are
used to select a value. These member preferences are research hypotheses; Xule
does not itself prefer State/local or OPEB to the other legal focus.
"""
import sys,re
from pathlib import Path
from decimal import Decimal
from collections import defaultdict,deque
from lxml import etree
W=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(W/'runs/calculation_semantics'))
from helpers import raw
LINK='http://www.xbrl.org/2003/linkbase';XL='http://www.w3.org/1999/xlink';XDT='http://xbrl.org/2005/xbrldt'
MODES={
 'state_local':('AccruedIncomeTaxesCurrent','IncomeTaxAuthorityAxis','StateAndLocalJurisdictionMember'),
 'opeb':('DefinedBenefitPlanAssumptionsUsedCalculatingBenefitObligationDiscountRate','RetirementPlanTypeAxis','OtherPostretirementBenefitPlansDefinedBenefitMember')}

def lname(q):return q.rsplit('}',1)[-1]

def drs_paths(p,axis,member):
 from source_financial_semantics import locators
 root=etree.fromstring(p['parts']['Definition linkbase document'].strip().encode())
 edges=[];groups=defaultdict(list)
 ignored={'{'+XL+'}'+s for s in ['from','to','type','title','show','actuate']}
 ignored|={'priority','use','order'}
 for link in root.findall('{'+LINK+'}definitionLink'):
  role=link.get('{'+XL+'}role');loc=locators(p,p['parts'],link)
  for n in link.findall('{'+LINK+'}definitionArc'):
   a,b=loc.get(n.get('{'+XL+'}from')),loc.get(n.get('{'+XL+'}to'))
   if not a or not b:continue
   relationship=n.get('{'+XL+'}arcrole','')
   if relationship not in {'http://xbrl.org/int/dim/arcrole/dimension-domain','http://xbrl.org/int/dim/arcrole/domain-member'}:continue
   attributes={k:v for k,v in n.attrib.items() if k not in ignored}
   attributes['{'+XDT+'}usable']='false' if n.get('{'+XDT+'}usable') in {'false','0'} else 'true'
   equivalence=tuple(sorted(attributes.items()))
   groups[(role,relationship,a,b,equivalence)].append(n)
 for (role,relationship,a,b,_),nodes in groups.items():
  top=max(int(n.get('priority','0')) for n in nodes)
  active=[n for n in nodes if int(n.get('priority','0'))==top]
  if any(n.get('use')=='prohibited' for n in active):continue
  n=active[0]
  edges.append({'role':role,'arcrole':relationship.rsplit('/',1)[-1],'from':a,'to':b,'next_role':n.get('{'+XDT+'}targetRole') or role,'usable':n.get('{'+XDT+'}usable') not in {'false','0'},'raw_xml':etree.tostring(n,encoding='unicode')})
 # A false membership for this axis's effective domain excludes that target
 # even if another domain path is usable. It never excludes descendants.
 blocked_by_role=defaultdict(set)
 for e in edges:
  if e['from']!=axis or e['arcrole']!='dimension-domain':continue
  blocked=blocked_by_role[e['role']]
  if not e['usable']:blocked.add(e['to'])
  pending=[(e['to'],e['next_role'])];seen=set()
  while pending:
   node,role=pending.pop()
   if (node,role) in seen:continue
   seen.add((node,role))
   for d in edges:
    if d['role']==role and d['from']==node and d['arcrole']=='domain-member':
     if not d['usable']:blocked.add(d['to'])
     pending.append((d['to'],d['next_role']))
 out=[]
 for e in edges:
  if e['from']!=axis or e['arcrole']!='dimension-domain':continue
  if member in blocked_by_role[e['role']]:continue
  todo=deque([(e['to'],e['next_role'],[e])]);seen=set()
  while todo:
   node,role,path=todo.popleft()
   if (node,role) in seen:continue
   seen.add((node,role))
   if node==member and path[-1]['usable']:out.append(path);continue
   for d in edges:
    if d['role']==role and d['from']==node and d['arcrole']=='domain-member':todo.append((d['to'],d['next_role'],path+[d]))
 return out

def select(parsed,mode):
 concept,axis,member=MODES[mode];target=parsed['target']
 if lname(target)!=concept or not re.fullmatch(r'\{http://fasb.org/us-gaap/20\d\d\}'+concept,target):return None
 yr=re.search(r'/([0-9]{4})}',target).group(1);ns='{http://fasb.org/us-gaap/'+yr+'}'
 eligible=[]
 for f in parsed['facts']:
  if f['QName']!=target or not f['asked_period'] or Decimal(f['value'])>=0:continue
  if raw.eligibility_0015(f,parsed['parts'],raw.exclusions())['subset_eligible'] is not True:continue
  dims=f['context']['dimensions']
  if len(dims)!=1 or dims[0][0]!=ns+axis or dims[0][2]!=ns+member or dims[0][1]!='explicit':continue
  paths=drs_paths(parsed,ns+axis,ns+member)
  if not paths:continue
  if concept=='AccruedIncomeTaxesCurrent' and f['unit_signature']!=(('{http://www.xbrl.org/2003/iso4217}USD',),()):continue
  if concept.endswith('DiscountRate') and f['unit_signature']!=(('{http://www.xbrl.org/2003/instance}pure',),()):continue
  eligible.append((f,paths))
 values={Decimal(f['value']) for f,pp in eligible}
 if len(values)!=1:return None
 f,paths=eligible[0]
 return {'new':{'extracted_value':f['value'],'calculated_value':str(abs(Decimal(f['value'])))},'fact':f,'DRS_paths':paths,'mode':mode,'question_focus_proved':False,'hypothesis':'Prefer specified legal secondary member over other eligible member; generic question omits a member locator.','calculation_basis':'original DQC0015 nonnegative sign repair; supplied calculation linkbase has no arcs'}

