
import os
import random
import numpy as np
import torch
import torch.nn as nn

from torch.utils.data import DataLoader
from dataset import RISMDataset
from models.rism_model import RISMModel


# ==========================================
# 1. 固定随机种子，尽量保证实验可复现
# ==========================================

seed = 42

random.seed(seed)
np.random.seed(seed)
torch.manual_seed(seed)


# ==========================================
# 2. 选择运行设备
# ==========================================

if torch.backends.mps.is_available():
    device = torch.device("mps")
else:
    device = torch.device("cpu")

print("当前运行设备：", device)


# ==========================================
# 3. 加载 Embedding 和标签
# ==========================================

experience_embeddings = np.load(
    "embeddings/experience_embeddings.npy"
)

job_embeddings = np.load(
    "embeddings/job_embeddings.npy"
)

labels_matrix = np.load(
    "embeddings/labels.npy"
)

# 拼接经历和岗位向量
features = np.concatenate(
    [experience_embeddings, job_embeddings],
    axis=1
)

print("输入特征形状：", features.shape)
print("标签矩阵形状：", labels_matrix.shape)


# ==========================================
# 4. 加载训练集、验证集索引
# ==========================================

split_data = np.load("embeddings/split_indices.npz")

train_indices = split_data["train_indices"]
val_indices = split_data["val_indices"]

train_features = features[train_indices]
train_labels = labels_matrix[train_indices]

val_features = features[val_indices]
val_labels = labels_matrix[val_indices]

print("训练集数量：", len(train_indices))
print("验证集数量：", len(val_indices))


# ==========================================
# 5. 计算正样本权重
# ==========================================

positive_counts = train_labels.sum(axis=0)

negative_counts = len(train_labels) - positive_counts

pos_weight = negative_counts / positive_counts

pos_weight = torch.tensor(
    pos_weight,
    dtype=torch.float32
).to(device)

print("正样本权重：", pos_weight)


# ==========================================
# 6. 创建 Dataset
# ==========================================

train_dataset = RISMDataset(
    train_features,
    train_labels
)

val_dataset = RISMDataset(
    val_features,
    val_labels
)


# ==========================================
# 7. 创建 DataLoader
# ==========================================

train_loader = DataLoader(
    train_dataset,
    batch_size=32,
    shuffle=True
)

val_loader = DataLoader(
    val_dataset,
    batch_size=32,
    shuffle=False
)


# ==========================================
# 8. 创建模型
# ==========================================

model = RISMModel().to(device)


# ==========================================
# 9. 创建损失函数和优化器
# ==========================================

criterion = nn.BCEWithLogitsLoss(
    pos_weight=pos_weight
)

optimizer = torch.optim.Adam(
    model.parameters(),
    lr=0.001,
    weight_decay=0.0001
)


# ==========================================
# 10. 训练参数
# ==========================================

epochs = 100
patience = 12

best_val_loss = float("inf")
best_epoch = 0
no_improve_count = 0

os.makedirs("outputs", exist_ok=True)


# ==========================================
# 11. 正式训练
# ==========================================

for epoch in range(epochs):

    # ---------- 训练阶段 ----------

    model.train()

    train_loss_sum = 0.0

    for batch_x, batch_y in train_loader:

        batch_x = batch_x.to(device)
        batch_y = batch_y.to(device)

        # 清除旧梯度
        optimizer.zero_grad()

        # 前向计算
        outputs = model(batch_x)

        # 计算损失
        loss = criterion(outputs, batch_y)

        # 反向传播
        loss.backward()

        # 更新参数
        optimizer.step()

        train_loss_sum += loss.item() * len(batch_x)

    train_loss = train_loss_sum / len(train_dataset)


    # ---------- 验证阶段 ----------

    model.eval()

    val_loss_sum = 0.0

    with torch.no_grad():

        for batch_x, batch_y in val_loader:

            batch_x = batch_x.to(device)
            batch_y = batch_y.to(device)

            outputs = model(batch_x)

            loss = criterion(outputs, batch_y)

            val_loss_sum += loss.item() * len(batch_x)

    val_loss = val_loss_sum / len(val_dataset)


    # ---------- 保存最佳模型 ----------

    if val_loss < best_val_loss:

        best_val_loss = val_loss
        best_epoch = epoch + 1
        no_improve_count = 0

        torch.save(
            model.state_dict(),
            "outputs/best_model.pth"
        )

        status = "保存最佳模型"

    else:

        no_improve_count += 1
        status = ""


    # ---------- 输出训练信息 ----------

    print(
        f"Epoch [{epoch + 1}/{epochs}] "
        f"Train Loss: {train_loss:.4f} "
        f"Val Loss: {val_loss:.4f} "
        f"{status}"
    )


    # ---------- Early Stopping ----------

    if no_improve_count >= patience:

        print("\n触发 Early Stopping，停止训练。")
        break


# ==========================================
# 12. 输出最终结果
# ==========================================

print("\n========== 训练完成 ==========")

print("最佳 Epoch：", best_epoch)
print("最佳验证损失：", round(best_val_loss, 4))
print("模型保存位置：outputs/best_model.pth")
