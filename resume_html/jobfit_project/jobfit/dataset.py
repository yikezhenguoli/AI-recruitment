"""torch Dataset / DataLoader。输入已是定长数组，无需动态 padding。"""
from __future__ import annotations

import torch
from torch.utils.data import DataLoader, Dataset

from .config import Config
from .data import Corpus


class ResumeDataset(Dataset):
    def __init__(self, corpus: Corpus, indices: list[int]) -> None:
        self.c = corpus
        self.idx = list(indices)
        self.labels = corpus.label_array

    def __len__(self) -> int:
        return len(self.idx)

    def __getitem__(self, k: int) -> dict[str, torch.Tensor]:
        i = self.idx[k]
        c = self.c
        score = c.records[i].score
        return {
            "ids": torch.from_numpy(c.X_ids[i]),
            "weights": torch.from_numpy(c.X_w[i]),
            "seg": torch.from_numpy(c.X_seg[i]),
            "numeric": torch.from_numpy(c.X_num[i]),
            "label": torch.tensor(self.labels[i], dtype=torch.long),
            "score": torch.tensor(score if score is not None else 0.0, dtype=torch.float),
            "score_mask": torch.tensor(1.0 if score is not None else 0.0, dtype=torch.float),
            "row": torch.tensor(i, dtype=torch.long),
        }


def make_loader(corpus: Corpus, split: str, cfg: Config, shuffle: bool | None = None
                ) -> DataLoader:
    if shuffle is None:
        shuffle = (split == "train")
    ds = ResumeDataset(corpus, corpus.splits[split])
    return DataLoader(ds, batch_size=cfg.batch_size, shuffle=shuffle,
                      num_workers=cfg.num_workers, drop_last=False,
                      pin_memory=torch.cuda.is_available())


def batch_to_device(batch: dict[str, torch.Tensor], device: torch.device
                    ) -> dict[str, torch.Tensor]:
    return {k: v.to(device, non_blocking=True) for k, v in batch.items()}
