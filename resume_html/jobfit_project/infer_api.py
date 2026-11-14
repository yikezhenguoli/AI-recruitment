#!/usr/bin/env python3
"""Expose the existing JobFit checkpoint through the TTC matcher CLI contract."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from jobfit.inference import JobFitPredictor  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--text-file", required=True)
    parser.add_argument("--jd-file")
    return parser.parse_args()


def softmax(values: np.ndarray) -> np.ndarray:
    shifted = values - values.max()
    exp = np.exp(shifted)
    return exp / exp.sum()


def main() -> int:
    args = parse_args()
    ckpt = Path(args.model_dir).expanduser() / "jobfit.ckpt"
    resume_text = Path(args.text_file).read_text(encoding="utf-8-sig")
    jd_text = (
        Path(args.jd_file).read_text(encoding="utf-8-sig")
        if args.jd_file
        else None
    )
    if not ckpt.is_file():
        raise FileNotFoundError(f"JobFit checkpoint not found: {ckpt}")
    if not resume_text.strip():
        raise ValueError("resume text is empty")

    predictor = JobFitPredictor(ckpt, device="cpu")
    arrays = predictor.encode_raw(resume_text)
    class_logits = predictor._logits(arrays)[0]
    probabilities = softmax(predictor.calib.z(class_logits[None, :])[0])

    ranked = sorted(
        enumerate(probabilities),
        key=lambda item: float(item[1]),
        reverse=True,
    )
    labels = predictor.id2label
    top_k = [
        {"code": labels[index], "score": round(float(score), 6)}
        for index, score in ranked
    ]
    category_index = int(np.argmax(probabilities))
    payload = {
        "category": labels[category_index],
        "confidence": round(float(probabilities[category_index]), 6),
        "top_k": top_k,
        "model_version": "jobfit-textcnn-20261113",
        "scores": {
            label: round(float(probabilities[index]), 6)
            for index, label in enumerate(labels)
        },
    }

    if jd_text and jd_text.strip():
        custom_jd = predictor._jd_tensors("Custom Position", jd_text)
        paired_logits = predictor._logits(arrays, custom_jd=custom_jd)
        payload["jd_match_score"] = round(
            float(predictor.calib.platt(paired_logits[:, 0])[0]) / 100,
            6,
        )

    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"infer_api: error: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
