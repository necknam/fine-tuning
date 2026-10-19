"""Create GrowPath synthetic wiring-test data. Never use for quality evaluation."""
import argparse
import hashlib
import json
import random
from pathlib import Path


SYSTEM = "당신은 GrowPath 학습 로드맵 작성 도우미입니다. 제공된 자료 ID만 사용하고, 4단계로 구성하며 시간과 예산을 지키세요. 결과는 JSON으로 작성하세요."
STAGES = ["기초 다지기", "핵심 이해", "업무 적용", "성과 확인"]
VIEWS = [("cost", "비용 우선"), ("time", "시간 우선"), ("application", "업무 적용 우선")]


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def build_rows():
    rows = []
    domains = ["문서 검색", "문의 분류", "업무 요약", "표 데이터 분석", "FAQ 검색"]
    for index in range(1, 21):
        scenario_id = f"sample_{index:03d}"
        weekly_hours = 2 + index % 3
        total_hours = weekly_hours * 4
        for view_id, view_name in VIEWS:
            # All materials below are fictional fixtures, not real recommendations.
            resources = [{"resource_id": f"DEMO_{i}", "title": f"가상 학습자료 {i}", "cost_krw": 0,
                          "is_fictional": True} for i in range(1, 4)]
            request = {
                "task": "create_roadmap",
                "goal": f"{domains[(index-1)%5]} 학습 시제품 만들기",
                "current_level": "Python 기초 경험, AI 개발 처음",
                "duration_weeks": 4,
                "weekly_hours": weekly_hours,
                "budget_krw": 50000,
                "perspective": view_name,
                "resources": resources,
                "support": {"status": "확인 필요", "deduct_from_cost": False},
                "sample_notice": "연결 시험 전용 가상 사례와 가상 자료",
            }
            if view_id == "cost":
                allocation = [0.30, 0.30, 0.25, 0.15]
                approach = "제공된 무료 자료를 활용해 학습한다."
            elif view_id == "time":
                allocation = [0.15, 0.20, 0.45, 0.20]
                approach = "핵심 기능 하나로 범위를 좁혀 순서대로 학습한다."
            else:
                allocation = [0.15, 0.25, 0.40, 0.20]
                approach = "가상 업무 입력으로 작은 실습을 반복한다."
            hours = [round(total_hours * fraction, 2) for fraction in allocation[:3]]
            hours.append(round(total_hours - sum(hours), 2))
            deliverables = ["기초 개념 요약", "핵심 처리 흐름도", "실행 가능한 최소 시제품", "고정 입력 시험 결과표"]
            stages = []
            for position, name in enumerate(STAGES):
                stages.append({
                    "stage": position + 1, "name": name,
                    "hours": hours[position], "cost_krw": 0,
                    "activity_type": "external_resource" if position < 2 else "practice",
                    "resource_ids": [f"DEMO_{position+1}"] if position < 2 else [],
                    "activity": f"{request['goal']}: {approach} {deliverables[position]}을 작성한다.",
                    "deliverable": deliverables[position],
                    "completion_criterion": f"{deliverables[position]}을 저장하고 확인 항목을 기록했다.",
                })
            answer = {"perspective": view_name, "stages": stages, "total_hours": total_hours,
                      "total_cost_krw": 0, "confirmation_needed": ["교육 지원 조건 확인"],
                      "sample_notice": "형식 시험용 정답이며 교육적 품질은 검토되지 않았습니다."}
            rows.append({
                "record_id": f"{scenario_id}_{view_id}", "scenario_id": scenario_id,
                "task_type": "create_roadmap", "perspective": view_id,
                "is_synthetic_sample": True, "review_status": "unreviewed",
                "messages": [{"role": "system", "content": SYSTEM},
                             {"role": "user", "content": json.dumps(request, ensure_ascii=False)},
                             {"role": "assistant", "content": json.dumps(answer, ensure_ascii=False)}],
            })
    return rows


def validate(rows):
    ids = set()
    groups = {}
    for row in rows:
        assert row["record_id"] not in ids, "duplicate record ID"
        ids.add(row["record_id"])
        assert row["is_synthetic_sample"] is True
        messages = row["messages"]
        assert [m["role"] for m in messages] == ["system", "user", "assistant"]
        request, answer = (json.loads(m["content"]) for m in messages[1:])
        stages = answer["stages"]
        assert [s["name"] for s in stages] == STAGES
        assert abs(sum(s["hours"] for s in stages) - answer["total_hours"]) < 1e-6
        assert answer["total_hours"] <= request["weekly_hours"] * request["duration_weeks"]
        assert sum(s["cost_krw"] for s in stages) == answer["total_cost_krw"] <= request["budget_krw"]
        available = {r["resource_id"] for r in request["resources"]}
        assert all(set(s["resource_ids"]) <= available for s in stages)
        groups.setdefault(row["scenario_id"], []).append(row)
    assert len(groups) == 20 and all(len(v) == 3 for v in groups.values())
    return groups


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    output = args.project_root.resolve() / "data" / "sample"
    # Exclusive directory creation prevents accidental replacement of existing samples.
    if output.exists():
        raise SystemExit(f"Refusing to overwrite existing sample folder: {output}")
    rows = build_rows()
    groups = validate(rows)
    keys = sorted(groups)
    random.Random(42).shuffle(keys)
    split_ids = {"train": keys[2:], "validation": keys[:1], "test": keys[1:2]}
    assert not (set(split_ids["train"]) & set(split_ids["validation"]))
    assert not (set(split_ids["train"]) & set(split_ids["test"]))
    assert not (set(split_ids["validation"]) & set(split_ids["test"]))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir(exist_ok=False)
    write_jsonl(output / "raw" / "dataset.jsonl", rows)
    manifest = {"purpose": "synthetic wiring test only; not training-quality evidence",
                "seed": 42, "split_group": "scenario_id", "splits": {}}
    for name, scenario_ids in split_ids.items():
        subset = [row for key in scenario_ids for row in groups[key]]
        # Keep audit metadata separately; training export contains messages only.
        path = output / ("eval" if name == "test" else "processed") / f"{name}.jsonl"
        write_jsonl(path, [{"messages": r["messages"]} for r in subset])
        write_jsonl(output / "metadata" / f"{name}.jsonl", subset)
        manifest["splits"][name] = {"rows": len(subset), "scenario_ids": scenario_ids,
                                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        print(f"{name}: {len(subset)} rows / {len(scenario_ids)} scenarios")
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved to: {output}")
    print("PASS: schema, budget/time sums, resource IDs, scenario separation")
    print("SAMPLE ONLY. No GPU, database or network calls were made.")


if __name__ == "__main__":
    main()
