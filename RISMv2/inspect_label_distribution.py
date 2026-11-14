import json
import numpy as np


# 1. 读取标签矩阵
labels_matrix = np.load("embeddings/labels.npy")

# 2. 读取标签名称
with open("embeddings/metadata.json", "r", encoding="utf-8") as f:
    metadata = json.load(f)

label_names = metadata["label_names"]


# 3. 读取数据集划分索引
split_data = np.load("embeddings/split_indices.npz")

print("数据集划分文件中的字段：", split_data.files)


# 4. 根据字段名称找到三组索引
def find_split_key(keywords):
    for key in split_data.files:
        if any(word in key.lower() for word in keywords):
            return key

    raise KeyError(f"没有找到对应的索引字段：{keywords}")


train_key = find_split_key(["train"])
val_key = find_split_key(["val", "valid"])
test_key = find_split_key(["test"])

train_indices = split_data[train_key]
val_indices = split_data[val_key]
test_indices = split_data[test_key]


# 5. 定义标签分布统计函数
def show_distribution(name, indices):
    subset_labels = labels_matrix[indices]

    print(f"\n========== {name} ==========")
    print("样本数量：", len(indices))

    for i, label_name in enumerate(label_names):
        positive_count = int(subset_labels[:, i].sum())
        negative_count = len(indices) - positive_count

        print(
            f"{label_name}: "
            f"正样本={positive_count}, "
            f"负样本={negative_count}"
        )


# 6. 分别统计三个数据集
show_distribution("训练集", train_indices)
show_distribution("验证集", val_indices)
show_distribution("测试集", test_indices)