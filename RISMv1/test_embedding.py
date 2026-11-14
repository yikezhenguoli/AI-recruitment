
from sentence_transformers import SentenceTransformer
import numpy as np

# 1. 加载 Embedding 模型
model = SentenceTransformer(
    "BAAI/bge-small-zh-v1.5",
    device="mps"
)


print("Embedding 模型加载成功！")

# 2. 准备三条测试文本
sentences = [
    "使用 Python 开发数据分析系统",
    "利用 Python 进行数据处理",
    "负责团队人员招聘和管理"
]

# 3. 将文本转换成向量
embeddings = model.encode(
    sentences,
    normalize_embeddings=True,
    convert_to_numpy=True
)


# 计算文本1和文本2的余弦相似度
similarity_1_2 = np.dot(embeddings[0], embeddings[1])

# 计算文本1和文本3的余弦相似度
similarity_1_3 = np.dot(embeddings[0], embeddings[2])

# 计算文本2和文本3的余弦相似度
similarity_2_3 = np.dot(embeddings[1], embeddings[2])

print("\n========== 余弦相似度 ==========")

print("文本1 vs 文本2：", round(float(similarity_1_2), 4))
print("文本1 vs 文本3：", round(float(similarity_1_3), 4))
print("文本2 vs 文本3：", round(float(similarity_2_3), 4))


# 4. 查看向量矩阵形状
print("\n向量矩阵形状：", embeddings.shape)

# 5. 查看第一条文本的完整向量
print("\n第一条文本的向量：")
print(embeddings[0])

# 6. 只查看前10个数字
print("\n第一条文本向量的前10个数字：")
print(embeddings[0][:10])
