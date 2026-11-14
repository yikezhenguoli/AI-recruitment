import torch
import torch.nn as nn

# 模拟模型输出的4个Logits
logits = torch.tensor([
    [-2.0, 2.0, -1.0, 1.0]
])

# 模拟真实标签
target = torch.tensor([
    [1.0, 0.0, 1.0, 0.0]
])

# 创建损失函数
criterion = nn.BCEWithLogitsLoss()

# 计算损失
loss = criterion(logits, target)

print("模型输出：", logits)
print("真实标签：", target)
print("损失值：", loss.item())