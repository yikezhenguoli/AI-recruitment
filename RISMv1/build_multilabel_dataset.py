
import json
from pathlib import Path
from collections import defaultdict, Counter


# ==========================================
# 1. 定义数据文件路径
# ==========================================

DATA_DIR = Path("data")

# 原始问题级训练数据
INPUT_FILE = DATA_DIR / "training_samples.jsonl"

# 新的多标签训练数据
OUTPUT_FILE = DATA_DIR / "multilabel_samples.jsonl"


def main():

    # ==========================================
    # 2. 读取原始训练数据
    # ==========================================

    samples = []

    with INPUT_FILE.open("r", encoding="utf-8") as f:

        for line in f:

            if not line.strip():
                continue

            # 将 JSON 字符串转换成 Python 字典
            sample = json.loads(line)

            samples.append(sample)

    print("原始样本数量：", len(samples))


    # ==========================================
    # 3. 按照 experience_id 对样本进行分组
    # ==========================================

    # defaultdict(list)：
    # 当一个 experience_id 第一次出现时，
    # 自动创建一个空列表。
    experience_groups = defaultdict(list)

    for sample in samples:

        # 获取当前样本的经历编号
        experience_id = sample["experience_id"]

        # 将样本放入对应经历的分组
        experience_groups[experience_id].append(sample)


    # ==========================================
    # 4. 将同一经历的多条问题合并
    # ==========================================

    multilabel_samples = []

    for experience_id, group in experience_groups.items():

        # 取该经历的第一条记录作为基础
        first_sample = group[0]

        # 检查同一经历的输入信息是否一致
        for sample in group:

            if sample["resume_id"] != first_sample["resume_id"]:
                raise ValueError(
                    f"{experience_id} 对应多个 resume_id"
                )

            if sample["experience_text"] != first_sample["experience_text"]:
                raise ValueError(
                    f"{experience_id} 的经历文本不一致"
                )

            if sample["job_text"] != first_sample["job_text"]:
                raise ValueError(
                    f"{experience_id} 的岗位文本不一致"
                )

        # 使用 set 收集所有追问维度
        # set 可以自动去除重复标签
        labels = set()

        for sample in group:

            labels.add(sample["label"])

        # 构建一条新的多标签训练样本
        new_sample = {

            "resume_id": first_sample["resume_id"],

            "experience_id": experience_id,

            "experience_text": first_sample["experience_text"],

            "job_text": first_sample["job_text"],

            # 将集合转换为排序后的列表
            "labels": sorted(labels),

            # 记录原来对应多少道面试问题
            "question_count": len(group)
        }

        multilabel_samples.append(new_sample)


    # ==========================================
    # 5. 统计多标签数据
    # ==========================================

    label_counter = Counter()

    single_label_count = 0
    multi_label_count = 0

    for sample in multilabel_samples:

        labels = sample["labels"]

        # 统计每个追问维度出现的次数
        for label in labels:
            label_counter[label] += 1

        # 判断一段经历有几个不同的追问维度
        if len(labels) == 1:
            single_label_count += 1

        elif len(labels) > 1:
            multi_label_count += 1


    # ==========================================
    # 6. 保存新的训练数据
    # ==========================================

    with OUTPUT_FILE.open("w", encoding="utf-8") as f:

        for sample in multilabel_samples:

            # 将 Python 字典转换为 JSON 字符串
            line = json.dumps(
                sample,
                ensure_ascii=False
            )

            # 每条样本占据一行
            f.write(line + "\n")


    # ==========================================
    # 7. 输出检查结果
    # ==========================================

    print("\n========== 多标签数据构建结果 ==========")

    print("原始问题级样本数量：", len(samples))

    print("合并后的经历级样本数量：", len(multilabel_samples))

    print("单标签经历数量：", single_label_count)

    print("多标签经历数量：", multi_label_count)

    print("\n========== 新的追问维度分布 ==========")

    for label, count in label_counter.most_common():

        print(f"{label}: {count}")

    print("\n========== 新样本示例 ==========")

    if multilabel_samples:

        print(
            json.dumps(
                multilabel_samples[0],
                ensure_ascii=False,
                indent=2
            )
        )

    print("\n数据保存位置：", OUTPUT_FILE)


if __name__ == "__main__":
    main()
