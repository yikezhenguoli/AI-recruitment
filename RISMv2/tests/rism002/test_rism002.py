#!/usr/bin/env python3
"""RISM-002 完整测试集（unittest，纯标准库）。

覆盖需求 §11 的全部 15 项，另加 5 项补充测试。
所有写操作都发生在临时目录，绝不修改 RISMv1 / RISMv2 的正式数据、审核文件与模型权重。

运行：
    python3 -m unittest discover -s tests/rism002 -v
    python3 tests/rism002/test_rism002.py -v
"""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from rism002.analyzers import candidate_builder  # noqa: E402
from rism002.parsers import jsonl as parser  # noqa: E402
from rism002.schemas import validator as schema  # noqa: E402
from rism002.utils import core  # noqa: E402
from rism002.validators import dataset_validator, ontology as ontology_validator  # noqa: E402
from scripts.rism002 import build_dataset  # noqa: E402

D1 = "test_performance_optimization"
D2 = "test_evidence_attribution"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _approved_review(cfg: dict[str, Any], reason: str = "人工逐条核验通过") -> dict[str, Any]:
    return core.review_block(source="human", status="approved",
                             annotator_id="human_reviewer_test",
                             reviewed_at=core.now_iso(), review_reason=reason, cfg=cfg)


def _direction(did: str, name: str, parents: list[str], cfg: dict[str, Any],
               *, related: list[str] | None = None, status: str = "approved") -> dict[str, Any]:
    return {
        "direction_id": did, "direction_name": name,
        "parent_dimensions": parents,
        "definition": "验证候选人在该方向上的具体判断依据与实施过程，用于测试多对多维度关联",
        "inclusion_criteria": ["经历中明确出现该方向相关主张"],
        "exclusion_criteria": ["仅出现指标名称而无实际行为"],
        "evidence_types": ["baseline_metrics", "process_description"],
        "typical_trigger_claims": ["响应时间降低", "归因说明"],
        "related_directions": related or [],
        "applicable_position_families": [],
        "status": status, "version": cfg["ontology_version"],
        "origin": {"source": "human_curated_test_fixture"},
        "review": _approved_review(cfg, "人工确认方向定义与边界"),
    }


def make_cfg(tmp: Path) -> dict[str, Any]:
    """构造隔离配置：源数据指向真实只读文件，所有输出落在临时目录。"""
    cfg = json.loads((ROOT / "configs/rism002.json").read_text(encoding="utf-8"))
    cfg["_root"] = str(tmp)
    cfg["_config_path"] = str(tmp / "config.json")
    for k, v in list(cfg["source"].items()):
        cfg["source"][k] = str(ROOT / v)
    cfg["paths"]["taxonomy"] = str(ROOT / "configs/rism002_taxonomy.json")
    cfg["paths"]["competencies"] = str(tmp / "competencies.json")
    cfg["paths"]["directions"] = str(tmp / "directions.json")
    cfg["paths"]["source_manifest"] = str(tmp / "absent_manifest.json")
    cfg["paths"]["baseline_manifest"] = str(
        ROOT / "outputs/rism002/rism001_baseline_manifest.json")
    for d in ("data/ontology", "data/intermediate", "data/annotations",
              "data/processed", "outputs"):
        (tmp / d).mkdir(parents=True, exist_ok=True)
    return cfg


def make_sample(cfg: dict[str, Any], *, n_claims: int = 2, n_gaps: int = 2,
                n_strategies: int = 2, label_d2: str = "unknown",
                claim_source: str | None = None) -> dict[str, Any]:
    """基于真实源经历构造一份完全合法的样本（可按需变异制造错误）。"""
    idx = parser.load_source_index(cfg)
    e = idx["experiences"][0]
    r = idx["by_resume"][e["resume_id"]]
    text = e["original_content"]
    sentences = candidate_builder.sentence_spans(text)
    claims, gaps, strategies = [], [], []
    for n in range(1, n_claims + 1):
        sentence, s, t = sentences[(n - 1) % len(sentences)]
        claims.append({
            "claim_id": f"CLM_T{n:02d}", "experience_id": e["experience_id"],
            "resume_id": e["resume_id"],
            "claim_type": "responsibility",
            "claim_text": sentence.rstrip("。；"),
            "source_text": claim_source if claim_source is not None else sentence,
            "source_span": {"start_offset": s, "end_offset": t},
            "review": _approved_review(cfg),
        })
    for n in range(1, n_gaps + 1):
        gaps.append({
            "gap_id": f"GAP_T{n:02d}", "experience_id": e["experience_id"],
            "resume_id": e["resume_id"],
            "related_claim_ids": [c["claim_id"] for c in claims[:2]],
            "gap_type": "missing_process",
            "description": "简历未提供该过程的执行细节。此项仅表示信息不足，不代表候选人不具备相关能力，也不代表经历存在造假。",
            "source_text": None, "source_span": None,
            "review": _approved_review(cfg),
        })
    for n in range(1, n_strategies + 1):
        did = D1 if n % 2 else D2
        strategies.append({
            "strategy_id": f"STR_T{n:02d}", "experience_id": e["experience_id"],
            "dimension": "technical_implementation" if n % 2 else "data_evidence",
            "direction_id": did,
            "direction_name": "性能优化" if n % 2 else "证据归因",
            "trigger_claim_ids": [claims[0]["claim_id"]],
            "trigger_gap_ids": [gaps[0]["gap_id"]] if gaps else [],
            "rationale": "该经历存在可核实的关键主张与信息缺口",
            "investigation_goal": "核实实施过程与指标依据",
            "evidence_to_obtain": ["实施过程", "指标口径"],
            "risk_signals": [], "expected_answer_signals": ["应说明判断依据"],
            "follow_up_triggers": [], "strategy_type": "process_reconstruction",
            "priority": "high", "difficulty": "L3", "sequence": n,
            "prerequisites": [], "label_status": "positive",
            "review": _approved_review(cfg),
        })
    ann = [
        {"direction_id": D1, "label_status": "positive", "annotation_source": "human",
         "reviewed": True, "review_reason": "人工确认值得追问",
         "ontology_version": cfg["ontology_version"]},
        {"direction_id": D2,
         "label_status": label_d2,
         "annotation_source": "human" if label_d2 != "unknown" else None,
         "reviewed": label_d2 != "unknown",
         "review_reason": "人工确认" if label_d2 != "unknown" else "未审核，不作正负判断",
         "ontology_version": cfg["ontology_version"]},
    ]
    return {
        "sample_id": "SAMPLE_TEST_0001", "resume_id": e["resume_id"],
        "candidate_id": r["candidate_id"],
        "experience": {"experience_id": e["experience_id"],
                       "experience_type": e["experience_type"],
                       "title": e.get("title", ""), "experience_text": text},
        "job": {"target_position": r["target_position"],
                "position_family": "algorithm_and_data",
                "career_level": r["career_level"], "job_requirements": []},
        "key_claims": claims, "evidence_gaps": gaps,
        "investigation_strategies": strategies,
        "direction_annotations": ann,
        "annotation": {"annotation_source": "human", "annotation_status": "reviewed",
                       "review_workflow_status": "approved",
                       "annotator_id": "human_reviewer_test", "reviewed": True,
                       "reviewed_at": core.now_iso(),
                       "ontology_version": cfg["ontology_version"]},
    }


class RISM002TestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="rism002_test_")
        self.tmp = Path(self._tmp.name)
        self.cfg = make_cfg(self.tmp)
        core.write_json(self.tmp / "directions.json", {
            "version": self.cfg["ontology_version"],
            "directions": [
                _direction(D1, "性能优化", ["technical_implementation", "problem_solving"],
                           self.cfg, related=[D2]),
                _direction(D2, "证据归因", ["data_evidence"], self.cfg),
            ],
        })
        core.write_json(self.tmp / "competencies.json", {
            "version": self.cfg["ontology_version"],
            "competencies": [{
                "position_family": "software_development",
                "competency_id": "TEST_COMP_001",
                "competency_name": "系统实现与证据归因能力",
                "competency_definition": "考察候选人还原实施过程、给出可核对证据并说明判断依据的能力",
                "importance": "high",
                "related_direction_ids": [D1, D2],
                "version": self.cfg["ontology_version"],
                "review": _approved_review(self.cfg, "人工确认岗位能力定义"),
            }],
        })

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _v(self, samples: list[dict[str, Any]]) -> dict[str, Any]:
        return dataset_validator.validate(self.cfg, samples=samples)

    def _errs(self, *samples: dict[str, Any]) -> list[str]:
        return self._v(list(samples))["errors"]

    # ---------------------------------------------------------- 需求 §11
    def test_01_normal_data_reads(self) -> None:
        """1. 正常数据能够成功读取。"""
        for name in ("resumes", "experiences", "questions", "chains"):
            rows, errs = core.read_jsonl(core.source_path(name, self.cfg))
            self.assertFalse(errs, f"{name} 解析错误: {errs[:2]}")
            self.assertGreater(len(rows), 0, name)
        s = make_sample(self.cfg)
        self.assertEqual(schema.validate_entity(s, "sample"), [])
        self.assertTrue(self._v([s])["passed"])

    def test_02_bad_jsonl_detected(self) -> None:
        """2. 错误 JSONL 能够被识别。"""
        p = self.tmp / "bad.jsonl"
        p.write_text('{"a":1}\nnot-json\n{"b":2}\n[1,2]\n', encoding="utf-8")
        rows, errs = core.read_jsonl(p, strict=False)
        self.assertEqual(len(rows), 2)
        self.assertEqual(len(errs), 2)
        self.assertTrue(any("JSON 解析失败" in e for e in errs))
        self.assertTrue(any("顶层不是 object" in e for e in errs))
        with self.assertRaises(ValueError):
            core.read_jsonl(p, strict=True)

    def test_03_missing_required_field(self) -> None:
        """3. 缺少必需字段能够报错。"""
        bad = copy.deepcopy(make_sample(self.cfg))
        del bad["key_claims"][0]["source_text"]
        self.assertTrue(any("source_text" in e for e in schema.validate_entity(
            bad, "sample")))
        self.assertTrue(any("source_text" in e for e in self._errs(bad)))
        bad2 = copy.deepcopy(make_sample(self.cfg))
        del bad2["direction_annotations"]
        self.assertTrue(any("direction_annotations" in e for e in self._errs(bad2)))

    def test_04_duplicate_ids(self) -> None:
        """4. 重复 ID 能够报错。"""
        a, b = make_sample(self.cfg), make_sample(self.cfg)
        self.assertTrue(any("重复 sample_id" in e for e in self._errs(a, b)))
        c = copy.deepcopy(a)
        c["key_claims"][1]["claim_id"] = c["key_claims"][0]["claim_id"]
        self.assertTrue(any("重复 claim_id" in e for e in self._errs(c)))

    def test_05_invalid_resume_id(self) -> None:
        """5. 无效 resume_id 能够被识别。"""
        s = make_sample(self.cfg)
        s["resume_id"] = "RES_DOES_NOT_EXIST"
        errs = self._errs(s)
        self.assertTrue(any("引用不存在的 resume_id" in e for e in errs), errs[:3])

    def test_06_invalid_experience_id(self) -> None:
        """6. 无效 experience_id 能够被识别。"""
        s = make_sample(self.cfg)
        s["experience"]["experience_id"] = "EXP_DOES_NOT_EXIST"
        errs = self._errs(s)
        self.assertTrue(any("引用不存在的 experience_id" in e for e in errs), errs[:3])

    def test_07_missing_direction_id(self) -> None:
        """7. 不存在的 direction_id 能够被识别（含未批准方向）。"""
        s = make_sample(self.cfg)
        s["investigation_strategies"][0]["direction_id"] = "direction_not_in_catalog"
        self.assertTrue(any("引用不存在的 direction_id" in e for e in self._errs(s)))
        # 语义不同但名称相近的方向不得被静默合并：candidate 状态也不能用
        doc = core.read_json(self.tmp / "directions.json")
        doc["directions"][0]["status"] = "candidate"
        core.write_json(self.tmp / "directions.json", doc)
        s2 = make_sample(self.cfg)
        self.assertTrue(any("未批准的方向" in e for e in self._errs(s2)))

    def test_08_unreviewed_ai_labels_rejected(self) -> None:
        """8. 未审核的 AI / 规则标签不能进入正式数据集。"""
        s = make_sample(self.cfg)
        s["key_claims"][0]["review"] = core.review_block(
            source="llm", status="approved", annotator_id="gpt",
            reviewed_at=core.now_iso(), review_reason="模型自动判定", cfg=self.cfg)
        self.assertTrue(any("未通过人工审核" in e for e in self._errs(s)))
        # 构建器同样必须过滤：把 pending 规则候选放进审核目录，不应生成任何正式样本
        claim = copy.deepcopy(s["key_claims"][0])
        claim["review"] = core.review_block(source="rule_based", status="pending", cfg=self.cfg)
        core.write_jsonl(self.tmp / "data/annotations/claims.jsonl", [claim])
        result = build_dataset.build(self.cfg)
        self.assertEqual(result["sample_count"], 0)
        self.assertEqual(result["dataset_status"], "awaiting_human_review")

    def test_09_unknown_never_becomes_negative(self) -> None:
        """9. Unknown 不会被转换为 Negative；negative 必须来自人工审核。"""
        self.assertEqual(core.direction_label_default(self.cfg)["label_status"], "unknown")
        # 构建器：有已批准方向与已审核 Claim，但没有人工方向标注 → 必须补 unknown
        s = make_sample(self.cfg)
        core.write_jsonl(self.tmp / "data/annotations/claims.jsonl", s["key_claims"])
        core.write_jsonl(self.tmp / "data/annotations/evidence_gaps.jsonl", s["evidence_gaps"])
        result = build_dataset.build(self.cfg)
        self.assertEqual(result["negative_directions_created"], 0)
        self.assertGreater(result["unknown_directions_filled"], 0)
        samples, _ = core.read_jsonl(self.tmp / "data/processed/rism002_samples.jsonl")
        self.assertTrue(all(a["label_status"] == "unknown"
                            for x in samples for a in x["direction_annotations"]))
        # 校验器：unknown + reviewed=False 合法；negative 但非人工必须报错
        self.assertTrue(self._v([make_sample(self.cfg)])["passed"])
        bad = make_sample(self.cfg)
        bad["direction_annotations"][1]["label_status"] = "negative"
        bad["direction_annotations"][1]["reviewed"] = False
        bad["direction_annotations"][1]["annotation_source"] = None
        self.assertTrue(any("negative 必须由人工审核确认" in e for e in self._errs(bad)))

    def test_10_multiple_claims_per_experience(self) -> None:
        """10. 同一经历可以对应多个 Claim。"""
        s = make_sample(self.cfg, n_claims=3)
        v = self._v([s])
        self.assertTrue(v["passed"], v["errors"][:3])
        self.assertEqual(v["statistics"]["claim_count"], 3)
        self.assertEqual(len({c["experience_id"] for c in s["key_claims"]}), 1)

    def test_11_multiple_gaps_per_experience(self) -> None:
        """11. 同一经历可以对应多个 Evidence Gap。"""
        s = make_sample(self.cfg, n_gaps=3)
        v = self._v([s])
        self.assertTrue(v["passed"], v["errors"][:3])
        self.assertEqual(v["statistics"]["gap_count"], 3)
        self.assertTrue(all(g["related_claim_ids"] for g in s["evidence_gaps"]))

    def test_12_multiple_strategies_per_experience(self) -> None:
        """12. 同一经历可以对应多个追问策略。"""
        s = make_sample(self.cfg, n_strategies=3)
        v = self._v([s])
        self.assertTrue(v["passed"], v["errors"][:3])
        self.assertEqual(v["statistics"]["strategy_count"], 3)
        self.assertEqual(v["statistics"]["duplicate_strategy_count"], 0)

    def test_13_direction_multiple_parent_dimensions(self) -> None:
        """13. 一个方向可以关联多个一级维度（多对多，不强制合并）。"""
        doc = core.read_json(self.tmp / "directions.json")
        d1 = doc["directions"][0]
        self.assertEqual(len(d1["parent_dimensions"]), 2)
        self.assertEqual(schema.validate_entity(d1, "direction"), [])
        res = ontology_validator.validate(self.cfg)
        self.assertTrue(res["passed"], res["errors"][:5])
        self.assertGreaterEqual(res["statistics"].get("multi_parent_direction_count", 0), 1)
        # 循环依赖必须被识别
        doc["directions"][1]["related_directions"] = [D1]
        doc["directions"][1]["depends_on_direction_ids"] = [D1]
        doc["directions"][0]["depends_on_direction_ids"] = [D2]
        core.write_json(self.tmp / "directions.json", doc)
        cyc = ontology_validator.validate(self.cfg)
        self.assertFalse(cyc["passed"])

    def test_14_build_never_modifies_rism001_files(self) -> None:
        """14. 数据构建过程不会修改 RISM-001 文件。"""
        manifest = core.read_json(ROOT / "outputs/rism002/rism001_baseline_manifest.json")
        base_root = Path(manifest["baseline_root"])
        before = {rel: _sha(base_root / rel) for rel in manifest["files"]}
        src_before = {rel: _sha(ROOT / rel) for rel in self.cfg["readonly_assets"]
                      if (ROOT / rel).exists()}
        s = make_sample(self.cfg)
        core.write_jsonl(self.tmp / "data/annotations/claims.jsonl", s["key_claims"])
        core.write_jsonl(self.tmp / "data/annotations/evidence_gaps.jsonl", s["evidence_gaps"])
        core.write_jsonl(self.tmp / "data/annotations/strategies.jsonl",
                         s["investigation_strategies"])
        result = build_dataset.build(self.cfg)
        self.assertEqual(result["sample_count"], 1)
        after = {rel: _sha(base_root / rel) for rel in manifest["files"]}
        self.assertEqual(before, after, "RISMv1 冻结基线被修改")
        self.assertEqual(src_before, {rel: _sha(ROOT / rel) for rel in src_before},
                         "RISMv2 只读源资产被修改")

    def test_15_no_model_training(self) -> None:
        """15. 不执行任何模型训练（AST 级检查真实 import / 训练调用）。"""
        banned_modules = {"torch", "tensorflow", "transformers",
                          "sentence_transformers", "pytorch_lightning"}
        hits: list[str] = []
        for base in (ROOT / "rism002", ROOT / "scripts/rism002"):
            for f in sorted(base.rglob("*.py")):
                tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for a in node.names:
                            if a.name.split(".")[0] in banned_modules:
                                hits.append(f"{f}:import {a.name}")
                    elif isinstance(node, ast.ImportFrom):
                        if (node.module or "").split(".")[0] in banned_modules:
                            hits.append(f"{f}:from {node.module}")
                    elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                        attr = node.func.attr
                        owner = (node.func.value.id
                                 if isinstance(node.func.value, ast.Name) else "")
                        if attr in ("backward", "step") or \
                                (attr == "train" and owner in ("model", "net")) or attr == "fit":
                            hits.append(f"{f}:{owner}.{attr}()")
        self.assertEqual(hits, [])
        self.assertFalse(self.cfg["llm"]["enabled"])
        self.assertFalse(list((ROOT / "outputs/rism002").glob("*.pth")))

    # ---------------------------------------------------------- 补充测试
    def test_16_claim_source_text_must_be_real_substring(self) -> None:
        s = make_sample(self.cfg, claim_source="这句话并不在简历原文中")
        self.assertTrue(any("source_text 不是经历原文子串" in e for e in self._errs(s)))

    def test_17_gap_must_link_claim_and_not_allege_fraud(self) -> None:
        s = make_sample(self.cfg)
        s["evidence_gaps"][0]["related_claim_ids"] = ["CLM_NOT_EXIST"]
        self.assertTrue(any("关联了不存在的 Claim" in e for e in self._errs(s)))
        s2 = make_sample(self.cfg)
        s2["evidence_gaps"][0]["description"] = "该数据疑似造假，需要核实"
        self.assertTrue(any("不得直接断定经历造假" in e for e in self._errs(s2)))

    def test_18_strategy_must_trace_to_claim_or_gap(self) -> None:
        s = make_sample(self.cfg)
        s["investigation_strategies"][0]["trigger_claim_ids"] = []
        s["investigation_strategies"][0]["trigger_gap_ids"] = []
        self.assertTrue(any("策略未追溯到任何 Claim 或 Gap" in e for e in self._errs(s)))

    def test_19_ontology_version_consistency(self) -> None:
        s = make_sample(self.cfg)
        s["annotation"]["ontology_version"] = "WRONG_VERSION"
        self.assertTrue(any("顶层 ontology_version 不一致" in e for e in self._errs(s)))

    def test_20_llm_and_privacy_defaults(self) -> None:
        cfg = core.load_config()
        self.assertFalse(cfg["llm"]["enabled"])
        self.assertTrue(cfg["llm"]["require_explicit_confirm"])
        self.assertEqual(cfg["review"]["default_label_status"], "unknown")
        self.assertFalse(cfg["review"]["auto_approve"])
        self.assertTrue(cfg["privacy"]["id_only_in_reports"])
        self.assertFalse(cfg["privacy"]["log_resume_text"])
        self.assertEqual(cfg["review"]["approved_requires_sources"], ["human"])
        self.assertEqual(core.redact("联系 13812345678 或 a@b.com"),
                         "联系 [PHONE] 或 [EMAIL]")


if __name__ == "__main__":
    unittest.main(verbosity=2)
