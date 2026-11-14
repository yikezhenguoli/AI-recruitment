import json

# 1. 读取 JSONL 文件
samples = []

with open("data/multilabel_samples.jsonl", "r", encoding="utf-8") as f:
    for line in f:
        sample = json.loads(line)
        samples.append(sample)

# 2. 查看数据数量
print("样本数量：", len(samples))

# 3. 查看第一条样本
print("\n第一条样本：")
print(json.dumps(samples[0], ensure_ascii=False, indent=2))

# 4. 检查文本字段
print("\n========== 字段检查 ==========")

for field in ["experience_text", "job_text"]:
    empty_count = sum(
        1 for sample in samples
        if not isinstance(sample.get(field), str) or not sample[field].strip()
    )

    print(f"{field} 空值数量：", empty_count)