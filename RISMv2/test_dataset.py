
import json
import numpy as np

from dataset import RISMDataset


# 1. 加载向量
experience_embeddings = np.load(
    "embeddings/experience_embeddings.npy"
)

job_embeddings = np.load(
    "embeddings/job_embeddings.npy"
)

labels = np.load(
    "embeddings/labels.npy"
)


# 2. 拼接经历和岗位向量
features = np.concatenate(
    [experience_embeddings, job_embeddings],
    axis=1
)


# 3. 创建 Dataset
dataset = RISMDataset(features, labels)


# 4. 检查 Dataset
print("样本数量：", len(dataset))

x, y = dataset[0]

print("第一条输入形状：", x.shape)
print("第一条标签形状：", y.shape)

print("输入数据类型：", x.dtype)
print("标签数据类型：", y.dtype)

print("第一条样本的标签：", y)
