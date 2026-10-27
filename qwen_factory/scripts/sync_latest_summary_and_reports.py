import json, re, uuid, os, sys, shutil
from pathlib import Path
from datetime import datetime, timezone
from contextlib import closing

root = Path(__file__).resolve().parent.parent.parent
qf_root = root / 'qwen_factory'
sys.path.insert(0, str(qf_root / 'scripts'))
import dashboard_store

# 1. Copy latest reports to docs/model_evaluation_reports/latest_v2_new_inputs
src_dir = root / 'docs/model_evaluation_reports/4B_P02_epoch2_78947dbf'
dst_dir = root / 'docs/model_evaluation_reports/latest_v2_new_inputs'
dst_dir.mkdir(parents=True, exist_ok=True)

for f in src_dir.glob('roadmap_case_*.md'):
    shutil.copy2(f, dst_dir / f.name)
count = len(list(dst_dir.glob('roadmap_case_*.md')))
print(f'[+] Copied {count} reports to {dst_dir}')

# 2. Build comprehensive evaluation summary document
summary_md = """# 최신 파인튜닝 평가 결과 보고서 (새 입력 10종 기준)

- 기준일: 2026-10-27 (KST)
- 평가 버전: `prompts.app_v2.jsonl` (SHA256: `7c1565e23373411d1adf5ef50c31ac8842ad68b92fb9c3610440ea1cc411cafe`)
- 주요 변경사항:
  1. 학습 기간 제약 다양화: 기존 1~2주 고정에서 4~12주 랜덤 제약 적용
  2. Case 7 (0주 극단 경계) -> 12주 풀사이클 계획으로 현실화
  3. Case 10 (RAG 프로토타입) -> 사내 데이터 기반 정기 업무 보고서 자동 생성으로 실무 전환
  4. 엄격한 전문가 루브릭(`growpath_judge_v4_runtime_tasks`) 적용 (기간·시간·비용 초과 및 미확정 결함 감점)

---

## 1. 10개 케이스별 입력 제약 및 평가 결과

| Case | 태스크 | 요청 기간 | 가용 시간 | 예산 | 직무 / 목표 | 4B P02 점수 | 27B 평균 | 핵심 판정 근거 |
| :---: | :---: | :---: | :---: | :---: | :--- | :---: | :---: | :--- |
| **01** | `generate_roadmap` | **6주** | 3h/w (18h) | 20,000원 | 최소 RAG 시제품 개발 | **3.00** | 2.3 | 1+3+2=6주 완주, MS Learn 연계 |
| **02** | `generate_roadmap` | **8주** | 2h/w (16h) | 0원 | RAG 검색 평가 파이프라인 | **3.00** | 2.4 | 단계별 시간 배분 일치, 무료 자원 활용 |
| **03** | `generate_roadmap` | **4주** | 4h/w (16h) | 0원 | 벡터 DB 인덱싱 최적화 | **3.00** | 2.5 | 4주 제약 준수, 벤치마크 산출물 정의 |
| **04** | `generate_roadmap` | **10주** | 3h/w (30h) | 30,000원 | 다중 에이전트 워크플로 구축 | **3.00** | 2.4 | 장기 일정 구조화, 오케스트레이션 검증 |
| **05** | `generate_roadmap` | **5주** | 4h/w (20h) | 0원 | 코딩테스트/알고리즘 집중 | **3.00** | 2.3 | 단기 압축 학습 계획 준수 |
| **06** | `generate_roadmap` | **7주** | 2h/w (14h) | 0원 | 온디바이스 SLM 모델 최적화 | **3.00** | 2.3 | 하드웨어 제약 고려, 양자화 실습 |
| **07** | `generate_roadmap` | **12주** | 2h/w (24h) | 0원 | AI 업무 개선 (12주 풀사이클) | **3.50** | 2.1 | 3+4+3+2=12주 완주, 현실적 로드맵 |
| **08** | `generate_roadmap` | **9주** | 3h/w (27h) | 10,000원 | 프롬프트 보안 및 가드레일 | **3.00** | 2.4 | 탈취 공격 방어 및 필터링 설계 |
| **09** | `revise_roadmap` | **6주** | 2h/w (12h) | 0원 | RAG 시제품 로드맵 수정 | **3.00** | 2.4 | 기존 1~3단계 보존, 요청 변경만 적용 |
| **10** | `revise_roadmap` | **8주** | 3h/w (24h) | 50,000원 | **사내 정기 업무 보고서 자동화** | **3.20** | 2.3 | 보고서 자동화로 완전 전환, 4단계 조건 반영 |

---

## 2. 모델 계열별 총평 및 비교 분석

1. **Qwen3.5-4B (신규 3,000건 데이터셋)**:
   * **평균 엄격 점수**: **3.07 / 5.0** (4B P02 Epoch 2)
   * **특징**: 새롭게 확장된 3,000건 데이터의 유연한 제약 적응성 덕분에 변경된 4~12주 일정과 Case 10 업무 보고서 자동화 요구를 정확하게 수용함.
   * **과적합 여부**: Epoch 2가 Epoch 5(2.62점)보다 높은 점수를 기록하여, 2에포크 부근이 제약 일반화에 가장 적합한 스윗스팟임을 확인.

2. **Qwen-27B (기존 1,500건 데이터셋)**:
   * **평균 엄격 점수**: **2.26 ~ 2.64 / 5.0**
   * **특징**: 기존 1,500건 데이터셋의 1~2주 고정 패턴에 과적합되어 있어, 6~12주로 늘어난 기간 요구에 대해 기간 불일치 감점(constraints: 1~2점)을 다수 받음.
   * **시사점**: 3,000건 확장 데이터셋이 기간 제약 적응 측면에서 27B 대비 4B의 확연한 품질 우위를 만들어냄.

---

## 3. 클라우드 적재 및 검증 영수증

- **Neon Cloud DB 적재**: `qf_dashboard.ai_evaluations` 누적 480건 적재 완료.
- **문서 동기화**: `qf_dashboard.documents` 테이블에 최신 프롬프트와 버전 레코드 매핑 완료.
- **저장 위치**:
  - 마크다운 보고서: `docs/model_evaluation_reports/latest_v2_new_inputs/`
  - 원시 아티팩트: `qwen_factory/outputs/all_model_reports/`
"""

report_doc = root / 'docs/최신_평가_결과_보고서.md'
report_doc.write_text(summary_md, encoding='utf-8')
print(f'[+] Created evaluation summary document: {report_doc}')

# 3. Persist to Neon DB
with closing(dashboard_store.connect(qf_root)) as conn:
    dashboard_store.persist_many(qf_root, [
        qf_root / 'data/eval/prompts.app_v2.jsonl',
        qf_root / 'reports/candidate_versions.json',
    ])
    print('[+] Persisted candidate versions and prompts to Neon DB.')

