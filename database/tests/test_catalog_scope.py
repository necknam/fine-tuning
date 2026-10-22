import unittest
from src.shared.catalog_scope import scope_reason, scoped_matches
from src.shared.catalog_eligibility import exclusion_reason

class CatalogScopeTests(unittest.TestCase):
    def book(self):
        return dict(title="파이썬 프로그래밍 실습", isbn="9791191234567", description="파이썬 프로그래밍 실습으로 데이터베이스와 SQL 쿼리를 작성하고 소프트웨어를 개발하는 방법을 학습합니다.")
    def test_reported_childrens_literature_is_never_admitted(self):
        f=dict(title="할머니, 어디 가요? 밤 주우러 간다! :옥이네 가을 이야기", isbn="9788984286269",
               description="옥이네 이야기 시리즈. 컴퓨터에 갇힌 도시 아이들에게 자연과 건강한 먹을거리를 함께 보여준다.")
        self.assertEqual(scope_reason("books",f,"API_DATA4LIBRARY",{"class_no":"813.7"}),"scope_title_not_it_specialty")
    def test_technical_korean_book(self):
        self.assertIsNone(scope_reason("books",self.book(),"API_DATA4LIBRARY",{"class_no":"005.13"}))
    def test_literature_rejected_even_with_technical_description(self):
        f=self.book();f["title"]="문학 데이터 분석 파이썬"
        self.assertEqual(scope_reason("books",f,"API_DATA4LIBRARY",{"class_no":"005.13"}),"scope_outside_it_subject")
    def test_wrong_or_missing_kdc_rejected(self):
        for raw in ({"class_no":"813.7"},{}, {"detail_record":{"class_no":"813.7"},"list_record":{"class_no":"005"}}):
            self.assertEqual(scope_reason("books",self.book(),"API_DATA4LIBRARY",raw),"scope_book_not_kdc_004_005")
    def test_keyword_only_and_unknown_sources_rejected(self):
        f=self.book();f["description"]="IT AI Python"
        self.assertIsNotNone(scope_reason("books",f,"API_DATA4LIBRARY",{"class_no":"005"}))
        self.assertIsNotNone(scope_reason("books",self.book(),"UNTRUSTED",{"class_no":"005"}))
    def test_foreign_publication_rejected(self):
        f=self.book();f["isbn"]="9780131234567"
        self.assertEqual(scope_reason("books",f,"API_DATA4LIBRARY",{"class_no":"005"}),"scope_not_korean_publication")
    def test_kmooc_humanities_class_rejected(self):
        self.assertEqual(scope_reason("courses",self.book(),"API_KMOOC",{"classfy_name":"인문","middle_classfy_name":"문학"}),"scope_course_not_it_classification")
    def test_kmooc_engineering_accepted(self):
        self.assertIsNone(scope_reason("courses",self.book(),"API_KMOOC",{"classfy_name":"공학","middle_classfy_name":"컴퓨터"}))
    def test_microsoft_korean_locale_and_actual_language_required(self):
        f=self.book();f["url"]="https://learn.microsoft.com/en-us/training/"
        self.assertEqual(scope_reason("courses",f,"API_MS_LEARN",{}),"scope_no_korean_localization")
        f["url"]="https://learn.microsoft.com/ko-kr/training/"
        self.assertIsNone(scope_reason("courses",f,"API_MS_LEARN",{}))
        f["description"]="Develop Python software and implement database queries in a training project."
        self.assertEqual(scope_reason("courses",f,"API_MS_LEARN",{}),"scope_no_korean_content")
    def test_title_only_skill_is_not_linked(self):
        class Matcher:
            def match(self,text):return {1:["SQL"]} if "SQL" in text else {}
        self.assertEqual(scoped_matches(Matcher(),{"title":"SQL","description":"일반 교양"}),{})
    def test_book_cannot_bypass_retrieval_guard(self):
        f=self.book();f["title"]="문학 데이터 분석"
        self.assertEqual(exclusion_reason("books",f,"API_DATA4LIBRARY",{"class_no":"005"},None),"scope_outside_it_subject")
    def test_non_it_job_and_major_rejected(self):
        for kind,source,title in [("jobs","API_CAREERNET","경비원"),("majors","API_CAREERNET_MAJOR","방사선학과")]:
            f=self.book();f["title"]=title
            self.assertIsNotNone(scope_reason(kind,f,source,{"detail_record":{}}))

if __name__ == "__main__":unittest.main()
