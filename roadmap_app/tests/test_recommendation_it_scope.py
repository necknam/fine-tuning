from unittest import TestCase
from unittest.mock import patch
from src.roadmap.services.recommendation_service import RecommendationService,supported_skill_links
from src.shared.skill_matching import SkillMatcher

SKILLS=[{'skill_id':1,'name':'SQL 기본 문법 & 조인','category':'데이터베이스'},
        {'skill_id':22,'name':'Python 프로그래밍 & 비동기 I/O','category':'프로그래밍'}]


class RecommendationITScopeTests(TestCase):
    def test_legacy_unrelated_or_wrong_target_link_is_not_evidence(self):
        m=SkillMatcher(SKILLS)
        self.assertEqual(supported_skill_links({'title':'문화와 생활 속 청렴','linked_skill_ids':[1,22]},m),set())
        self.assertEqual(supported_skill_links({'title':'Python 프로그래밍 실습','linked_skill_ids':[1,22]},m),{22})

    def test_retrieval_rejects_wrong_target_even_with_high_similarity_and_saved_link(self):
        rows={('skills',str(s['skill_id'])):{'record':s,'hash':'h'} for s in SKILLS}
        rows.update({('courses','bad'):{'record':{'course_id':'bad','title':'Python 실습','linked_skill_ids':[1,22]},'hash':'h'},
                     ('courses','good'):{'record':{'course_id':'good','title':'SQL 기본 문법 실습','linked_skill_ids':[1]},'hash':'h'}})
        module='src.roadmap.services.recommendation_service.'
        with patch(module+'vectors.sources',return_value=rows),patch(module+'eligible_keys',return_value=({('courses','bad'),('courses','good')},{})),\
             patch(module+'vectors.stored',return_value={}),patch(module+'vectors.is_current',return_value=True),\
             patch(module+'vectors.embed_texts',return_value=[[1.0]]),\
             patch(module+'vectors.similarities',return_value={('skills','1'):.8,('courses','bad'):.99,('courses','good'):.6}) as similarity:
            result=RecommendationService()._retrieve(object(),['SQL 기본 문법 & 조인'],'',None,'SQL 실습')
        self.assertEqual([r['course_id'] for r in result['courses']],['good'])
        self.assertNotIn(('courses','bad'),similarity.call_args.args[2])
        self.assertEqual(result['courses'][0]['matched_skill_ids'],[1])
