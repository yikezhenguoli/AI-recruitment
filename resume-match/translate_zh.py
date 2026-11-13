#!/usr/bin/env python3
"""把 train 集里的英文简历翻译成中文，供中英混合训练用。

只翻 train 集：val/test 保持纯英文，翻译体不参与任何对外指标。
产物 data/resume_zh.jsonl，每行 {"id","category","zh"}；支持断点续跑。

用法：
    python translate_zh.py --per-class 20 --concurrency 8
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import random
import time
import urllib.request
from pathlib import Path

PROMPT = """把下面这份英文简历翻译成简体中文。要求：
1. 保留原有结构和顺序（个人总结、工作经历、教育背景、技能等标题与要点）。
2. 公司名、学校名、产品名保留英文原文；职位名称译为中文并在括号内保留英文。
3. 不增删任何内容，不添加解释或评论。
4. 只输出译文正文，不要任何前后缀。"""


def read_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def pick_samples(csv_path: Path, split_path: Path, per_class: int, seed: int) -> list[dict]:
    splits = {row["id"]: row["split"] for row in csv.DictReader(split_path.open(encoding="utf-8"))}
    with csv_path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    by_class: dict[str, list[dict]] = {}
    for row in rows:
        if splits.get(row["ID"]) != "train":
            continue
        by_class.setdefault(row["Category"], []).append(row)
    rng = random.Random(seed)
    picked: list[dict] = []
    for code in sorted(by_class):
        items = by_class[code]
        rng.shuffle(items)
        for row in items[:per_class]:
            picked.append({"id": row["ID"], "category": code, "en": row["Resume_str"]})
    return picked


async def translate_one(item: dict, base_url: str, api_key: str, model: str) -> dict:
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": item["en"]},
        ],
        "temperature": 0.2,
        "max_tokens": 4000,
    }).encode()
    request = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    last: Exception | None = None
    for attempt in range(4):
        try:
            def call() -> dict:
                with urllib.request.urlopen(request, timeout=180) as response:
                    return json.loads(response.read())

            payload = await asyncio.to_thread(call)
            text = payload["choices"][0]["message"]["content"].strip()
            if not text:
                raise ValueError("模型返回空文本")
            return {"id": item["id"], "category": item["category"], "zh": text}
        except Exception as exc:  # noqa: BLE001 - 网络/限流都要重试
            last = exc
            await asyncio.sleep(2 ** attempt)
    raise RuntimeError(f"{item['id']} 翻译失败: {last}")


async def run(items: list[dict], out_path: Path, base_url: str, api_key: str,
              model: str, concurrency: int) -> None:
    done: set[str] = set()
    if out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                done.add(json.loads(line)["id"])
    todo = [item for item in items if item["id"] not in done]
    print(f"总样本 {len(items)}，已翻译 {len(done)}，本次待翻 {len(todo)}", flush=True)
    if not todo:
        return

    semaphore = asyncio.Semaphore(concurrency)
    lock = asyncio.Lock()
    finished = 0
    started = time.time()

    async def worker(item: dict) -> None:
        nonlocal finished
        async with semaphore:
            result = await translate_one(item, base_url, api_key, model)
        async with lock:
            with out_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(result, ensure_ascii=False) + "\n")
            finished += 1
            if finished % 20 == 0 or finished == len(todo):
                rate = finished / max(1e-9, time.time() - started)
                print(f"  {finished}/{len(todo)}  {rate:.2f} 条/秒", flush=True)

    await asyncio.gather(*(worker(item) for item in todo))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, default=Path("Resume.csv"))
    parser.add_argument("--split", type=Path, default=Path("splits/split.csv"))
    parser.add_argument("--env-file", type=Path, default=Path("../apps/api/.env"))
    parser.add_argument("--out", type=Path, default=Path("data/resume_zh.jsonl"))
    parser.add_argument("--per-class", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--concurrency", type=int, default=8)
    args = parser.parse_args()

    env = read_env(args.env_file)
    base_url = env.get("LLM_BASE_URL", "https://api.deepseek.com/v1")
    api_key = env.get("LLM_API_KEY", "")
    model = env.get("LLM_MODEL", "deepseek-chat")
    if not api_key:
        raise SystemExit(f"没在 {args.env_file} 里找到 LLM_API_KEY")

    csv_path = args.csv if args.csv.exists() else Path("data/archive/archive/Resume/Resume.csv")
    items = pick_samples(csv_path, args.split, args.per_class, args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    asyncio.run(run(items, args.out, base_url, api_key, model, args.concurrency))
    print(f"完成，产物 {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
