import numpy as np
import torch


# 1. 读取标签矩阵
labels_matrix = np.load("embeddings/labels.npy")


# 2. 读取训练集索引
split_data = np.load("embeddings/split_indices.npz")

train_indices = split_data["train_indices"]


# 3. 只提取训练集标签
train_labels = labels_matrix[train_indices]


# 4. 统计每个维度的正负样本数量
positive_counts = train_labels.sum(axis=0)

negative_counts = len(train_labels) - positive_counts


# 5. 计算每个维度的正样本权重
pos_weight = negative_counts / positive_counts


# 6. 转换成 PyTorch Tensor
pos_weight_tensor = torch.tensor(
    pos_weight,
    dtype=torch.float32
)


# 7. 输出结果
print("正样本数量：")
print(positive_counts)

print("\n负样本数量：")
print(negative_counts)

print("\npos_weight：")
print(pos_weight_tensor)

print("\npos_weight 形状：")
print(pos_weight_tensor.shape)