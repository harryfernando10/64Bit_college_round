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

def test_modified_fixture_input_uses_baseline_and_echoes_all_sources():
 s=client.get('/api/scenarios').json()[0]
 sources=[*s['sources'],{'source_id':'extra-source','title':'Additional source','text':'A separate note.'}]
 response=client.post('/api/audit',json={'answer':s['answer']+' Edited.','sources':sources,'scenario_id':s['scenario_id']})
 assert response.status_code==200
 data=response.json()
 assert data['sources']==sources
 assert data['execution_mode']=='BASELINE'
 assert len(data['claims'])>=1
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

def test_source_driven_baseline_supported_contradicted_and_missing():
 source={'source_id':'note','title':'Note','text':'The garden trial ended after four weeks. Researchers counted 48 plants in the trial.'}
 answer='The garden trial ended after four weeks. Researchers counted 84 plants in the trial. The report lists the plant color.'
 data=client.post('/api/audit',json={'answer':answer,'sources':[source]}).json()
 assert data['execution_mode']=='BASELINE'
 assert [c['verdict'] for c in data['claims']]==['SUPPORTED','CONTRADICTED','INSUFFICIENT_EVIDENCE']
 for c in data['claims']:
  assert answer[c['start_offset']:c['end_offset']]==c['claim_text']
  for ref in c['evidence']:
   assert source['text'][ref['start_offset']:ref['end_offset']]==ref['quote']
 assert data['summary']['total_claims']==3
 expected_counts={'SUPPORTED':'supported','CONTRADICTED':'contradicted','INSUFFICIENT_EVIDENCE':'insufficient_evidence','AMBIGUOUS':'ambiguous'}
 for verdict,key in expected_counts.items():
  assert data['summary'][key]==sum(c['verdict']==verdict for c in data['claims'])

def test_baseline_unicode_multisource_and_negation():
 sources=[{'source_id':'first','title':'First','text':'🌿 The room is not open on Friday.'}, {'source_id':'second','title':'Second','text':'The room opens on Saturday.'}]
 data=client.post('/api/audit',json={'answer':'🌿 The room is open on Friday.','sources':sources}).json()
 claim=data['claims'][0]
 assert data['execution_mode']=='BASELINE' and claim['verdict']=='CONTRADICTED'
 assert claim['start_offset']==0 and claim['claim_text']==data['answer']
 assert claim['evidence'][0]['source_id']=='first'
 assert any(x['check_type']=='polarity' and x['status']=='MISMATCH' for x in claim['deterministic_checks'])

def test_baseline_conflicting_sources_are_ambiguous():
 sources=[{'source_id':'a','title':'A','text':'The room is open on Monday.'},{'source_id':'b','title':'B','text':'The room is not open on Monday.'}]
 data=client.post('/api/audit',json={'answer':'The room is open on Monday.','sources':sources}).json()
 assert data['claims'][0]['verdict']=='AMBIGUOUS'

def test_baseline_wrong_year_and_decimal_segmentation():
 from backend.service import split_sentences
 assert [s.text for s in split_sentences('The value is 3.14 cm. It was measured in 2024.','x')]==['The value is 3.14 cm.','It was measured in 2024.']
 source={'source_id':'s','title':'Report','text':'The review was completed in 2024.'}
 data=client.post('/api/audit',json={'answer':'The review was completed in 2025.','sources':[source]}).json()
 assert data['claims'][0]['verdict']=='CONTRADICTED'
 assert any(c['check_type']=='date' and c['status']=='MISMATCH' for c in data['claims'][0]['deterministic_checks'])

def test_unrelated_quantities_in_same_passage_do_not_create_contradiction():
 source={'source_id':'s','title':'Report','text':'The study enrolled 14 volunteers and assigned 12 tablets to staff.'}
 data=client.post('/api/audit',json={'answer':'The study enrolled 12 volunteers.','sources':[source]}).json()
 assert data['claims'][0]['verdict']=='INSUFFICIENT_EVIDENCE'
 assert not any(c['check_type']=='quantity_or_unit' and c['status']=='MISMATCH' for c in data['claims'][0]['deterministic_checks'])

def test_unrelated_single_quantities_with_shared_generic_words_do_not_compare():
 source={'source_id':'s','title':'Report','text':'The report recorded 14 items today.'}
 data=client.post('/api/audit',json={'answer':'The report recorded 12 items last year.','sources':[source]}).json()
 assert data['claims'][0]['verdict']=='INSUFFICIENT_EVIDENCE'
 assert not any(c['check_type']=='quantity_or_unit' and c['status']=='MISMATCH' for c in data['claims'][0]['deterministic_checks'])

def test_negation_scope_and_quotes_do_not_create_false_contradictions():
 answer='The room is open on Monday.'
 cases=[
  ('The room is open on Monday; parking is not available.', 'INSUFFICIENT_EVIDENCE'),
  ('"The room is not open on Monday," said a visitor.', 'INSUFFICIENT_EVIDENCE'),
  ('"The room is open on Monday."', 'INSUFFICIENT_EVIDENCE'),
  ('The room is not open on Monday.', 'CONTRADICTED'),
 ]
 for text, expected in cases:
  data=client.post('/api/audit',json={'answer':answer,'sources':[{'source_id':'s','title':'Notice','text':text}]}).json()
  assert data['claims'][0]['verdict']==expected

def test_paraphrased_or_irrelevant_evidence_does_not_prove_claim():
 cases=[
  ('The trial lasted four weeks.', 'The experiment continued for a month.'),
  ('The report describes tea imports.', 'A river bridge opened after repairs.'),
 ]
 for answer, source_text in cases:
  data=client.post('/api/audit',json={'answer':answer,'sources':[{'source_id':'s','title':'Source','text':source_text}]}).json()
  assert data['claims'][0]['verdict']=='INSUFFICIENT_EVIDENCE'
  if data['claims'][0]['evidence']:
   assert data['claims'][0]['note'].startswith('Relevant passages were retrieved')

def test_low_rank_conflict_in_another_document_is_considered():
 sources=[
  {'source_id':'primary','title':'Primary','text':'The room is open on Monday. The room is open on Monday morning.'},
  {'source_id':'conflict','title':'Conflict','text':'The room is not open on Monday.'},
 ]
 data=client.post('/api/audit',json={'answer':'The room is open on Monday.','sources':sources}).json()
 claim=data['claims'][0]
 assert claim['verdict']=='AMBIGUOUS'
 assert {e['source_id'] for e in claim['evidence']}=={'primary','conflict'}

def test_unrelated_dates_and_incompatible_units_are_not_compared():
 cases=[
  ('The meeting was on 2024.', 'The meeting was on 2025 and the report was filed in 2024.'),
  ('The pipe is 3 cm wide.', 'The pipe is 0.03 m wide.'),
 ]
 for answer, source_text in cases:
  data=client.post('/api/audit',json={'answer':answer,'sources':[{'source_id':'s','title':'Source','text':source_text}]}).json()
  assert data['claims'][0]['verdict']=='INSUFFICIENT_EVIDENCE'
  assert not any(x['status']=='MISMATCH' and x['check_type'] in {'date','quantity_or_unit'} for x in data['claims'][0]['deterministic_checks'])
