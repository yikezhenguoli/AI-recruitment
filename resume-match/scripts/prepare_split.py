"""Build the train/val/test split for the 24-class resume classifier.

Reads the raw Kaggle resume CSV, drops empty resumes, then splits
stratified by category into 2283 / 100 / 100. Writes:

  ../splits/split.csv      id, category, split
  ../splits/summary.json   per-category counts and totals

Run with:  python3 -I scripts/prepare_split.py
"""

import csv
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "archive" / "archive" / "Resume" / "Resume.csv"
SPLITS = ROOT / "splits"

SEED = 42
VAL_SIZE = 100
TEST_SIZE = 100
MIN_PER_CLASS = 4          # val/test floor so every category is represented


def allocate(counts: dict[str, int], total: int) -> dict[str, int]:
    """Give each class MIN_PER_CLASS, then split the rest by class size."""
    alloc = {c: min(MIN_PER_CLASS, n) for c, n in counts.items()}
    remaining = total - sum(alloc.values())
    if remaining < 0:
        raise SystemExit(f"total {total} too small for {len(counts)} classes")
    order = sorted(counts, key=lambda c: (-counts[c], c))
    i = 0
    while remaining > 0:
        c = order[i % len(order)]
        alloc[c] += 1
        remaining -= 1
        i += 1
    return alloc


def main() -> None:
    rng = random.Random(SEED)
    with RAW.open(newline="", encoding="utf-8", errors="replace") as f:
        raw_rows = list(csv.DictReader(f))
    rows = [r for r in raw_rows if (r.get("Resume_str") or "").strip()]

    by_cat: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_cat[r["Category"].strip()].append(r)
    for items in by_cat.values():
        rng.shuffle(items)

    counts = {c: len(items) for c, items in by_cat.items()}
    total = sum(counts.values())
    val_alloc = allocate(counts, VAL_SIZE)
    test_alloc = allocate(counts, TEST_SIZE)

    split_of: dict[str, str] = {}
    for cat, items in by_cat.items():
        n_val, n_test = val_alloc[cat], test_alloc[cat]
        for r in items[:n_val]:
            split_of[r["ID"]] = "val"
        for r in items[n_val:n_val + n_test]:
            split_of[r["ID"]] = "test"
        for r in items[n_val + n_test:]:
            split_of[r["ID"]] = "train"

    SPLITS.mkdir(parents=True, exist_ok=True)
    with (SPLITS / "split.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "category", "split"])
        for r in rows:
            w.writerow([r["ID"], r["Category"].strip(), split_of[r["ID"]]])

    split_counts = Counter(split_of.values())
    per_cat = {
        cat: {
            "total": counts[cat],
            "train": counts[cat] - val_alloc[cat] - test_alloc[cat],
            "val": val_alloc[cat],
            "test": test_alloc[cat],
        }
        for cat in sorted(counts)
    }
    summary = {
        "seed": SEED,
        "raw_rows": len(raw_rows),
        "valid_rows": total,
        "classes": len(counts),
        "totals": dict(split_counts),
        "per_category": per_cat,
    }
    (SPLITS / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"valid rows : {total}")
    print(f"splits     : {dict(split_counts)}")
    print(f"written    : {SPLITS/'split.csv'}")
    print(f"             {SPLITS/'summary.json'}")


if __name__ == "__main__":
    main()
