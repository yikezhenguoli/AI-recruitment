#!/usr/bin/env python3
"""阶段四：强制经历拆解。

读取各批次的原始中间结构，剥离内部事实句元数据后写出：
  dataset/resumes/resume_experiences.jsonl        正式经历数据
  dataset/metadata/experience_facts.jsonl        内部事实句索引（供问题生成使用）

用法： python3 scripts/extract_experiences.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib import config, pipeline  # noqa: E402
from lib.common import log, read_jsonl  # noqa: E402


def main() -> None:
    pipeline.materialize()
    p = pipeline.paths()
    resumes = read_jsonl(p["resumes"])
    exps = read_jsonl(p["experiences"])
    facts = read_jsonl(config.abspath("dataset/metadata/experience_facts.jsonl"))
    by_rid = {r["resume_id"]: r for r in resumes}
    assert len({e["experience_id"] for e in exps}) == len(exps), "经历 ID 存在重复"
    assert len(facts) == len(exps), "事实句索引与经历数量不一致"
    for e in exps:
        assert e["resume_id"] in by_rid, f"孤立经历: {e['experience_id']}"
        assert e["original_content"] in by_rid[e["resume_id"]]["resume_text"], \
            f"经历原文无法追溯到简历正文: {e['experience_id']}"
        assert e["original_content"], f"空原文: {e['experience_id']}"
        assert e["experience_type"] in {
            "education", "internship", "work_experience", "project_experience",
            "achievement", "skill_application", "research", "competition"}, \
            f"非法经历类型: {e['experience_type']}"
    from collections import Counter
    log(f"经历拆解完成：{len(exps)} 个经历单元，类型分布 "
        f"{dict(Counter(e['experience_type'] for e in exps))}")
    log("关联校验通过：resume_id → experience_id → original_content → resume_text 全部可追溯")


if __name__ == "__main__":
    main()
