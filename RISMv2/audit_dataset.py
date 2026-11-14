
import json
from pathlib import Path
from collections import Counter, defaultdict

DATA_DIR = Path("data")


def load_jsonl(filename):
    """读取 JSONL 文件，返回字典列表"""

    file_path = DATA_DIR / filename
    records = []

    with file_path.open("r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            if not line.strip():
                continue

            try:
                record = json.loads(line)
                records.append(record)
            except json.JSONDecodeError as e:
                print(f"{filename} 第 {line_number} 行错误：{e}")

    return records


def main():

    # 1. 读取数据
    resumes = load_jsonl("resumes.jsonl")
    experiences = load_jsonl("resume_experiences.jsonl")
    questions = load_jsonl("interview_questions.jsonl")

    print("数据读取完成")
    print("简历数量：", len(resumes))
    print("经历数量：", len(experiences))
    print("问题数量：", len(questions))

    # 2. 建立索引
    resume_map = {
        item["resume_id"]: item
        for item in resumes
    }

    experience_map = {
        item["experience_id"]: item
        for item in experiences
    }

    # 3. 统计信息
    label_counter = Counter()
    missing_resume = 0
    missing_experience = 0
    invalid_label = 0

    # 4. 构建训练样本
    samples = []

    for question in questions:

        resume_id = question.get("resume_id")
        experience_id = question.get("experience_id")
        label = question.get("dimension")

        # 检查关联
        resume = resume_map.get(resume_id)
        experience = experience_map.get(experience_id)

        if resume is None:
            missing_resume += 1
            continue

        if experience is None:
            missing_experience += 1
            continue

        # 检查标签
        if not label:
            invalid_label += 1
            continue

        # 检查经历与简历是否属于同一个人
        if experience.get("resume_id") != resume_id:
            print("关联错误：", question.get("question_id"))
            continue

        # 构建样本
        sample = {
            "question_id": question["question_id"],
            "resume_id": resume_id,
            "experience_id": experience_id,

            "experience_text": experience.get(
                "original_content", ""
            ),

            "job_text": resume.get(
                "target_position", ""
            ),

            "label": label
        }

        samples.append(sample)
        label_counter[label] += 1

    # ==========================================
    # 额外检查：统计训练样本的关联情况
    # 注意：这段代码必须放在 for question 循环结束之后！
    # ==========================================

    # 1. 统计不同简历的数量
    # set() 可以自动去重
    # 例如：["RES001", "RES001", "RES002"] 去重后变成两个元素
    unique_resumes = set(
        sample["resume_id"]
        for sample in samples
    )

    # 2. 统计不同经历的数量
    # 同一段经历可能对应多道面试问题，因此需要去重
    unique_experiences = set(
        sample["experience_id"]
        for sample in samples
    )

    # 3. 建立经历与追问维度之间的对应关系
    # defaultdict(set) 表示：
    # 当一个 experience_id 第一次出现时，自动创建一个空集合
    experience_labels = defaultdict(set)

    # 遍历所有训练样本
    for sample in samples:

        # 获取当前样本对应的经历编号
        experience_id = sample["experience_id"]

        # 获取当前样本的追问维度
        label = sample["label"]

        # 将追问维度加入对应经历的集合
        # set() 会自动去重
        experience_labels[experience_id].add(label)

    # 4. 找出对应多个追问维度的经历
    multi_label_experiences = {
        experience_id: labels
        for experience_id, labels in experience_labels.items()

        # 只有追问维度数量大于 1，才保留
        if len(labels) > 1
    }

    # 5. 输出深入检查结果
    print("\n========== 深入数据检查 ==========")

    # len() 统计集合中的不同简历数量
    print("涉及的不同简历数量：", len(unique_resumes))

    # len() 统计集合中的不同经历数量
    print("涉及的不同经历数量：", len(unique_experiences))

    # 统计对应多个追问维度的经历数量
    print(
        "对应多个追问维度的经历数量：",
        len(multi_label_experiences)
    )

    # 6. 输出前五条多维度经历作为示例
    print("\n========== 多维度经历示例 ==========")

    for experience_id, labels in list(
        multi_label_experiences.items()
    )[:5]:

        # sorted() 将集合排序，方便查看
        print(experience_id, "=>", sorted(labels))
    # 5. 输出统计
    print("\n========== 数据关联结果 ==========")

    print("成功构建样本：", len(samples))
    print("简历关联失败：", missing_resume)
    print("经历关联失败：", missing_experience)
    print("标签缺失：", invalid_label)

    print("\n========== 追问维度分布 ==========")

    for label, count in label_counter.most_common():
        print(f"{label}: {count}")

    print("\n========== 样本示例 ==========")

    if samples:
        print(json.dumps(
            samples[0],
            ensure_ascii=False,
            indent=2
        ))

    # 6. 保存初步训练样本
    output_path = DATA_DIR / "training_samples.jsonl"

    with output_path.open("w", encoding="utf-8") as f:
        for sample in samples:
            f.write(
                json.dumps(sample, ensure_ascii=False) + "\n"
            )

    print("\n训练样本已保存：", output_path)


if __name__ == "__main__":
    main()
