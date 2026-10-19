"""Local candidate versions, human rating history and named Markdown reports."""
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone
import uuid
import dashboard_store
from contextlib import closing, contextmanager



@contextmanager
def version_guard(folder):
    import os
    folder.mkdir(parents=True,exist_ok=True)
    with (folder/"candidate_versions.lock").open("a+b") as guard:
        if os.name=="nt":
            import msvcrt
            if guard.seek(0,2)==0:
                guard.write(b"0")
                guard.flush()
            guard.seek(0)
            msvcrt.locking(guard.fileno(),msvcrt.LK_LOCK,1)
        else:
            import fcntl
            fcntl.flock(guard,fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name=="nt":
                guard.seek(0)
                msvcrt.locking(guard.fileno(),msvcrt.LK_UNLCK,1)
            else:
                fcntl.flock(guard,fcntl.LOCK_UN)


def catalog(root, precision=None):
    groups = {}
    reports=[]
    for path in sorted((root/"reports").glob("smoke_compare_*/comparison.json")):
        report = json.loads(path.read_text(encoding="utf-8"))
        q=report.get("quantization",{})
        if precision=="bf16" and not (q.get("load_in_4bit") is False and q.get("dtype")=="bfloat16"):
            continue
        if precision=="4bit" and not q.get("load_in_4bit"):
            continue
        manifest = report.get("factory_manifest", {})
        weight = manifest.get("weight_id")
        if weight:
            reports.append((path,report,manifest,weight))
    latest_sets={}
    for path,report,manifest,weight in reports:
        if weight not in latest_sets or report["created_at"]>latest_sets[weight][0]:
            latest_sets[weight]=(report["created_at"],report.get("test_sha256"),report.get("quantization"))
    for path,report,manifest,weight in reports:
        if report.get("test_sha256")==latest_sets[weight][1] and report.get("quantization")==latest_sets[weight][2]:
            group = groups.setdefault(weight, {"manifest":manifest, "cases":{}})
            key = report["case_index"]
            if key not in group["cases"] or report["created_at"] > group["cases"][key][1]["created_at"]:
                group["cases"][key] = (path, report)
    path = root/"reports/candidate_versions.json"
    try:cached_versions=json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError,ValueError):cached_versions={}
    if all(weight in cached_versions for weight in groups):
        for weight,group in groups.items():group['version']=cached_versions[weight]
        return groups
    with dashboard_store.version_lock(root), version_guard(path.parent):
        versions = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        original=dict(versions)
        for weight, group in sorted(groups.items(), key=lambda item:(item[1]["manifest"]["run_id"], item[1]["manifest"]["trained_epoch"])):
            if weight not in versions:
                versions[weight] = max(versions.values(), default=0)+1
            group["version"] = versions[weight]
        path.parent.mkdir(parents=True, exist_ok=True)
        if versions!=original or not path.exists():
            temporary = path.with_name(path.name+"."+uuid.uuid4().hex+".tmp")
            temporary.write_text(json.dumps(versions, indent=2), encoding="utf-8")
            temporary.replace(path)
    return groups


def ratings(root, weight):
    latest = {}
    for f in (root/"reports/human_evaluations").glob("*.json"):
        entry = json.loads(f.read_text(encoding="utf-8"))
        if entry.get("weight_id") != weight or "scores" not in entry:
            continue
        person = entry["evaluator"]
        if person not in latest or entry["created_at"] > latest[person]["created_at"]:
            latest[person] = entry
    return list(latest.values())


def title(root, weight, group):
    score = case_summary(root,weight,group)["average"]
    return f"v{group['version']}_" + (f"{score:.1f}(5점 만점)" if score is not None else "평가대기")


def case_signature(report):
    keys=("model","quantization","messages","generation","test_sha256","case_index","adapter_sha256")
    payload={k:report.get(k) for k in keys}
    payload["answer"]=report["tuned"]["text"]
    return hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


_rating_cache=globals().get("_rating_cache",{})

def case_ratings(root,weight,group,evaluator=None):
    latest={}
    entries=[]
    import time
    cache_key=(str(Path(root).resolve()),dashboard_store.database_key(root),weight)
    cached=_rating_cache.get(cache_key)
    if cached is None or time.monotonic()-cached[0]>10:
        with closing(dashboard_store.connect(root)) as connection:
            if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='case_evaluations'").fetchone():
                entries=[json.loads(row[0]) for row in connection.execute("SELECT payload FROM case_evaluations WHERE weight_id=?",(weight,))]
        if len(_rating_cache)>128:_rating_cache.clear()
        _rating_cache[cache_key]=(time.monotonic(),entries)
    else:
        entries=list(cached[1])
    for f in (root/"reports/human_evaluations").glob("*.json"):
        entries.append(json.loads(f.read_text(encoding="utf-8")))
    for e in entries:
        if e.get("schema")!="per_case_v1" or e.get("weight_id")!=weight:
            continue
        case=e["case_index"]
        if case not in group["cases"] or e["case_signature"]!=case_signature(group["cases"][case][1]):
            continue
        if evaluator is not None and e["evaluator"]!=evaluator:
            continue
        key=(e["evaluator"],case)
        if key not in latest or e["created_at"]>latest[key]["created_at"]:
            latest[key]=e
    return list(latest.values())


def case_summary(root,weight,group,evaluator=None):
    by_case={}
    for entry in case_ratings(root,weight,group,evaluator):
        by_case.setdefault(entry["case_index"],[]).append(entry["score"])
    means={case:sum(scores)/len(scores) for case,scores in by_case.items()}
    return {"scores":means,"rated":len(means),"total":len(group["cases"]),
            "average":sum(means.values())/len(means) if means else None}


def save_case_rating(root,weight,group,case,evaluator,score,note=""):
    if not evaluator.strip() or type(score) is not int or not 1<=score<=5 or case not in group["cases"]:
        raise ValueError("평가자와 이 입력에 대한 1~5점 점수를 선택하세요.")
    path,report=group["cases"][case]
    entry=dict(schema="per_case_v1",evaluation_id=str(uuid.uuid4()),created_at=datetime.now(timezone.utc).isoformat(),
        weight_id=weight,run_id=group["manifest"]["run_id"],version=group["version"],case_index=case,
        evaluator=evaluator.strip(),score=score,note=note,case_signature=case_signature(report),
        report=str(path.relative_to(root)),report_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    folder=root/"reports"
    folder.mkdir(parents=True,exist_ok=True)
    with closing(dashboard_store.connect(root)) as connection:
        connection.execute("CREATE TABLE IF NOT EXISTS case_evaluations (evaluation_id TEXT PRIMARY KEY, weight_id TEXT NOT NULL, case_index INTEGER NOT NULL, evaluator TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL)")
        connection.execute("CREATE INDEX IF NOT EXISTS evaluations_weight ON case_evaluations(weight_id)")
        connection.execute("INSERT INTO case_evaluations VALUES (?,?,?,?,?,?)",(entry["evaluation_id"],weight,case,evaluator.strip(),entry["created_at"],json.dumps(entry,ensure_ascii=False)))
        connection.commit()
    _rating_cache.clear()
    return entry


def save_rating(root, weight, group, evaluator, scores, note):
    if not evaluator.strip() or not note.strip() or not scores or any(not 1<=v<=5 for v in scores.values()):
        raise ValueError("평가자·평가 근거와 1~5점 항목별 점수를 입력하세요.")
    entry = dict(evaluation_id=str(uuid.uuid4()), created_at=datetime.now(timezone.utc).isoformat(),
        weight_id=weight, run_id=group["manifest"]["run_id"], version=group["version"],
        evaluator=evaluator.strip(), scores=scores, average=sum(scores.values())/len(scores), note=note,
        reports=[dict(path=str(p.relative_to(root)), sha256=hashlib.sha256(p.read_bytes()).hexdigest())
                 for p,d in group["cases"].values()])
    folder=root/"reports/human_evaluations"
    folder.mkdir(parents=True,exist_ok=True)
    with (folder/(entry["evaluation_id"]+".json")).open("x",encoding="utf-8") as stream:
        json.dump(entry,stream,ensure_ascii=False,indent=2)
    dashboard_store.persist(root,folder/(entry["evaluation_id"]+".json"))
    return entry


def render(root, weight, group):
    import yaml
    heading=title(root,weight,group)
    m=group["manifest"]
    config_path=root/"reports/run_configs"/(m["run_id"]+".yaml")
    cfg=yaml.safe_load(config_path.read_text(encoding="utf-8")) if config_path.exists() else None
    rows=["# "+heading,"",f"- 모델: {m['model']['base_model_id']}",f"- 모델 revision: {m['model']['revision']}",
          "- 학습 구분: "+("샘플 시험" if m.get("is_sample",True) else "실제 데이터 학습"),
          "- 학습 데이터 해시: "+str(m.get("dataset",{}).get("train",{}).get("sha256","이전 보고서 · 실행 설정 참조")),
          "- 검증 데이터 해시: "+str(m.get("dataset",{}).get("validation",{}).get("sha256","이전 보고서 · 실행 설정 참조")),
          f"- run_id: {m['run_id']}",f"- weight_id: {weight}",f"- 저장 에포크: {m['trained_epoch']}",
          "- 평균: 각 입력의 최신 휴먼 점수를 입력별 동일 비중으로 평균; 미평가 입력 제외", "",
          "## 학습 파라미터", ""]
    rows += ["```yaml",yaml.safe_dump(cfg,allow_unicode=True,sort_keys=False),"```",""] if cfg else ["실제 실행 설정을 아직 가져오지 않았습니다.",""]
    rows += ["## 휴먼 평가",""]
    summary=case_summary(root,weight,group)
    rows += [f"평가 완료: {summary['rated']}/{summary['total']}개 · "+("전체 평가 완료" if summary['rated']==summary['total'] else "일부만 평가한 임시 평균"),""]
    for entry in sorted(case_ratings(root,weight,group),key=lambda e:(e["case_index"],e["evaluator"])):
        rows += [f"- 입력 {entry['case_index']+1} · {entry['evaluator']}: {entry['score']}/5 · {entry['note']}",""]
    import ai_evaluation
    ai=ai_evaluation.group_summary(root,weight,group)
    human_average=f"{summary['average']:.2f} / 5" if summary['average'] is not None else "평가 전"
    ai_average=f"{ai['average']:.2f} / 5" if ai['average'] is not None else "평가 전"
    rows += ["## 사람·AI 평균 비교","","| 평가 | 평균 | 평가 건수 |","| --- | --- | --- |",
             f"| 사람 | {human_average} | {summary['rated']}/{summary['total']} |",
             f"| AI | {ai_average} | {ai['rated']}/{ai['total']} |","",
             "AI 모델: "+ai['model'],"각 입력을 동일 비중으로 평균하며 미평가·판단 불가 점수는 제외합니다. 사람과 AI 점수는 합산하지 않습니다.",""]
    for case,(path,d) in sorted(group["cases"].items()):
        rows += [f"## 입력 {case+1}","","### 입력","","```json",json.dumps(d["messages"],ensure_ascii=False,indent=2),"```",""]
        for key,name in (("base","기본 모델"),("tuned","어댑터 적용")):
            rows += [f"### {name}","",f"생성 {d[key]['tokens']}토큰 · 길이 제한 도달: {d[key]['hit_token_limit']}","","```text",d[key]["text"],"```",""]
        entry=ai_evaluation.latest(root,weight,d,ai["model"])
        rows += ["### AI 보조 평가", ""]
        if entry:
            score=f"{entry['average']:.2f} / 5" if entry['average'] is not None else "판단 불가"
            rows += ["AI 평균: "+score,"",entry["review"]["summary"],"", "| 항목 | 점수 | 근거 |","| --- | --- | --- |"]
            for name,label in ai_evaluation.DIMENSIONS.items():
                item=entry["review"][name]
                reason=item["reason"].replace("|","\\|").replace("\n"," ")
                rows.append(f"| {label} | {item['score'] if item['score'] is not None else '해당 없음'} | {reason} |")
            rows += ["",*["- "+issue for issue in entry["review"]["issues"]],""]
        else:
            rows += ["AI 평가 대기", ""]
    return "\n".join(rows)
