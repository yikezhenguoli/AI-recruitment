
import numpy as np
import torch

from torch.utils.data import DataLoader
from dataset import RISMDataset


# 1. 读取数据
experience_embeddings = np.load(
    "embeddings/experience_embeddings.npy"
)

job_embeddings = np.load(
    "embeddings/job_embeddings.npy"
)

labels = np.load("embeddings/labels.npy")


# 2. 拼接特征
features = np.concatenate(
    [experience_embeddings, job_embeddings],
    axis=1
)


# 3. 创建 Dataset
dataset = RISMDataset(features, labels)


# 4. 创建 DataLoader
dataloader = DataLoader(
    dataset,
    batch_size=32,
    shuffle=True
)


# 5. 读取第一个 Batch
for batch_x, batch_y in dataloader:

    print("输入 Batch 形状：", batch_x.shape)
    print("标签 Batch 形状：", batch_y.shape)

    print("输入数据类型：", batch_x.dtype)
    print("标签数据类型：", batch_y.dtype)

    print("当前 Batch 样本数量：", len(batch_x))

    break
