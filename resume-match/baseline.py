"""非神经基线：TF-IDF + LinearSVC / LogisticRegression。

用途：在 val.py / test.py 里与神经模型并排对照。用户要"效果最好"，
所以必须给出能证伪的说法——如果经典方法不差，报告要如实呈现。

口径：
  * 向量器只在 train 上 fit，再 transform 评估集（避免泄漏）。
  * 与神经模型使用同一份固定划分，不做额外调参；
    神经模型的超参是在 val 上选的，这一点在报告里会注记。
"""

from __future__ import annotations

import time
import warnings
from collections import Counter

import numpy as np
from joblib import parallel_backend
from sklearn.exceptions import ConvergenceWarning
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.multiclass import OneVsRestClassifier
from sklearn.svm import LinearSVC

from common import compute_metrics


def _writable_csr(matrix):
    """scipy 部分版本返回只读 data 视图；joblib 并行 fit 时会报
    WRITEBACKIFCOPY base is read-only，这里统一复制成可写 CSR。"""
    matrix = matrix.tocsr(copy=True)
    matrix.data = matrix.data.copy()
    matrix.indices = matrix.indices.copy()
    matrix.indptr = matrix.indptr.copy()
    return matrix


def _class_distribution(y: list[int], labels: list[str]) -> dict[str, int]:
    counts = Counter(y)
    return {labels[i]: counts.get(i, 0) for i in range(len(labels))}


def fit_and_eval_baselines(
    train_texts: list[str],
    train_labels: list[int],
    eval_texts: list[str],
    eval_labels: list[int],
    labels: list[str],
    *,
    seed: int = 42,
    max_features: int = 200_000,
    min_df: int = 2,
) -> dict:
    """训练并评估两个经典模型，返回指标 + 少量诊断信息。"""
    t0 = time.time()
    vectorizer = TfidfVectorizer(
        lowercase=True,
        strip_accents="unicode",
        ngram_range=(1, 2),
        min_df=min_df,
        max_df=0.9,
        sublinear_tf=True,
        max_features=max_features,
        dtype=np.float32,
    )
    x_train = _writable_csr(vectorizer.fit_transform(train_texts))
    x_eval = _writable_csr(vectorizer.transform(eval_texts))
    vectorize_seconds = time.time() - t0

    specs = {
        "linear_svc": LinearSVC(C=1.0, dual="auto", max_iter=10_000, random_state=seed),
        # n_jobs=1：joblib 的 loky 后端会把稀疏矩阵以只读 memmap 送进子进程，而
        # sklearn 1.8 的 LogisticRegression.fit 里有 np.max(X)，它会触发 scipy 原地
        # 排序 → "WRITEBACKIFCOPY base is read-only"。串行拟合 24 个二分类器只需几十秒。
        "logreg": OneVsRestClassifier(
            LogisticRegression(C=4.0, solver="liblinear", max_iter=3_000, tol=1e-3, random_state=seed),
            n_jobs=1,
        ),
    }

    models: dict[str, dict] = {}
    for name, estimator in specs.items():
        start = time.time()
        with warnings.catch_warnings():
            # 高维稀疏文本上 liblinear/LinearSVC 常报未收敛；记录而不是打断
            warnings.simplefilter("ignore", ConvergenceWarning)
            # threading 后端共享内存、不走 memmap；即便把 n_jobs 改回 -1 也不会踩只读。
            with parallel_backend("threading"):
                estimator.fit(x_train, train_labels)
        fit_seconds = time.time() - start
        pred = estimator.predict(x_eval)
        metrics = compute_metrics(eval_labels, pred.tolist(), labels)
        models[name] = {
            "name": name,
            "estimator": type(estimator).__name__,
            "fit_seconds": fit_seconds,
            "metrics": metrics,
            "pred": pred.tolist(),
        }

    # 以 macro-F1 选主基线（24 类不平衡，accuracy 会骗人）
    main_name = max(models, key=lambda k: models[k]["metrics"]["macro_f1"])

    return {
        "vectorizer": {
            "type": "TfidfVectorizer",
            "ngram_range": [1, 2],
            "min_df": min_df,
            "max_features": max_features,
            "n_features_actual": int(x_train.shape[1]),
            "train_docs": int(x_train.shape[0]),
            "fit_seconds": vectorize_seconds,
        },
        "models": models,
        "main": main_name,
        "train_class_counts": _class_distribution(train_labels, labels),
    }
