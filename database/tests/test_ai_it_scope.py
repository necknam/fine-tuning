import unittest
from unittest.mock import MagicMock,patch
from src.shared.catalog_scope import scope_reason,scoped_matches
from src.shared.skill_matching import SkillMatcher
from src.database.ingestion.real_data_ingestor import RealDataIngestor
from tests.test_ai_catalog_filter import client,SKILLS

class AIITScopeTests(unittest.TestCase):
    def practical(self):
        return {'title':'ChatGPT 업무 자동화 실습','isbn':'9791191234567',
                'description':'ChatGPT의 프롬프트 작성 방법을 예제와 실습으로 학습하고 문서 처리 워크플로와 AI 에이전트 업무 자동화를 구현합니다.'}
    def test_practical_ai_business_book_allowed(self):
        self.assertIsNone(scope_reason('books',self.practical(),'API_DATA4LIBRARY',{'class_no':'325.211'}))
    def test_practical_ai_engineering_book_allowed(self):
        self.assertIsNone(scope_reason('books',self.practical(),'API_DATA4LIBRARY',{'class_no':'004.73'}))
    def test_ai_mention_cannot_admit_fiction_or_children(self):
        for title,code in [('AI 소설 실습','813.7'),('어린이 ChatGPT 실습','004')]:
            f=self.practical();f['title']=title
            self.assertIsNotNone(scope_reason('books',f,'API_DATA4LIBRARY',{'class_no':code}))
    def test_reported_science_comic_not_admitted(self):
        f=self.practical();f['title']='놓지 마 과학!';f['isbn']='9791190305310'
        self.assertIsNotNone(scope_reason('books',f,'API_DATA4LIBRARY',{'class_no':'004'}))
    def test_business_book_without_ai_training_excluded(self):
        f=self.practical();f['title']='AI 시대 경영 전망';f['description']='AI가 세상을 바꾸는 미래 전망을 살펴봅니다. 일반 경영의 변화를 소개하고 기업의 전략을 이야기합니다.'
        self.assertIsNotNone(scope_reason('books',f,'API_DATA4LIBRARY',{'class_no':'325'}))
    def test_business_kmooc_actual_ai_training_allowed(self):
        self.assertIsNone(scope_reason('courses',self.practical(),'API_KMOOC',{'classfy_name':'사회','middle_classfy_name':'경영'}))
    def test_skill_ids_preserved_with_new_ai_candidates(self):
        matcher=SkillMatcher([{'skill_id':13,'name':'RAG & 생성형 AI 에이전트','category':'AI'}])
        self.assertIn(13,scoped_matches(matcher,self.practical()))
        self.assertEqual(set(matcher.skills),{13})
    def test_no_reset_by_default(self):
        ing=RealDataIngestor(config={},ai_client=client());context=MagicMock()
        context.__enter__.return_value.execute.return_value.fetchall.return_value=SKILLS
        with patch('src.database.deployment.connect',return_value=context), \
             patch('src.database.local_runtime.backup') as backup, \
             patch('src.database.catalog_reset.reset_skill_catalogs') as reset, \
             patch.object(ing,'collect',return_value={'rows':{},'sources':{},'failures':{'books':'FAILED'}}):
            result=ing.execute_full_pipeline()
        backup.assert_not_called();reset.assert_not_called();self.assertFalse(result['database_changes'])

if __name__=='__main__':unittest.main()
