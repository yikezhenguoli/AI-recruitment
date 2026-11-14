
import torch

from models.rism_model import RISMModel


# 1. 自动选择运行设备
if torch.backends.mps.is_available():
    device = torch.device("mps")
else:
    device = torch.device("cpu")


# 2. 创建模型
model = RISMModel()

# 3. 将模型放到运行设备
model = model.to(device)


# 4. 创建模拟输入
x = torch.randn(32, 1024).to(device)


# 5. 前向传播
output = model(x)


# 6. 查看结果
print("运行设备：", device)
print("输入形状：", x.shape)
print("输出形状：", output.shape)
print("输出数据类型：", output.dtype)

print("\n第一条样本的预测分数：")
print(output[0])
