
import json
import os

import numpy as np
import torch
from sentence_transformers import SentenceTransformer


# 1. 自动选择运行设备
if torch.backends.mps.is_available():
    device = "mps"
else:
    device = "cpu"

print("当前运行设备：", device)


# 2. 读取训练数据
samples = []

with open("data/multilabel_samples.jsonl", "r", encoding="utf-8") as f:
    for line in f:
        samples.append(json.loads(line))

print("读取样本数量：", len(samples))


# 3. 提取经历文本和岗位文本
experience_texts = [
    sample["experience_text"]
    for sample in samples
]

job_texts = [
    sample["job_text"]
    for sample in samples
]


# 4. 加载 Embedding 模型
model = SentenceTransformer(
    "BAAI/bge-small-zh-v1.5",
    device=device
)

print("Embedding 模型加载成功！")


# 5. 生成经历向量
experience_embeddings = model.encode(
    experience_texts,
    batch_size=32,
    show_progress_bar=True,
    normalize_embeddings=True,
    convert_to_numpy=True
)


# 6. 生成岗位向量
job_embeddings = model.encode(
    job_texts,
    batch_size=32,
    show_progress_bar=True,
    normalize_embeddings=True,
    convert_to_numpy=True
)


# 7. 创建输出目录
os.makedirs("embeddings", exist_ok=True)


# 8. 保存向量
np.save(
    "embeddings/experience_embeddings.npy",
    experience_embeddings
)

np.save(
    "embeddings/job_embeddings.npy",
    job_embeddings
)


# 9. 保存样本对应关系，保证向量与原始数据顺序一致
labels = sorted({
    label
    for sample in samples
    for label in sample["labels"]
})

metadata = {
    "resume_ids": [sample["resume_id"] for sample in samples],
    "experience_ids": [sample["experience_id"] for sample in samples],
    "labels": [sample["labels"] for sample in samples],
    "label_names": labels
}

with open("embeddings/metadata.json", "w", encoding="utf-8") as f:
    json.dump(metadata, f, ensure_ascii=False, indent=2)


# 10. 检查结果
print("\n========== Embedding 生成结果 ==========")

print("经历向量形状：", experience_embeddings.shape)
print("岗位向量形状：", job_embeddings.shape)

print("经历向量数据类型：", experience_embeddings.dtype)
print("追问维度类别数量：", len(labels))

print("\n生成完成！")
