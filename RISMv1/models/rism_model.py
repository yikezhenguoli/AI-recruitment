
import torch
import torch.nn as nn


class RISMModel(nn.Module):

    def __init__(self):
        super().__init__()

        self.network = nn.Sequential(

            # 输入层：1024 -> 128
            nn.Linear(1024, 128),

            # 激活函数
            nn.ReLU(),

            # 输出层：128 -> 15
            nn.Linear(128, 15)
        )

    def forward(self, x):

        return self.network(x)
