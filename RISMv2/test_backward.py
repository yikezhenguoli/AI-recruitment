import torch
import torch.nn as nn

from models.rism_model import RISMModel


# 1. 选择运行设备
if torch.backends.mps.is_available():
    device = torch.device("mps")
else:
    device = torch.device("cpu")


# 2. 创建模型
model = RISMModel().to(device)


# 3. 创建损失函数
criterion = nn.BCEWithLogitsLoss()


# 4. 创建优化器
optimizer = torch.optim.Adam(
    model.parameters(),
    lr=0.001
)


# 5. 创建模拟训练数据
x = torch.randn(4, 1024).to(device)

y = torch.randint(
    0, 2, (4, 15)
).float().to(device)


# 6. 记录更新前的参数
before = model.network[0].weight.detach().clone()


# 7. 前向计算
outputs = model(x)


# 8. 计算损失
loss = criterion(outputs, y)


# 9. 清除旧梯度
optimizer.zero_grad()


# 10. 反向传播
loss.backward()


# 11. 查看梯度
gradient = model.network[0].weight.grad

print("运行设备：", device)
print("初始损失：", loss.item())
print("梯度形状：", gradient.shape)
print("梯度平均绝对值：", gradient.abs().mean().item())


# 12. 更新模型参数
optimizer.step()


# 13. 记录更新后的参数
after = model.network[0].weight.detach().clone()


# 14. 比较参数变化
difference = (after - before).abs().mean()

print("参数平均变化量：", difference.item())
print("参数是否发生变化：", not torch.equal(before, after))