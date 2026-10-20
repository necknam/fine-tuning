from datetime import datetime, timezone, timedelta
from unittest import TestCase
from unittest.mock import patch

from src.shared.skill_matching import SkillMatcher
from src.database.ingestion.real_data_ingestor import RealDataIngestor, SourceError
from src.database.ingestion import catalog_details

SKILLS=[{'skill_id':1,'name':'SQL 기본 문법 & 조인','category':'IT'}]

def ing():
    obj=RealDataIngestor(config={'library':{'base_url':'https://data4library.kr/api/srchBooks',
        'max_pages':1,'page_size':50},'ingestion':{'book_keywords':['데이터베이스']},
        'kmooc':{'detail_url':'https://apis.data.go.kr/B552881/kmooc_v2_0/courseDetail_v2_0'}})
    obj.matcher=SkillMatcher(SKILLS,rules={'SQL 기본 문법 & 조인':['SQL']})
    return obj

class CatalogExpansionTests(TestCase):
    def test_description_can_match_without_title_keyword(self):
        obj=ing()
        row=obj._record('books','API_DATA4LIBRARY','123',
            {'title':'현업의 문제 해결','description':'SQL 조인과 PostgreSQL 실습'}, {})
        self.assertIn(1,row['matches'])

    def test_zero_limit_keeps_all_matches(self):
        obj=ing()
        rows=[{'source':'real','external_key':str(i),'matches':{1:['SQL']}} for i in range(6)]
        self.assertEqual(len(obj._select('courses',rows,0)),6)
        self.assertFalse(obj.selection_reports['courses']['limit_reached'])

    def test_detail_is_fetched_before_book_skill_filter(self):
        obj=ing()
        with patch.object(obj,'_key',return_value='test'), patch.object(obj,'_request',return_value={
            'response':{'numFound':1,'docs':[{'doc':{'isbn13':'9781234567890','bookname':'현업의 문제 해결'}}]}}) as request:
            with patch.object(catalog_details,'enrich_books',side_effect=lambda _,rows: rows) as detail:
                rows=obj.fetch_books_from_api(1)
        self.assertEqual(len(detail.call_args.args[1]),1)
        self.assertFalse(rows[0]['matches'])
        self.assertIn('keyword',request.call_args.args[1])
        self.assertNotIn('title',request.call_args.args[1])

    def test_list_quota_failure_keeps_completed_candidates(self):
        obj=ing();obj.config['ingestion']['book_keywords']=['SQL','데이터베이스']
        data={'response':{'numFound':1,'docs':[{'doc':{'isbn13':'9781234567890','bookname':'SQL 실무'}}]}}
        with patch.object(obj,'_key',return_value='test'), patch.object(obj,'_request',side_effect=[data,SourceError('LIBRARY_REQUEST_BUDGET_REACHED')]):
            with patch.object(catalog_details,'enrich_books',side_effect=lambda _,rows: rows):
                rows=obj.fetch_books_from_api(10)
        self.assertEqual(len(rows),1)
        self.assertEqual(obj.reports['library']['status'],'INCOMPLETE')

    def test_page_size_follows_actual_total_not_requested_size(self):
        obj=ing();obj.max_pages=10
        payloads=[{'resultCode':'00','items':[{'id':'first'}],'totalCount':2},
                  {'resultCode':'00','items':[{'id':'second'}],'totalCount':2}]
        payloads[0]['items'][0]['id']='first'
        with patch.object(obj,'_request',side_effect=payloads) as request:
            rows=obj._pages('kmooc','https://apis.data.go.kr/list',{},page_key='Page',size_key='Size',size=50,list_key='items')
        self.assertEqual(len(rows),2)
        self.assertEqual(request.call_args.args[1]['Page'],2)
        self.assertFalse(obj.reports['kmooc']['page_limit_reached'])

    def test_kmooc_detail_matches_generic_title(self):
        obj=ing();now=datetime.now(timezone.utc)
        raw={'id':'123','public_yn':'Y','enrollment_start':(now-timedelta(days=1)).isoformat(),
             'enrollment_end':(now+timedelta(days=1)).isoformat(),'study_end':(now+timedelta(days=2)).isoformat()}
        row=obj._record('courses','API_KMOOC','123',{'title':'현업의 문제 해결','url':'https://www.kmooc.kr/x',
            'org_name':'실제 대학'},raw)
        with patch.object(obj,'_key',return_value='test'),patch.object(obj,'_request',return_value={
            'resultCode':'00','results':{**raw,'summary':'SQL 조인과 인덱스를 직접 작성하여 데이터베이스 성능을 개선합니다.','week':'5'}}) as request:
            rows=catalog_details.enrich_kmooc(obj,[row])
        valid=catalog_details.finalize(obj,'courses',rows)
        self.assertEqual(len(valid),1)
        self.assertIn(1,valid[0]['matches'])
        self.assertEqual(request.call_args.args[1]['CourseId'],'123')

    def test_closed_kmooc_not_fetched(self):
        obj=ing()
        row=obj._record('courses','API_KMOOC','closed',{'title':'SQL 실습'},{'public_yn':'N'})
        with patch.object(obj,'_key',return_value='test'),patch.object(obj,'_request') as request:
            self.assertEqual(catalog_details.enrich_kmooc(obj,[row]),[])
        request.assert_not_called()

    def test_long_course_keeps_source_and_bounds_only_embedding_input(self):
        from src.database.vectors.resource_vectors import embedding_text
        row={'course_id':'real','title':'SQL 실습','syllabus_summary':'SQL 실습 내용 '*5000}
        original=row['syllabus_summary']
        value=embedding_text('courses',row)
        self.assertLessEqual(len(value.encode('utf-8')),8000)
        self.assertEqual(row['syllabus_summary'],original)

    def test_library_budget_counts_retries_and_prevents_extra_network_call(self):
        from unittest.mock import MagicMock
        obj=ing();obj.config['library']['request_budget']=2
        obj.client=MagicMock()
        failed=MagicMock(status_code=503,headers={})
        obj.client.get.return_value=failed
        with patch.object(obj,'_library_cache_read',return_value=None),patch('src.database.ingestion.real_data_ingestor.time.sleep'):
            with self.assertRaisesRegex(SourceError,'LIBRARY_REQUEST_BUDGET_REACHED'):
                obj._request('https://data4library.kr/api/srchBooks',{'keyword':'SQL'})
        self.assertEqual(obj.client.get.call_count,2)

    def test_kmooc_unix_seconds_are_valid_dates(self):
        from src.shared.catalog_eligibility import timestamp
        now=datetime.now(timezone.utc).replace(microsecond=0)
        self.assertEqual(timestamp(str(int(now.timestamp()))),now)
        self.assertEqual(timestamp(str(int(now.timestamp())*1000)),now)
        self.assertIsNone(timestamp('not-a-date'))

    def test_clothing_patterns_do_not_match_software_design(self):
        m=SkillMatcher([{'skill_id':26,'name':'객체지향 설계(OOP) & 디자인 패턴'}],
            rules={'객체지향 설계(OOP) & 디자인 패턴':['디자인.*패턴','오브젝트']})
        self.assertFalse(m.match('디자인 전문 인력을 양성합니다. 의복 생산의 기본이 되는 패턴 설계'))
        self.assertFalse(m.match('패션 디자인 패턴 실습'))
        self.assertIn(26,m.match('객체지향 프로그래밍과 디자인 패턴을 구현합니다.'))

    def test_latin_terms_adjacent_to_korean_are_recognized(self):
        self.assertIn(1,ing().matcher.match('SQL기초부터 PostgreSQL실습까지'))
        self.assertFalse(ing().matcher.match('nosqlstorage'))

    def test_legacy_non_it_rows_are_excluded_without_deleting_them(self):
        from unittest.mock import MagicMock
        from src.shared.catalog_eligibility import eligible_keys
        now=datetime.now(timezone.utc).isoformat()
        rows=[{'job_id':1,'title':'SQL 데이터베이스 관리자','description':'SQL 조인과 데이터베이스 설계 및 운영 업무를 수행합니다.',
               'content_status':'ready','source_url':'https://www.career.go.kr','source_verified_at':now},
              {'job_id':2,'title':'경비원','description':'시설의 출입을 관리하고 순찰하여 안전을 확보하는 업무를 수행합니다.',
               'content_status':'ready','source_url':'https://www.career.go.kr','source_verified_at':now}]
        sources=[{'resource_type':'jobs','entity_key':str(r['job_id']),'source':'API_CAREERNET',
                  'payload':{'detail_record':{'baseInfo':{'job_cd':r['job_id']}}},'fetched_at':now} for r in rows]
        def query(sql):
            result=MagicMock()
            result.fetchall.return_value=SKILLS if 'SELECT skill_id' in sql else sources if 'catalog_api_sources' in sql else [{'record':r} for r in rows] if 'public.jobs ' in sql else []
            return result
        conn=MagicMock();conn.execute.side_effect=query
        usable,report=eligible_keys(conn)
        self.assertIn(('jobs','1'),usable)
        self.assertNotIn(('jobs','2'),usable)
        self.assertEqual(report['jobs']['excluded']['no_it_skill_evidence'],1)
        self.assertFalse(any('DELETE' in str(call) for call in conn.execute.call_args_list))
