
import json
import os
import numpy as np


# 1. 读取样本元数据
with open("embeddings/metadata.json", "r", encoding="utf-8") as f:
    metadata = json.load(f)

resume_ids = metadata["resume_ids"]

# 2. 检查数据数量
unique_resume_ids = sorted(set(resume_ids))

print("经历样本数量：", len(resume_ids))
print("不同简历数量：", len(unique_resume_ids))

assert len(resume_ids) == 471
assert len(unique_resume_ids) == 100


# 3. 检查三个数据文件是否对齐
experience_embeddings = np.load(
    "embeddings/experience_embeddings.npy"
)

job_embeddings = np.load(
    "embeddings/job_embeddings.npy"
)

labels = np.load(
    "embeddings/labels.npy"
)

assert experience_embeddings.shape == (471, 512)
assert job_embeddings.shape == (471, 512)
assert labels.shape == (471, 15)


# 4. 随机打乱简历 ID
rng = np.random.default_rng(seed=42)

shuffled_resume_ids = rng.permutation(unique_resume_ids)


# 5. 按 70 / 15 / 15 份简历进行划分
train_resume_ids = set(shuffled_resume_ids[:70])
val_resume_ids = set(shuffled_resume_ids[70:85])
test_resume_ids = set(shuffled_resume_ids[85:100])


# 6. 根据 resume_id 找到对应的经历样本索引
train_indices = [
    i for i, resume_id in enumerate(resume_ids)
    if resume_id in train_resume_ids
]

val_indices = [
    i for i, resume_id in enumerate(resume_ids)
    if resume_id in val_resume_ids
]

test_indices = [
    i for i, resume_id in enumerate(resume_ids)
    if resume_id in test_resume_ids
]


# 7. 检查简历是否发生交叉
assert train_resume_ids.isdisjoint(val_resume_ids)
assert train_resume_ids.isdisjoint(test_resume_ids)
assert val_resume_ids.isdisjoint(test_resume_ids)

# 检查所有样本都被划分且没有重复
all_indices = train_indices + val_indices + test_indices

assert len(all_indices) == len(resume_ids)
assert len(set(all_indices)) == len(resume_ids)


# 8. 保存划分索引
os.makedirs("embeddings", exist_ok=True)

np.savez(
    "embeddings/split_indices.npz",
    train_indices=train_indices,
    val_indices=val_indices,
    test_indices=test_indices
)


# 9. 保存各集合对应的简历 ID，方便追溯
split_metadata = {
    "train_resume_ids": sorted(train_resume_ids),
    "val_resume_ids": sorted(val_resume_ids),
    "test_resume_ids": sorted(test_resume_ids)
}

with open("embeddings/split_metadata.json", "w", encoding="utf-8") as f:
    json.dump(split_metadata, f, ensure_ascii=False, indent=2)


# 10. 输出结果
print("\n========== 数据集划分结果 ==========")

print("训练集简历数量：", len(train_resume_ids))
print("验证集简历数量：", len(val_resume_ids))
print("测试集简历数量：", len(test_resume_ids))

print("\n训练集经历数量：", len(train_indices))
print("验证集经历数量：", len(val_indices))
print("测试集经历数量：", len(test_indices))

print("\n简历交叉检查：通过")
print("样本完整性检查：通过")
print("数据划分文件保存成功！")
