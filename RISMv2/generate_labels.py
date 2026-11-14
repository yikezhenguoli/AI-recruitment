
import json
import numpy as np


# 1. 读取 metadata.json
with open("embeddings/metadata.json", "r", encoding="utf-8") as f:
    metadata = json.load(f)


# 2. 获取标签名称和每条样本的标签
label_names = metadata["label_names"]
sample_labels = metadata["labels"]

print("标签类别数量：", len(label_names))
print("样本数量：", len(sample_labels))


# 3. 建立标签名称与数字位置的映射
label_to_index = {
    label: index
    for index, label in enumerate(label_names)
}

print("\n标签位置映射：")
print(label_to_index)


# 4. 创建全零矩阵
labels_matrix = np.zeros(
    (len(sample_labels), len(label_names)),
    dtype=np.float32
)


# 5. 将标签转换成 Multi-hot
for sample_index, labels in enumerate(sample_labels):

    for label in labels:

        label_index = label_to_index[label]

        labels_matrix[sample_index, label_index] = 1


# 6. 保存标签矩阵
np.save("embeddings/labels.npy", labels_matrix)


# 7. 检查结果
print("\n========== Multi-hot 生成结果 ==========")

print("标签矩阵形状：", labels_matrix.shape)
print("数据类型：", labels_matrix.dtype)

print("\n第一条样本的原始标签：")
print(sample_labels[0])

print("\n第一条样本的 Multi-hot：")
print(labels_matrix[0])

print("\n第一条样本中标签数量：")
print(int(labels_matrix[0].sum()))

print("\n所有样本的标签总数：")
print(int(labels_matrix.sum()))

print("\n生成完成！")
