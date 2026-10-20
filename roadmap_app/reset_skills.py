"""Compatibility command: validate existing real skill identities and refresh canonical vectors.

Does not seed skills, clear mappings, or write obsolete master embedding columns.
"""
from src.database.deployment import connect, validate_skill_identity
from src.database.vectors import resource_vectors
import json

STANDARD_SKILLS = [
    {"skill_id": 1, "name": "SQL 기본 문법 & 조인", "category": "데이터베이스"},
    {"skill_id": 2, "name": "SQL 쿼리 튜닝 & 인덱스 최적화", "category": "데이터베이스"},
    {"skill_id": 3, "name": "RDBMS 데이터 모델링", "category": "데이터베이스"},
    {"skill_id": 4, "name": "NoSQL & 분산 DB", "category": "데이터베이스"},
    {"skill_id": 5, "name": "ETL & 데이터 파이프라인", "category": "데이터 엔지니어링"},
    {"skill_id": 6, "name": "데이터 웨어하우스 & OLAP", "category": "데이터 엔지니어링"},
    {"skill_id": 7, "name": "탐색적 데이터 분석(EDA) & 전처리", "category": "데이터 분석"},
    {"skill_id": 8, "name": "머신러닝 지도/비지도 학습", "category": "머신러닝"},
    {"skill_id": 9, "name": "MLOps & 모델 서빙", "category": "머신러닝"},
    {"skill_id": 10, "name": "딥러닝 신경망 아키텍처", "category": "딥러닝"},
    {"skill_id": 11, "name": "PyTorch/TensorFlow 딥러닝 구현", "category": "딥러닝"},
    {"skill_id": 12, "name": "자연어 처리(NLP) & LLM 기초", "category": "딥러닝"},
    {"skill_id": 13, "name": "RAG & 생성형 AI 에이전트", "category": "인공지능"},
    {"skill_id": 14, "name": "컴퓨터 비전(CV) 모델링", "category": "인공지능"},
    {"skill_id": 15, "name": "리눅스 환경 및 Bash 스크립팅", "category": "인프라/OS"},
    {"skill_id": 16, "name": "TCP/IP 네트워크 프로토콜", "category": "네트워크"},
    {"skill_id": 17, "name": "클라우드 컴퓨팅 아키텍처 (AWS/Azure)", "category": "클라우드"},
    {"skill_id": 18, "name": "클라우드 IAM & 네트워크 보안", "category": "클라우드"},
    {"skill_id": 19, "name": "Docker 컨테이너 가상화", "category": "DevOps"},
    {"skill_id": 20, "name": "Kubernetes 클러스터 오케스트레이션", "category": "DevOps"},
    {"skill_id": 21, "name": "CI/CD 배포 자동화 파이프라인", "category": "DevOps"},
    {"skill_id": 22, "name": "Python 프로그래밍 & 비동기 I/O", "category": "프로그래밍"},
    {"skill_id": 23, "name": "자료구조 & 알고리즘 최적화", "category": "컴퓨터공학 기초"},
    {"skill_id": 24, "name": "운영체제(OS) & 동시성 제어", "category": "컴퓨터공학 기초"},
    {"skill_id": 25, "name": "컴퓨터 구조 & 메모리 관리", "category": "컴퓨터공학 기초"},
    {"skill_id": 26, "name": "객체지향 설계(OOP) & 디자인 패턴", "category": "소프트웨어공학"},
    {"skill_id": 27, "name": "RESTful API 서버 아키텍처", "category": "백엔드"},
    {"skill_id": 28, "name": "대용량 트래픽 처리 & 캐싱", "category": "백엔드"},
    {"skill_id": 29, "name": "마이크로서비스(MSA) 설계", "category": "백엔드"},
    {"skill_id": 30, "name": "웹 프레임워크 (FastAPI/Django)", "category": "백엔드"},
    {"skill_id": 31, "name": "시스템 프로그래밍 & POSIX API", "category": "시스템"},
    {"skill_id": 32, "name": "멀티스레딩 & 비동기 동시성", "category": "시스템"},
    {"skill_id": 33, "name": "시스템 & OS 보안 강화", "category": "정보보안"},
    {"skill_id": 34, "name": "웹 애플리케이션 취약점 진단", "category": "정보보안"},
    {"skill_id": 35, "name": "네트워크 보안 & 침입 탐지", "category": "정보보안"},
    {"skill_id": 36, "name": "데이터 거버넌스 & 보안 규정 준수", "category": "정보보안"},
]

def reset_and_seed_skill_tags():
    with connect('SUPABASE_DB_URL') as conn:
        actual=conn.execute('SELECT skill_id,name,category FROM public.skill_tags ORDER BY skill_id').fetchall()
        if actual != STANDARD_SKILLS:
            raise ValueError('Existing skill identities differ; refusing to seed or overwrite.')
        result = resource_vectors.embed(conn)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result

if __name__ == '__main__':
    reset_and_seed_skill_tags()
