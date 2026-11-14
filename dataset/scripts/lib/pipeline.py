"""分批生成编排核心：阶段闸门、批次状态、断点续跑、最终合并。

批次文件命名： dataset/batches/<stage>_<batch:03d>_raw.json / _qa.json
每个批次独立写入、独立校验；已存在且通过校验的批次不会被覆盖。
"""
from __future__ import annotations

import glob
import os
from typing import Any

from . import config
from .common import (load_state, log, read_json, read_jsonl, save_state,
                     strip_tail_punct, write_json, write_jsonl)
from .question_engine import build_for_resume
from .resume_builder import build_one

GC = config.get_config("generation_config")
ROOT = config.ROOT
BATCH_DIR = config.abspath(GC["checkpoint"]["batch_dir"])
PLAN_FILE = config.abspath(GC["checkpoint"]["plan_file"])
PILOT_FILE = config.abspath("dataset/metadata/pilot_ids.json")
ACCEPT_FILE = config.abspath("dataset/metadata/acceptance.json")


def _p(pid: str) -> str:
    return config.abspath(pid)


def paths() -> dict[str, str]:
    return {k: _p(v) for k, v in GC["paths"].items()}


# ---------------------------------------------------------------- 计划
def ensure_plan() -> list[dict[str, Any]]:
    from . import plan as plan_lib
    pl = plan_lib.load_plan(PLAN_FILE)
    plan_lib.validate_plan(pl)
    return pl


def ensure_pilot_ids() -> list[str]:
    from . import plan as plan_lib
    if not os.path.exists(PILOT_FILE):
        pl = ensure_plan()
        ids = plan_lib.select_pilot_ids(pl)
        write_json(PILOT_FILE, {"stage": "pilot", "size": len(ids), "ids": ids})
        log(f"试验样本分层抽样完成：{len(ids)} 个 ID（全量计划的子集）")
    return read_json(PILOT_FILE)["ids"]


def target_ids(stage: str) -> list[dict[str, Any]]:
    pl = ensure_plan()
    by_id = {x["resume_id"]: x for x in pl}
    if stage == "pilot":
        return [by_id[i] for i in ensure_pilot_ids()]
    if stage == "full":
        if not os.path.exists(ACCEPT_FILE):
            raise RuntimeError(
                "阶段闸门未通过：第三阶段人工验收尚未确认。\n"
                "请先审阅 reports/ 下的抽样报告，确认后运行 "
                "`python3 scripts/run_pipeline.py --accept` 生成验收标记，再执行 --stage full。"
            )
        done = staged_resume_ids()
        return [x for x in pl if x["resume_id"] not in done]
    raise ValueError(f"未知阶段: {stage}")


def staged_resume_ids() -> set[str]:
    ids: set[str] = set()
    for f in glob.glob(os.path.join(BATCH_DIR, "*_raw.json")):
        try:
            for r in read_json(f)["resumes"]:
                ids.add(r["resume_id"])
        except (KeyError, ValueError):
            continue
    return ids


def batch_files(stage: str, kind: str) -> list[str]:
    return sorted(glob.glob(os.path.join(BATCH_DIR, f"{stage}_*_{kind}.json")))


# ---------------------------------------------------------------- 阶段二：简历 + 经历
def stage_resumes(stage: str, batch_size: int | None = None, force: bool = False) -> dict[str, Any]:
    import json
    slots = target_ids(stage)
    size = batch_size or GC["batch_size"]
    os.makedirs(BATCH_DIR, exist_ok=True)
    state = load_state()
    state["stage"] = stage
    total_new, total_skip, failed = 0, 0, []
    chunks = [slots[i:i + size] for i in range(0, len(slots), size)]
    for bi, chunk in enumerate(chunks):
        bf = os.path.join(BATCH_DIR, f"{stage}_{bi:03d}_raw.json")
        key = os.path.basename(bf)
        if os.path.exists(bf) and not force and state["batches"].get(key, {}).get("status") == "ok":
            total_skip += len(chunk)
            continue
        resumes, exps = [], []
        for slot in chunk:
            try:
                r, e = build_one(slot)
                # 生成时即做基本自检
                for x in e:
                    assert x["original_content"] in r["resume_text"], "经历原文未进入简历正文"
                    assert x["experience_id"].startswith("EXP_"), "经历 ID 格式错误"
                resumes.append(r)
                exps.extend(e)
            except Exception as exc:  # noqa: BLE001
                failed.append({"resume_id": slot["resume_id"], "error": str(exc)})
        with open(bf, "w", encoding="utf-8") as fh:
            json.dump({"stage": stage, "batch": bi, "resumes": resumes,
                       "experiences": exps}, fh, ensure_ascii=False)
        state["batches"][key] = {"status": "ok" if not failed else "partial",
                                 "resumes": len(resumes), "experiences": len(exps)}
        total_new += len(resumes)
        log(f"[{stage}] 批次 {bi:03d} 生成简历 {len(resumes)} 份 / 经历 {len(exps)} 条")
    state["failed_resume_ids"] = [x["resume_id"] for x in failed]
    state["completed_resume_ids"] = sorted(staged_resume_ids())
    save_state(state)
    return {"stage": stage, "new": total_new, "skipped": total_skip,
            "failed": failed, "batches": len(chunks)}


# ---------------------------------------------------------------- 阶段三/四：问题 + 追问链
def stage_qa(stage: str, force: bool = False) -> dict[str, Any]:
    import json
    state = load_state()
    n_q = n_c = n_skip = 0
    for raw in sorted(glob.glob(os.path.join(BATCH_DIR, f"{stage}_*_raw.json"))):
        qa = raw.replace("_raw.json", "_qa.json")
        key = os.path.basename(qa)
        if os.path.exists(qa) and not force and state["batches"].get(key, {}).get("status") == "ok":
            d = read_json(qa)
            n_q += len(d["questions"])
            n_c += len(d["chains"])
            n_skip += 1
            continue
        data = read_json(raw)
        resumes = data["resumes"]
        exps = data["experiences"]
        by_rid: dict[str, list[dict[str, Any]]] = {}
        for e in exps:
            by_rid.setdefault(e["resume_id"], []).append(e)
        questions, chains = [], []
        for r in resumes:
            es = by_rid.get(r["resume_id"], [])
            facts_map = {e["experience_id"]: e["_facts"] for e in es}
            q, c = build_for_resume(r, es, facts_map)
            questions.extend(q)
            chains.extend(c)
        with open(qa, "w", encoding="utf-8") as fh:
            json.dump({"stage": stage, "questions": questions, "chains": chains,
                       "resume_count": len(resumes)}, fh, ensure_ascii=False)
        state["batches"][key] = {"status": "ok", "questions": len(questions), "chains": len(chains)}
        n_q += len(questions)
        n_c += len(chains)
        log(f"[{stage}] {os.path.basename(qa)} 生成问题 {len(questions)} 道 / 追问链 {len(chains)} 条")
    save_state(state)
    return {"questions": n_q, "chains": n_c, "skipped_batches": n_skip}


# ---------------------------------------------------------------- 合并落盘
def materialize() -> dict[str, Any]:
    p = paths()
    resumes: list[dict[str, Any]] = []
    exps: list[dict[str, Any]] = []
    facts: list[dict[str, Any]] = []
    questions: list[dict[str, Any]] = []
    chains: list[dict[str, Any]] = []
    seen_r, seen_e = set(), set()
    for raw in sorted(glob.glob(os.path.join(BATCH_DIR, "*_raw.json"))):
        d = read_json(raw)
        for r in d["resumes"]:
            if r["resume_id"] in seen_r:
                continue
            seen_r.add(r["resume_id"])
            resumes.append(r)
        for e in d["experiences"]:
            if e["experience_id"] in seen_e:
                continue
            seen_e.add(e["experience_id"])
            facts.append({"experience_id": e["experience_id"], "resume_id": e["resume_id"],
                          "facts": e.pop("_facts", [])})
            exps.append(e)
    for qa in sorted(glob.glob(os.path.join(BATCH_DIR, "*_qa.json"))):
        d = read_json(qa)
        questions.extend(d["questions"])
        chains.extend(d["chains"])
    resumes.sort(key=lambda x: x["resume_id"])
    exps.sort(key=lambda x: x["experience_id"])
    facts.sort(key=lambda x: x["experience_id"])
    questions.sort(key=lambda x: x["question_id"])
    chains.sort(key=lambda x: x["chain_id"])
    write_jsonl(p["resumes"], resumes)
    write_jsonl(p["experiences"], exps)
    write_jsonl(_p("dataset/metadata/experience_facts.jsonl"), facts)
    write_jsonl(p["questions"], questions)
    write_jsonl(p["chains"], chains)
    log(f"合并落盘：简历 {len(resumes)} / 经历 {len(exps)} / 问题 {len(questions)} / 追问链 {len(chains)}")
    return {"resumes": len(resumes), "experiences": len(exps),
            "questions": len(questions), "chains": len(chains)}


def mark_acceptance(note: str = "人工验收确认") -> str:
    import datetime
    write_json(ACCEPT_FILE, {"confirmed": True, "note": note,
                             "confirmed_at": datetime.datetime.now().isoformat(timespec="seconds")})
    log("已记录第三阶段人工验收确认标记")
    return ACCEPT_FILE
