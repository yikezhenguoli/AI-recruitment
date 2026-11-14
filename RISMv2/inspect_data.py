
import json
from pathlib import Path
from collections import Counter

# 数据目录
DATA_DIR = Path("data")

# 需要检查的文件
FILES = [
    "resumes.jsonl",
    "resume_experiences.jsonl",
    "interview_questions.jsonl",
    "question_chains.jsonl",
]


def inspect_jsonl(file_path):
    """读取并检查一个 JSONL 文件"""

    print("\n" + "=" * 60)
    print(f"文件：{file_path.name}")
    print("=" * 60)

    if not file_path.exists():
        print("文件不存在！")
        return

    total = 0
    invalid = 0
    field_counter = Counter()
    first_record = None

    with file_path.open("r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):

            # 跳过空行
            if not line.strip():
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"第 {line_number} 行 JSON 格式错误：{e}")
                invalid += 1
                continue

            if not isinstance(record, dict):
                print(f"第 {line_number} 行不是 JSON 对象")
                invalid += 1
                continue

            total += 1
            field_counter.update(record.keys())

            if first_record is None:
                first_record = record

    print(f"有效记录数：{total}")
    print(f"错误记录数：{invalid}")

    print("\n字段统计：")
    for field, count in field_counter.most_common():
        print(f"  {field}: 出现于 {count} 条记录")

    if first_record:
        print("\n第一条记录示例：")
        print(json.dumps(
            first_record,
            ensure_ascii=False,
            indent=2
        )[:3000])


def main():
    for filename in FILES:
        inspect_jsonl(DATA_DIR / filename)


if __name__ == "__main__":
    main()
