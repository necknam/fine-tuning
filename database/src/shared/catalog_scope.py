"""Korean IT catalog boundary. Classification, title, substantive content all required."""
import re
from urllib.parse import urlsplit

POLICY_VERSION = "kr-ai-it-2026-10-22-v2"
SOURCES = {"books": {"API_DATA4LIBRARY"}, "courses": {"API_KMOOC", "API_MS_LEARN"},
           "certifications": {"API_ODCLOUD_KDATA", "API_MS_CERT"},
           "jobs": {"API_CAREERNET"}, "majors": {"API_CAREERNET_MAJOR"}}
# AI/data/computer mentions alone are deliberately absent.
IT = re.compile(r"파이썬|\bpython\b|\bsql\b|데이터베이스|자료구조|알고리즘|프로그래밍|프로그래머|소프트웨어|컴퓨터\s*(공학|과학|구조|비전|네트워크)|전산|정보\s*(보안|보호|통신|시스템)|머신\s*러닝|딥\s*러닝|기계\s*학습|자연어\s*처리|인공지능|데이터\s*(분석|과학|공학|엔지니어)|클라우드|리눅스|도커|쿠버네티스|\b(?:linux|docker|kubernetes|pytorch|tensorflow|azure|aws|devops|mlops|rag|fastapi|django)\b|네트워크\s*(보안|설계|운영)|운영체제|객체지향|웹\s*(개발|프레임워크|서버)|시스템\s*(개발|프로그래밍)|정보처리|빅데이터", re.I)
OUTSIDE = re.compile(r"문학|소설|사유|시집|(?<!자)동화|수필|에세이|인문|철학|종교|역사|예술|미술|음악|요리|여행|육아|어린이|유아|초등|중학생|고등학생|교양|리터러시|마케팅|재테크|주식|방사선|간호|경비원|청렴")
AI = re.compile(r"(?<![A-Za-z])AI(?![A-Za-z])|인공지능|생성형|프롬프트|챗\s*(GPT|지피티)|ChatGPT|\b(?:LLM|Copilot|Gemini|Claude)\b|코파일럿|제미나이|클로드",re.I)
AI_TASK = re.compile(r"프롬프트|업무\s*자동화|워크플로|에이전트|모델\s*(학습|훈련|평가|구현|개발|배포)|파인\s*튜닝|미세\s*조정|검색\s*증강|실습|예제|실전|hands.on|prompt|fine.tun|workflow",re.I)
HARD_OUTSIDE = re.compile(r"문학|소설|시집|(?<!자)동화|수필|에세이|어린이|유아|초등|중학생|고등학생|학습\s*만화")

PRACTICE = re.compile(r"구현|개발|설계|실습|프로그래밍|코딩|학습|훈련|쿼리|분석|알고리즘|모델링|구축|배포|운영|디버깅|최적화|처리|보안|작성|관리|컴파일|테스트|\b(?:implement|develop|design|build|deploy|configure|train|query|code|programming|manage|analy[sz]|secure|test)\w*", re.I)

def body_text(fields):
    return "\n".join(dict.fromkeys(str(fields.get(k) or "") for k in
                       ("syllabus_summary", "description", "test_subjects", "curriculum", "ncs_units")))

def scope_reason(kind, fields, source, raw):
    if source not in SOURCES.get(kind, set()):
        return "scope_unsupported_source"
    if not isinstance(raw, dict):
        return "scope_missing_official_evidence"
    title = str(fields.get("title") or "")
    body = body_text(fields)
    if not re.search(r"[가-힣]", title) or not re.search(r"[가-힣]", body):
        return "scope_no_korean_content"
    ai_learning=bool(AI.search(title) and AI.search(body) and AI_TASK.search(body) and PRACTICE.search(body))
    if HARD_OUTSIDE.search(title) or (OUTSIDE.search(title) and not ai_learning):
        return "scope_outside_it_subject"
    if not IT.search(title) and not ai_learning:
        return "scope_title_not_it_specialty"
    if len(body.strip()) < 40 or (not IT.search(body) and not ai_learning) or not PRACTICE.search(body):
        return "scope_no_substantive_it_training_or_work"
    if source in ("API_MS_LEARN", "API_MS_CERT"):
        try:
            url = urlsplit(str(fields.get("url") or fields.get("source_url") or ""))
            if url.hostname != "learn.microsoft.com" or not url.path.lower().startswith("/ko-kr/"):
                return "scope_no_korean_localization"
        except ValueError:
            return "scope_no_korean_localization"
    elif not re.search(r"[가-힣]", body):
        return "scope_no_korean_content"
    if kind == "books":
        isbn = str(fields.get("isbn") or "").replace("-", "")
        if not re.fullmatch(r"(?:97889|97911)\d{8}", isbn):
            return "scope_not_korean_publication"
        records = [raw.get("detail_record"), raw.get("list_record"), raw]
        codes = [str(r.get("class_no") or "").strip() for r in records if isinstance(r, dict) and r.get("class_no")]
        def accepted_code(code):
            return bool(re.fullmatch(r"00[45](?:\.\d+)?",code) or
                        (ai_learning and re.fullmatch(r"325(?:\.\d+)?",code)))
        if not codes or any(not accepted_code(code) for code in codes):
            return "scope_book_not_kdc_004_005"
    if source == "API_KMOOC":
        classification = " ".join(str(raw.get(k) or "") for k in ("classfy_name", "middle_classfy_name"))
        if HARD_OUTSIDE.search(classification) or (not ai_learning and (OUTSIDE.search(classification) or not re.search(r"공학|컴퓨터|정보|소프트웨어|전산|데이터|인공지능", classification))):
            return "scope_course_not_it_classification"
    if kind in ("jobs", "majors") and not isinstance(raw.get("detail_record"), dict):
        return "scope_missing_official_detail"
    return None

def scoped_matches(matcher, fields):
    # A skill mentioned only in the title is insufficient to attach a learning link.
    return matcher.match(body_text(fields))
