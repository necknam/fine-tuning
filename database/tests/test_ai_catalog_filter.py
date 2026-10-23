import json
import os
from datetime import datetime, timezone
from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import MagicMock, patch
from pathlib import Path
from src.database.ingestion.ai_catalog_filter import AICatalogFilter, AIReviewError, MODEL
from src.database.ingestion.real_data_ingestor import RealDataIngestor

SKILLS=[{'skill_id':1,'name':'SQL 기본 문법 & 조인','category':'IT'},
        {'skill_id':22,'name':'Python 프로그래밍 & 비동기 I/O','category':'IT'}]

def row():
    return {'kind':'books','source':'API_DATA4LIBRARY','external_key':'9791191234567',
        'fields':{'isbn':'9791191234567','title':'파이썬 SQL 프로그래밍 실습','author':'저자','publisher':'출판사','content_status':'ready',
                  'description':'파이썬 프로그래밍으로 SQL 조인과 데이터베이스를 구현하고 데이터 분석 방법을 구체적으로 학습하는 실습서입니다.'},
        'raw':{'class_no':'005.13'},'matches':{1:['SQL'],22:['파이썬']},'fetched_at':datetime.now(timezone.utc).isoformat()}

def client(value=None, *, refusal=None, finish='stop'):
    fake=MagicMock()
    content=json.dumps(value if value is not None else {'decision':'APPROVE','skill_ids':[1]})
    fake.chat.completions.create.return_value=NS(choices=[NS(finish_reason=finish,message=NS(content=content,refusal=refusal))])
    return fake

class AIAdmissionTests(TestCase):
    def test_exact_model_strict_output_and_no_api_storage(self):
        fake=client();result=AICatalogFilter(SKILLS,client=fake).filter('books',[row()])
        self.assertEqual(set(result[0]['matches']),{1})
        args=fake.chat.completions.create.call_args.kwargs
        self.assertEqual(args['model'],'gpt-6-luna');self.assertFalse(args['store'])
        self.assertTrue(args['response_format']['json_schema']['strict'])
        self.assertNotIn('reason',args['response_format']['json_schema']['schema']['properties'])
    def test_exclusion_is_not_inserted(self):
        self.assertEqual(AICatalogFilter(SKILLS,client=client({'decision':'EXCLUDE','skill_ids':[]})).filter('books',[row()]),[])
    def test_only_same_execution_cache_reused(self):
        fake=client();gate=AICatalogFilter(SKILLS,client=fake)
        gate.filter('books',[row()]);gate.filter('books',[row()])
        self.assertEqual(fake.chat.completions.create.call_count,1)
        AICatalogFilter(SKILLS,client=fake).filter('books',[row()])
        self.assertEqual(fake.chat.completions.create.call_count,2)
    def test_changed_content_is_reviewed_again(self):
        fake=client();gate=AICatalogFilter(SKILLS,client=fake);gate.filter('books',[row()])
        changed=row();changed['fields']['description']+='새 교육 내용';gate.filter('books',[changed])
        self.assertEqual(fake.chat.completions.create.call_count,2)
    def test_missing_key_fails_closed(self):
        with patch.dict(os.environ,{},clear=True),self.assertRaises(AIReviewError):AICatalogFilter(SKILLS)
    def test_refusal_truncation_and_api_failure_fail_closed(self):
        for fake in (client(refusal='refused'),client(finish='length')):
            with self.subTest(fake=fake),self.assertRaises(AIReviewError):AICatalogFilter(SKILLS,client=fake).filter('books',[row()])
        fake=client();fake.chat.completions.create.side_effect=RuntimeError('secret request text')
        with self.assertRaises(AIReviewError) as caught:AICatalogFilter(SKILLS,client=fake).filter('books',[row()])
        self.assertNotIn('secret',str(caught.exception))
    def test_invalid_or_extra_output_and_unknown_skills_fail_closed(self):
        for value in ({'decision':'APPROVE','skill_ids':[999]}, {'decision':'MAYBE','skill_ids':[]},
                      {'decision':'APPROVE','skill_ids':[True]},
                      {'decision':'APPROVE','skill_ids':[1],'reason':'not wanted'}):
            with self.subTest(value=value),self.assertRaises(AIReviewError):
                AICatalogFilter(SKILLS,client=client(value)).filter('books',[row()])
    def test_exclusion_wins_and_no_skill_approval_is_excluded(self):
        for value in ({'decision':'APPROVE','skill_ids':[]},{'decision':'EXCLUDE','skill_ids':[1]}):
            self.assertEqual(AICatalogFilter(SKILLS,client=client(value)).filter('books',[row()]),[])
        accepted=AICatalogFilter(SKILLS,client=client({'decision':'APPROVE','skill_ids':[1,1]})).filter('books',[row()])
        self.assertEqual(set(accepted[0]['matches']),{1})
    def test_malformed_json_fails_closed(self):
        fake=client();fake.chat.completions.create.return_value.choices[0].message.content='bad JSON'
        with self.assertRaises(AIReviewError):AICatalogFilter(SKILLS,client=fake).filter('books',[row()])
    def test_only_catalog_fields_sent_and_no_judgment_fields_added(self):
        fake=client();candidate=row();candidate['raw']['private_key']='NEVER_SEND';candidate['fields']['employee_name']='NEVER_SEND'
        result=AICatalogFilter(SKILLS,client=fake).filter('books',[candidate])
        args=fake.chat.completions.create.call_args.kwargs
        self.assertNotIn('NEVER_SEND',json.dumps(args));self.assertEqual(set(candidate),set(result[0]))
    def test_official_content_is_preserved_for_recommendation(self):
        fake=client();candidate=row()
        result=AICatalogFilter(SKILLS,client=fake).filter('books',[candidate])
        self.assertIs(result[0]['fields'],candidate['fields'])
        self.assertIs(result[0]['raw'],candidate['raw'])
        from src.database.vectors.resource_vectors import embedding_text
        self.assertIn(candidate['fields']['description'],embedding_text('books',result[0]['fields']))
    def test_description_fallback_copies_only_official_text(self):
        from src.database.ingestion.catalog_details import copy_api_description
        fields={'test_subjects':'SQL 문법 / 관계형 데이터베이스 / 조인과 집계'}
        copy_api_description('certifications',fields)
        self.assertEqual(fields['description'],fields['test_subjects'])
        original=fields['description']='공식 별도 소개'
        copy_api_description('certifications',fields)
        self.assertEqual(fields['description'],original)
    def test_certification_status_refresh_cannot_reapprove_excluded_rows(self):
        from src.database.ingestion.catalog_details import refresh_certification_status
        conn=MagicMock();conn.execute.return_value.fetchall.return_value=[{'cert_id':1,'content_status':'scope_excluded'}]
        self.assertEqual(refresh_certification_status(conn),{})
        self.assertFalse(any('UPDATE' in call.args[0] for call in conn.execute.call_args_list))
    def test_no_silent_truncation(self):
        fake=client();candidate=row();candidate['fields']['description']='a'*65000
        self.assertEqual(AICatalogFilter(SKILLS,client=fake).filter('books',[candidate]),[])
        fake.chat.completions.create.assert_not_called()
    def test_direct_apply_cannot_bypass_ai_failure(self):
        fake=client();fake.chat.completions.create.side_effect=RuntimeError('unavailable')
        ing=RealDataIngestor(config={},ai_client=fake);conn=MagicMock()
        with self.assertRaises(AIReviewError):
            ing.apply(conn,{'failures':{},'rows':{'books':[row()]},'skill_identity':SKILLS})
        conn.execute.assert_not_called()
    def test_source_collection_stops_on_ai_failure(self):
        fake=client();fake.chat.completions.create.side_effect=RuntimeError('unavailable')
        ing=RealDataIngestor(config={'ingestion':{}},ai_client=fake)
        with patch('src.database.ingestion.real_data_ingestor.KINDS',('books',)), \
             patch.object(ing,'fetch_books_from_api',return_value=[row()]), \
             patch('src.database.ingestion.catalog_details.finalize',side_effect=lambda _,kind,rows:rows):
            with self.assertRaises(AIReviewError):ing.collect(SKILLS)
    def test_collect_uses_ai_skill_subset(self):
        ing=RealDataIngestor(config={'ingestion':{}},ai_client=client())
        with patch('src.database.ingestion.real_data_ingestor.KINDS',('books',)), \
             patch.object(ing,'fetch_books_from_api',return_value=[row()]), \
             patch('src.database.ingestion.catalog_details.finalize',side_effect=lambda _,kind,rows:rows):
            batch=ing.collect(SKILLS)
        self.assertEqual(set(batch['rows']['books'][0]['matches']),{1})
        self.assertEqual(batch['sources']['books_ai'],{'approved':1,'excluded':0})
    def test_reset_precedes_collection_and_is_reported_on_failure(self):
        from src.database.local_runtime import DATA
        ing=RealDataIngestor(config={},ai_client=client());conn=MagicMock();conn.info.host='127.0.0.1'
        conn.execute.return_value.fetchall.return_value=SKILLS
        conn.execute.return_value.fetchone.return_value={'data_directory':str(DATA)}
        context=MagicMock();context.__enter__.return_value=conn
        order=[]
        with patch('src.database.deployment.connect',return_value=context), \
             patch('src.database.local_runtime.backup',side_effect=lambda path:order.append('backup') or {'backup':str(path)}), \
             patch('src.database.catalog_reset.reset_skill_catalogs',side_effect=lambda c:order.append('reset') or {'reset':True}), \
             patch.object(ing,'collect',side_effect=lambda *a,**k:order.append('collect') or {'rows':{},'sources':{},'failures':{'books':'FAILED'}}):
            result=ing.execute_full_pipeline(reset_catalog=True)
        self.assertEqual(order,['backup','reset','collect']);self.assertTrue(result['database_changes'])
    def test_dry_run_does_not_reset(self):
        ing=RealDataIngestor(config={},ai_client=client());context=MagicMock()
        context.__enter__.return_value.execute.return_value.fetchall.return_value=SKILLS
        batch={'rows':{},'sources':{},'failures':{},'unresolved_rule_names':[]}
        with patch('src.database.deployment.connect',return_value=context), \
             patch('src.database.local_runtime.backup') as backup, \
             patch('src.database.catalog_reset.reset_skill_catalogs') as reset,patch.object(ing,'collect',return_value=batch):
            result=ing.execute_full_pipeline(dry_run=True)
        backup.assert_not_called();reset.assert_not_called();self.assertFalse(result['database_changes'])
