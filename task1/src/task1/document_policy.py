"""Execute the document/category matrix explicitly supplied in a question.

No real KYC rules or document catalog is used. Every category and accepted
purpose must come from the question; unknown or conflicting clauses decline
inside this capability, while the public mandatory-answer fallback remains.
"""
import re

IDENT=r'[a-z][a-z0-9_]*'

def solve_document_policy(question):
    if question['answer_spec'].get('type')!='enum':return None
    body=question['question'].split('\n\nAnswer format:')[0]
    if len(body)>16000:return None
    matrix={};accepts={};document=purpose=None;evidence=[];header=False
    try:
        for match in re.finditer(r'[^.;]+',body):
            raw=match[0];text=re.sub(r'\s+',' ',raw).strip().casefold()
            if not text:continue
            if re.fullmatch(r'apply only this fictional scenario-local document matrix(?:, not current law or general kyc guidance)?',text):
                if header:raise ValueError('duplicate scope')
                header=True;continue
            m=re.fullmatch(r'the submitted document is ('+IDENT+')',text)
            if m:
                if document is not None:raise ValueError('duplicate document')
                document=m[1];continue
            m=re.fullmatch(r'the requested use is ('+IDENT+')',text)
            if m:
                if purpose is not None:raise ValueError('duplicate purpose')
                purpose=m[1];continue
            m=re.fullmatch(r'the identifiers? (.+) (?:are|is) ('+IDENT+')',text)
            if m:
                names=re.split(r',\s*(?:and\s+)?|\s+and\s+',m[1])
                if not names or len(names)>64:raise ValueError('document list bound')
                for name in names:
                    if not re.fullmatch(IDENT,name) or name in matrix:raise ValueError('invalid or conflicting matrix entry')
                    matrix[name]=m[2]
                evidence.append({'source':raw,'start':match.start(),'end':match.end(),'kind':'category_assignment'});continue
            m=re.fullmatch(r'the purpose ('+IDENT+') accepts (.+)',text)
            if m:
                categories=re.split(r'\s+or\s+|,\s*(?:or\s+)?',m[2])
                if m[1] in accepts or not categories or len(categories)>32 or any(not re.fullmatch(IDENT,c) for c in categories):raise ValueError('invalid acceptance relation')
                accepts[m[1]]=set(categories);evidence.append({'source':raw,'start':match.start(),'end':match.end(),'kind':'acceptance_relation'});continue
            if text=='classify the document category and determine whether it is valid for the requested use':continue
            raise ValueError('unsupported policy clause')
        if not header or document not in matrix or purpose not in accepts or len(matrix)>128:return None
        categories=set(matrix.values())
        if any(not accepted<=categories for accepted in accepts.values()):return None
        category=matrix[document];valid=category in accepts[purpose];final='true' if valid else 'false'
        if final not in question['answer_spec']['allowed_values']:return None
        steps=[]
        for slot in question['trace_spec']['slots']:
            description=re.sub(r'\s+',' ',slot['description']).strip().rstrip('.').casefold()
            if description!='report the scenario-local document category':return None
            spec=slot['result_spec']
            if spec['type']!='enum' or category not in spec['allowed_values']:return None
            steps.append({'slot_id':slot['slot_id'],'value':category})
        prediction={'schema_version':'finreason.task1.prediction/1.0.0','dataset_version':question['dataset_version'],'case_id':question['case_id'],'final_answer':{'value':final},'steps':steps}
        return prediction,{'strategy':'explicit_document_matrix','document':document,'purpose':purpose,'category':category,'accepted_categories':sorted(accepts[purpose]),'source_evidence':evidence,'external_catalog_used':False}
    except (ValueError,KeyError,TypeError):return None
