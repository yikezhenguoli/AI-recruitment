
import argparse
import json
import torch

from pathlib import Path
from sentence_transformers import SentenceTransformer

from models.rism_model import RISMModel


# ==========================================
# 1. 基础配置
# ==========================================

EMBEDDING_MODEL_NAME = "BAAI/bge-small-zh-v1.5"

MODEL_PATH = "outputs/best_model.pth"

METADATA_PATH = "embeddings/metadata.json"

DEFAULT_THRESHOLD = 0.5


# ==========================================
# 2. 选择设备
# ==========================================

if torch.backends.mps.is_available():
    device = torch.device("mps")
else:
    device = torch.device("cpu")

print("当前运行设备：", device)


# ==========================================
# 3. 加载标签名称
# ==========================================

with open(
    METADATA_PATH,
    "r",
    encoding="utf-8"
) as f:
    metadata = json.load(f)

label_names = metadata["label_names"]


# ==========================================
# 4. 加载 Embedding 模型
# ==========================================

print("正在加载 Embedding 模型...")

embedding_model = SentenceTransformer(
    EMBEDDING_MODEL_NAME,
    device=str(device)
)

print("Embedding 模型加载成功！")


# ==========================================
# 5. 加载 RISMv1 模型
# ==========================================

print("正在加载 RISMv1 模型...")

model = RISMModel().to(device)

state_dict = torch.load(
    MODEL_PATH,
    map_location=device
)

model.load_state_dict(state_dict)

model.eval()

print("RISMv1 模型加载成功！")


# ==========================================
# 6. 定义单段经历预测函数
# ==========================================

def predict_experience(
    experience,
    target_position,
    threshold=DEFAULT_THRESHOLD
):

    experience_text = experience["content"]

    # 生成经历 Embedding
    experience_embedding = embedding_model.encode(
        experience_text,
        convert_to_numpy=True,
        show_progress_bar=False
    )

    # 生成岗位 Embedding
    job_embedding = embedding_model.encode(
        target_position,
        convert_to_numpy=True,
        show_progress_bar=False
    )

    # 拼接为 1024 维向量
    features = torch.tensor(
        list(experience_embedding) + list(job_embedding),
        dtype=torch.float32
    ).unsqueeze(0).to(device)

    # 模型预测
    with torch.no_grad():

        logits = model(features)

        probabilities = torch.sigmoid(logits)[0]

    # 转换为 Python 数值
    scores = probabilities.cpu().tolist()

    # 筛选预测维度
    predicted_dimensions = []

    for label_name, score in zip(label_names, scores):

        if score >= threshold:

            predicted_dimensions.append({
                "dimension": label_name,
                "score": round(float(score), 4)
            })

    # 按分数从高到低排序
    predicted_dimensions.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    # 保留全部维度的分数
    dimension_scores = {}

    for label_name, score in zip(label_names, scores):

        dimension_scores[label_name] = round(
            float(score),
            4
        )

    return {
        "experience_id": experience["experience_id"],
        "experience_type": experience.get(
            "experience_type",
            "unknown"
        ),
        "title": experience.get("title", ""),
        "predicted_dimensions": predicted_dimensions,
        "dimension_scores": dimension_scores
    }


# ==========================================
# 7. 定义整份简历预测函数
# ==========================================

def predict_resume(
    resume_data,
    threshold=DEFAULT_THRESHOLD
):

    resume_id = resume_data["resume_id"]

    target_position = resume_data["target_position"]

    experiences = resume_data["experiences"]

    if not experiences:
        raise ValueError("简历中没有可预测的经历")

    results = []

    for experience in experiences:

        print(
            "正在预测经历：",
            experience["experience_id"]
        )

        result = predict_experience(
            experience,
            target_position,
            threshold
        )

        results.append(result)

    return {
        "resume_id": resume_id,
        "target_position": target_position,
        "threshold": threshold,
        "model": "RISMv1",
        "experiences": results
    }


# ==========================================
# 8. 程序入口
# ==========================================

if __name__ == "__main__":

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--input",
        default="input_resume.json"
    )

    parser.add_argument(
        "--output",
        default="outputs/prediction_result.json"
    )

    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD
    )

    args = parser.parse_args()

    if not 0 <= args.threshold <= 1:
        raise ValueError("threshold 必须在 0 到 1 之间")

    # 读取新简历
    with open(
        args.input,
        "r",
        encoding="utf-8"
    ) as f:

        resume_data = json.load(f)

    # 执行预测
    result = predict_resume(
        resume_data,
        threshold=args.threshold
    )

    # 确保输出目录存在
    output_path = Path(args.output)

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    # 保存 JSON
    with open(
        output_path,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            result,
            f,
            ensure_ascii=False,
            indent=4
        )

    print("\n预测完成！")
    print("结果保存位置：", output_path)

    print("\n========== JSON 预测结果 ==========")

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=4
        )
    )
