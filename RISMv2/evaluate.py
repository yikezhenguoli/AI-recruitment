
import json
import numpy as np
import torch

from models.rism_model import RISMModel


# ==========================================
# 1. 选择运行设备
# ==========================================

if torch.backends.mps.is_available():
    device = torch.device("mps")
else:
    device = torch.device("cpu")

print("当前运行设备：", device)


# ==========================================
# 2. 加载数据
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

features = np.concatenate(
    [experience_embeddings, job_embeddings],
    axis=1
)

# 读取标签名称
with open(
    "embeddings/metadata.json",
    "r",
    encoding="utf-8"
) as f:
    metadata = json.load(f)

label_names = metadata["label_names"]


# ==========================================
# 3. 加载验证集
# ==========================================

split_data = np.load(
    "embeddings/split_indices.npz"
)

val_indices = split_data["val_indices"]

val_features = features[val_indices]
val_labels = labels_matrix[val_indices]

print("验证集样本数量：", len(val_indices))


# ==========================================
# 4. 加载训练好的模型
# ==========================================

model = RISMModel().to(device)

model.load_state_dict(
    torch.load(
        "outputs/best_model.pth",
        map_location=device
    )
)

model.eval()

print("模型加载成功！")


# ==========================================
# 5. 模型预测
# ==========================================

x = torch.tensor(
    val_features,
    dtype=torch.float32
).to(device)

with torch.no_grad():

    logits = model(x)

    # Logits 转换为概率
    probabilities = torch.sigmoid(logits)

    # 使用 0.5 作为初始预测阈值
    predictions = (
        probabilities >= 0.5
    ).float()


# 转换为 NumPy，方便计算评价指标
y_true = val_labels.astype(np.int32)

y_pred = predictions.cpu().numpy().astype(np.int32)


# ==========================================
# 额外实验：比较不同分类阈值
# ==========================================

print("\n========== 不同阈值对比 ==========")

thresholds = [0.3, 0.4, 0.5, 0.6, 0.7]

for threshold in thresholds:

    # 根据不同阈值生成预测结果
    pred = (
        probabilities >= threshold
    ).cpu().numpy().astype(np.int32)

    # 计算整体 TP、FP、FN
    tp = ((y_true == 1) & (pred == 1)).sum()

    fp = ((y_true == 0) & (pred == 1)).sum()

    fn = ((y_true == 1) & (pred == 0)).sum()

    # Micro Precision
    precision = (
        tp / (tp + fp)
        if tp + fp > 0
        else 0.0
    )

    # Micro Recall
    recall = (
        tp / (tp + fn)
        if tp + fn > 0
        else 0.0
    )

    # Micro F1
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall > 0
        else 0.0
    )

    # 统计平均每条样本预测多少个维度
    avg_predictions = pred.sum(axis=1).mean()

    print(
        f"Threshold: {threshold:.1f} | "
        f"Precision: {precision:.4f} | "
        f"Recall: {recall:.4f} | "
        f"Micro-F1: {f1:.4f} | "
        f"平均预测维度数: {avg_predictions:.2f}"
    )


# ==========================================
# 6. 计算每个标签的 Precision、Recall、F1
# ==========================================

print("\n========== 各维度评估结果 ==========")

all_tp = 0
all_fp = 0
all_fn = 0

f1_scores = []

for i, label_name in enumerate(label_names):

    true = y_true[:, i]
    pred = y_pred[:, i]

    # 统计 TP、FP、FN
    tp = int(((true == 1) & (pred == 1)).sum())

    fp = int(((true == 0) & (pred == 1)).sum())

    fn = int(((true == 1) & (pred == 0)).sum())

    # Precision
    precision = (
        tp / (tp + fp)
        if tp + fp > 0
        else 0.0
    )

    # Recall
    recall = (
        tp / (tp + fn)
        if tp + fn > 0
        else 0.0
    )

    # F1
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall > 0
        else 0.0
    )

    f1_scores.append(f1)

    all_tp += tp
    all_fp += fp
    all_fn += fn

    print(
        f"{label_name:30s} "
        f"Precision: {precision:.4f} "
        f"Recall: {recall:.4f} "
        f"F1: {f1:.4f}"
    )


# ==========================================
# 7. 计算 Micro-F1 和 Macro-F1
# ==========================================

micro_precision = (
    all_tp / (all_tp + all_fp)
    if all_tp + all_fp > 0
    else 0.0
)

micro_recall = (
    all_tp / (all_tp + all_fn)
    if all_tp + all_fn > 0
    else 0.0
)

micro_f1 = (
    2 * micro_precision * micro_recall
    / (micro_precision + micro_recall)
    if micro_precision + micro_recall > 0
    else 0.0
)

macro_f1 = float(np.mean(f1_scores))


print("\n========== 整体评估结果 ==========")

print("Micro Precision：", round(micro_precision, 4))
print("Micro Recall：", round(micro_recall, 4))
print("Micro F1：", round(micro_f1, 4))
print("Macro F1：", round(macro_f1, 4))


# ==========================================
# 8. 查看一条样本的预测结果
# ==========================================

print("\n========== 第一条验证样本 ==========")

print("真实标签：")

for i, label_name in enumerate(label_names):

    if y_true[0, i] == 1:
        print("  ", label_name)

print("\n模型预测标签：")

for i, label_name in enumerate(label_names):

    if y_pred[0, i] == 1:
        print("  ", label_name)

print("\n模型预测概率：")

for i, label_name in enumerate(label_names):

    probability = probabilities[0, i].item()

    print(
        f"{label_name:30s} {probability:.4f}"
    )
