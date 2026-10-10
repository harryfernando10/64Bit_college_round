import json
from pathlib import Path
from fastapi.testclient import TestClient
from backend.main import app
client = TestClient(app)
ROOT = Path(__file__).resolve().parents[1]
def test_health():
 r=client.get('/api/health'); assert r.status_code==200 and r.json()['status']=='ok'
def test_scenario_api_and_response_contract():
 s=client.get('/api/scenarios').json()[0]; r=client.post('/api/audit',json={'answer':s['answer'],'sources':s['sources'],'scenario_id':s['scenario_id']}); assert r.status_code==200
 data=r.json(); assert data['execution_mode']=='FIXTURE'; assert data['summary']['total_claims']==len(data['claims'])
 expected={'SUPPORTED':'supported','CONTRADICTED':'contradicted','INSUFFICIENT_EVIDENCE':'insufficient_evidence','AMBIGUOUS':'ambiguous'}
 for verdict,key in expected.items(): assert data['summary'][key]==sum(c['verdict']==verdict for c in data['claims'])
 for c in data['claims']:
  assert data['answer'][c['start_offset']:c['end_offset']]==c['claim_text']
  for ref in c['evidence']:
   source=next(source for source in data['sources'] if source['source_id']==ref['source_id'])
   assert source['text'][ref['start_offset']:ref['end_offset']]==ref['quote']
def test_invalid_request_returns_readable_422():
 r=client.post('/api/audit',json={'answer':'','sources':[]}); assert r.status_code==422 and 'detail' in r.json()

def test_whitespace_only_answer_and_source_are_rejected():
 assert client.post('/api/audit',json={'answer':'   ','sources':[{'source_id':'s1','title':'Source','text':'Text'}]}).status_code==422
 assert client.post('/api/audit',json={'answer':'Claim.','sources':[{'source_id':'s1','title':'   ','text':'Text'}]}).status_code==422
 assert client.post('/api/audit',json={'answer':'Claim.','sources':[{'source_id':'s1','title':'Source','text':'   '}]}).status_code==422

def test_modified_fixture_input_is_insufficient_and_echoes_all_sources():
 s=client.get('/api/scenarios').json()[0]
 sources=[*s['sources'],{'source_id':'extra-source','title':'Additional source','text':'A separate note.'}]
 response=client.post('/api/audit',json={'answer':s['answer']+' Edited.','sources':sources,'scenario_id':s['scenario_id']})
 assert response.status_code==200
 data=response.json()
 assert data['sources']==sources
 assert all(c['verdict']=='INSUFFICIENT_EVIDENCE' for c in data['claims'])
 assert data['summary']['insufficient_evidence']==len(data['claims'])
 assert data['summary']['total_claims']==len(data['claims'])

def test_duplicate_source_ids_are_rejected():
 source={'source_id':'same','title':'Source','text':'Text'}
 assert client.post('/api/audit',json={'answer':'Claim.','sources':[source,source]}).status_code==422
def test_fixtures_have_consistent_claim_and_evidence_spans():
 files=list((ROOT/'data/scenarios').glob('*.json')); assert len(files)>=3
 for f in files:
  d=json.loads(f.read_text(encoding='utf8')); assert len(d['claims'])==len(d['expected_claims'])
  for c,e in zip(d['claims'],d['expected_claims'],strict=True):
   assert d['answer'][c['start_offset']:c['end_offset']]==c['claim_text']
   assert (c['claim_id'],c['verdict'])==(e['claim_id'],e['verdict'])
   assert (c['evidence'][0]['sentence_id'] if c['evidence'] else None)==e['evidence_sentence_id']
   assert c['note']==e['rationale']
   for ref in c['evidence']:
    src=next(x for x in d['sources'] if x['source_id']==ref['source_id']); assert src['text'][ref['start_offset']:ref['end_offset']]==ref['quote']
    sentences=__import__('backend.service',fromlist=['split_sentences']).split_sentences(src['text'],src['source_id'])
    sentence=next(item for item in sentences if item.sentence_id==ref['sentence_id'])
    assert sentence.start_offset<=ref['start_offset']<ref['end_offset']<=sentence.end_offset
def test_unknown_evidence_source_rejected():
 import pytest
 from backend.models import AuditResponse
 d=json.loads(next((ROOT/'data/scenarios').glob('*.json')).read_text(encoding='utf8')); c=d['claims'][0]
 payload={'audit_id':'x','execution_mode':'FIXTURE','answer':d['answer'],'sources':d['sources'],'source_sentences':{d['sources'][0]['source_id']:[]},'claims':[{**c,'evidence':[{**c['evidence'][0],'source_id':'unknown'}]}],'summary':{'supported':1,'contradicted':0,'insufficient_evidence':0,'ambiguous':0,'total_claims':1},'warnings':[]}
 with pytest.raises(ValueError,match='unknown evidence source_id'): AuditResponse.model_validate(payload)


def test_offsets_use_python_unicode_code_points():
 answer='🌱 An unsupported claim.'
 source={'source_id':'unicode-source','title':'Unicode source','text':'🌱 Background note.'}
 response=client.post('/api/audit',json={'answer':answer,'sources':[source]})
 assert response.status_code==200
 claim=response.json()['claims'][0]
 assert answer[claim['start_offset']:claim['end_offset']]==claim['claim_text']
 assert claim['end_offset']==len(answer)


def test_invalid_quote_is_rejected_even_when_source_id_exists():
 from backend.models import AuditResponse
 import pytest
 s=client.get('/api/scenarios').json()[0]
 payload=client.post('/api/audit',json={'answer':s['answer'],'sources':s['sources'],'scenario_id':s['scenario_id']}).json()
 payload['claims'][0]['evidence'][0]['quote']='not the source quote'
 with pytest.raises(ValueError,match='evidence quote offsets'): AuditResponse.model_validate(payload)
