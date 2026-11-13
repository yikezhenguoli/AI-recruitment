# 简历-岗位匹配：训练、评估与推理

本目录是 24 类简历分类模型的训练/评估/推理代码。输入一份英文简历纯文本，输出它在
24 个职业类别上的概率分布、最匹配的岗位 code，以及模型版本。

> 说明：这里的"匹配"是**24 类分类**（`Resume.csv` 的 `Category`），不是在线的
> 简历-JD 语义打分。`jd/jobs_24.yaml` 只用于把类别 code 映射成中英文岗位名，
> 模型训练与推理都不读取它。

---

## 0. 文件清单

| 文件 | 职责 |
| --- | --- |
| `train.py` | 训练 DeBERTa-v3-base / BERT，按 val macro-F1 保存 `best/` |
| `val.py` | 在固定 val 集评估，含经典基线对照与 bootstrap 区间 |
| `test.py` | 在固定 test 集评估（唯一可作对外结论的指标） |
| `evaluate.py` | val/test 共用评估逻辑与报告生成 |
| `baseline.py` | TF-IDF + LinearSVC / LogisticRegression 非神经基线 |
| `infer_cli.py` | **与后端约定的命令行推理入口**（`python -I`） |
| `infer.py` | `ResumeMatcher` 类，供 Python 代码 import / 本地调试 |
| `common.py` | 数据读取、标签顺序、指标、随机种子等共用工具 |
| `requirements-train.txt` | 训练侧依赖（与 `apps/api` 的 venv 无关） |
| `README-train.md` | 本文件 |

`data-processing.py` 是早先的 3 行 pandas 示例，本流程不依赖它。

---

## 1. 数据与固定切分（只读，不要改）

* 原始数据：`data/archive/archive/Resume/Resume.csv`，列 `ID, Resume_str, Resume_html, Category`。
  共 2484 行，去掉 `Resume_str` 为空（ID `12632728`）后 **2483 行 / 24 类**。
  该目录是外部归档数据：脚本只按路径读 CSV，不会 `chdir` 进去，也不从那里执行任何东西。
* 固定切分：`splits/split.csv`，列 `id, category, split`，seed=42。
  **脚本直接读它，绝不重新划分。** 已核对：

  | split | 条数 |
  | --- | --- |
  | train | 2283 |
  | val | 100 |
  | test | 100 |

  24 个类别每类在 val / test 都有样本，最少 4 条（BPO、AUTOMOBILE 等），最多 5 条。
  因此**单次 test 评估的 95% 置信区间大约是 ±9 个百分点**，看差异时必须看本脚本给出的
  bootstrap 区间，不要拿小数点后第三位当结论。
* 标签顺序 = `sorted(category)`，与 `split.csv` 完全一致，并写入 `label2id.json`。
  推理端只信这个文件，不自行排序。
* `splits/summary.json`、`jd/jobs_24.yaml`、`scripts/prepare_split.py` 都是只读资产。

### 数据不入 git

仓库根目录的 `.gitignore` 已排除 `resume-match/*`，只放行：

```
resume-match/jd/
resume-match/scripts/
resume-match/splits/
```

也就是说原始 CSV（含 `Resume_html`）不会进版本库。**注意同一条规则也把本目录的训练脚本、
README、requirements 一起排除了**：如果要把这些代码纳入版本管理，需要另外调整忽略规则或
单独归档；本次任务按要求不执行任何 `git add` / `git commit`。

---

## 2. 云服务器环境安装

```bash
cd /path/to/AI-recruitment/resume-match

python3 -m venv .venv-train
source .venv-train/bin/activate
python -m pip install -U pip

# 1) 先按服务器 CUDA 版本装 torch（示例 cu121；V100 请用 cu118/cu121，不要用 cu130）
pip install torch --index-url https://download.pytorch.org/whl/cu121
# 2) 再装其余依赖（已满足的 torch 会被跳过）
pip install -r requirements-train.txt
```

必须用 venv，**不要 `pip install --user`**：推理入口的约定是 `python -I infer_cli.py ...`，
隔离模式（`-I`）会屏蔽 user site-packages。装在 venv 的 site-packages 里则不受影响。

HuggingFace 访问（国内/无直连时）：

```bash
export HF_ENDPOINT=https://hf-mirror.com
export HF_HUB_DISABLE_XET=1      # 镜像不代理 xet，不关掉可能 401/超时
# 如模型需要鉴权：
# export HF_TOKEN=hf_xxx
```

完全离线时：在能联网的机器上下载模型目录（`microsoft/deberta-v3-base` 整个目录），
拷到服务器后用 `--model-name /abs/path/to/deberta-v3-base`。DeBERTa-v3 的 tokenizer
需要 `sentencepiece`（已写进 requirements）。

---

## 3. 一键跑法

```bash
cd /path/to/AI-recruitment/resume-match
source .venv-train/bin/activate
export HF_ENDPOINT=https://hf-mirror.com HF_HUB_DISABLE_XET=1

# 训练（默认输出 runs/<timestamp>/）
python train.py \
  --model-name microsoft/deberta-v3-base \
  --epochs 5 --batch-size 8 --grad-accum 2 --fp16 \
  --max-length 512 --lr 2e-5

# 评估（把 RUN 换成上面的 runs/<timestamp>）
python val.py  --model-dir runs/RUN/best
python test.py --model-dir runs/RUN/best
```

显存参考：DeBERTa-v3-base + 512 token 在 8GB 卡上建议 `--batch-size 4 --grad-accum 4`；
V100/A100 可用 16～32。OOM 就降 batch、加 grad-accum，等价 batch 不变。

训练超参默认值：AdamW，lr 2e-5，weight decay 0.01，warmup 6%，label smoothing 0.1，
梯度裁剪 1.0，早停 patience=3（按 val macro-F1，min_delta=5e-4）。全部随机种子固定
（random / numpy / torch / cuda），并开启 cudnn deterministic；不同卡型仍可能有极小数值差异。

### 常用参数

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `--model-name` | `microsoft/deberta-v3-base` | 也支持 `bert-base-uncased` 或本地模型目录 |
| `--epochs` | 5 | 早停可能提前结束 |
| `--batch-size` | 8 | 单卡 batch（不含累积） |
| `--lr` | 2e-5 | |
| `--max-length` | 512 | 简历中位长度约 5.9k 字符，截断后只覆盖前 512 token |
| `--grad-accum` | 1 | 梯度累积 |
| `--freeze-layers` | 0 | 冻结底部 N 层编码器；`-1` 冻结整个底座（只训分类头） |
| `--fp16` | 关 | 仅 CUDA 生效，CPU 上自动忽略并提示 |
| `--class-weights` | 关 | 按训练集频次反比加权 CE，可能抬高 macro-F1 |
| `--truncation` | `head` | `head_tail` = 保留开头一半 + 结尾一半 token（未经实测的启发式，建议在 val 上对比后再定） |
| `--out-dir` | `runs/<timestamp>` | run_id 取目录名 |
| `--seed` | 42 | |

---

## 4. 训练输出结构

```
runs/<run_id>/
├── train.log                 # 每个 epoch 的 train loss / val acc / val macro-F1
├── metrics.json              # 同上，机器可读；每 epoch 覆写一次
├── label2id.json             # 24 类顺序（= sorted(category)）
├── id2label.json
├── infer_config.json         # max_length / truncation / model_version / labels
├── model_version.json
├── best/                     # save_pretrained + tokenizer；推理指向这里
│   ├── config.json
│   ├── model.safetensors（或 pytorch_model.bin）
│   ├── tokenizer 文件
│   ├── label2id.json         # 副本，infer 先在模型目录找
│   ├── infer_config.json
│   └── model_version.json
├── eval-val/                 # val.py 产物
└── eval-test/                # test.py 产物
```

每个 `eval-*` 目录内含：`metrics.json`、`report.txt`、`confusion_matrix.csv`、
`confusion_matrix.txt`（人类可读）、`per_class.csv`、`predictions.csv`（逐条预测）。

`metrics.json` 的 `epochs` 数组每项含：`train_loss`、`val_loss`、`val_accuracy`、
`val_macro_f1`、`val_weighted_f1`、`elapsed_seconds`、`optimizer_steps`、`lr_end`、
`improved`；顶层还有 `best_epoch`、`best_val_macro_f1`、`stopped_early`、`total_train_seconds`。

`best/` 同时保存了 label2id 与 infer_config 的副本，因此 `--model-dir` 可以直接指向
`runs/<run_id>/best`（后端约定如此）。找不到 `label2id.json` 时推理会直接报错退出，
不会猜标签顺序。

---

## 5. 评估、经典基线与"效果最好"的诚实口径

`val.py` / `test.py` 都会同时跑：

1. 神经模型（checkpoint）；
2. 非神经基线：`TfidfVectorizer(ngram 1-2, min_df=2, sublinear_tf, max_features=200k)` +
   `LinearSVC(C=1.0)` 和 `LogisticRegression(C=4.0, liblinear)`。
   向量器只在 **train** 上 fit，评估集只 transform；两个基线都不额外调参。

输出并排的 `accuracy / macro-F1 / weighted-F1`、每类 precision/recall/F1、完整 24×24
混淆矩阵，以及被误判最多的 5 组"真实类别 → 预测类别"（附占该类比例）。

为什么按 macro-F1 选模型：BPO 只有 22 份、val/test 各 4 条，accuracy 会被
INFORMATION-TECHNOLOGY 等大类主导，掩盖小类崩塌。

### 差异是不是噪声

n=100 的 test 集太小，0.01～0.03 的差距完全可能是抽样波动。脚本对"神经 vs 主基线"
做 **1000 次配对 bootstrap**，给出 accuracy 与 macro-F1 差值的 95% CI，并自动生成结论：

* CI 跨 0 → 写"两者差异与随机波动无法区分"，**不能宣称效果更好**；
* CI 整体 >0 → 该 test 集上神经模型更好，但仍要注明 n=100；
* CI 整体 <0 → 经典基线更好，按事实写，不美化。

### 经典基线实测（本机 CPU，sklearn 1.7.2）

这条基线是**真实测出来的**，与神经 checkpoint 无关：在完整 train（2283 条）上拟合，
在完整 test（100 条）上评估。

| 模型 | split | accuracy | macro-F1 | weighted-F1 |
| --- | --- | --- | --- | --- |
| TF-IDF + LinearSVC | test | **0.5400** | **0.4982** | 0.5034 |
| TF-IDF + OvR LogisticRegression | test | — | 0.4592 | — |
| TF-IDF + LinearSVC | val | 0.5800 | 0.5393 | 0.5397 |

TF-IDF 实际 169,460 维（1-2gram，min_df=2）；向量化 2.9s、LinearSVC 拟合 1.3s，
整次 `test.py` 约 15s（含 bootstrap）。这是神经模型必须超过的门槛。

**神经模型的真实指标未实测**：本机只跑了 16 条样本的 dry-run 与微型随机模型链路，
这些数字不能代表 DeBERTa。云上训练完成后，请用 `test.py` 打印的并排表格和
bootstrap CI 替换此处的"神经模型"一列，不要引用任何未测量的预期值。

### 预期差异（未实测，不要当结论引用）

经验上 DeBERTa 这类预训练模型在 24 类简历分类上通常略优于 TF-IDF + LinearSVC，
但这份数据只有 2283 条训练样本、test 只有 100 条，差距很可能落在置信区间内。
如果 `test.py` 的 CI 跨 0，就如实写"两者无法区分"；如果基线更好，也照写。
脚本会自动生成这段结论，README/汇报材料请直接采用脚本输出。

另外注意：`val.py` 的指标是**乐观的**——`best/` 正是按 val macro-F1 选出来的，
存在选择偏差；对外结论只用 `test.py`。

### 提升效果的可试项（每次只改一个，在 val 上比较）

1. `--max-length 512` 已接近大部分卡的极限；`--truncation head_tail` 可让尾部技能/教育
   信息进入模型，但未经实测。
2. `--class-weights` 可能改善小类召回，从而抬 macro-F1；也可能伤大类，必须实测。
3. `--freeze-layers 6` / `-1` 在数据少时降低过拟合（会减少可训练参数）。
4. 更强的底座（如 `microsoft/deberta-v3-large`）显存要求约翻倍。
5. 学习率/epoch 的小网格，但**不要用 test 调参**，否则 test 失去意义。

---

## 6. 无 GPU / 无网络：`--dry-run`

```bash
# 尝试真实模型（首次可能下载约 500MB；下载/加载失败会打印醒目警告并回落）
python train.py --dry-run --device cpu

# 完全离线：不尝试下载，直接用随机微型 BERT
python train.py --dry-run --dry-run-tiny --device cpu
```

dry-run 的行为：

* 只取 **16 条 train + 16 条 val**（按类别轮流抽样，尽量覆盖多个类）；
* `max_length<=64`、1 epoch、batch<=4；
* 完整跑一遍"读 CSV → 分词 → 前向 → 反向 → val 指标 → 保存 checkpoint"；
* 输出到 `runs/dryrun-<timestamp>/dryrun-best/`，并写入 `DRY_RUN.txt`；
* 随机权重没有任何训练意义，**不能用于推理**；`infer_cli.py` 默认拒绝加载带
  `DRY_RUN.txt` 的目录（只调试链路时可加 `--allow-dry-run`）。

本机没有网络时的清晰提示：未加 `--dry-run-tiny` 时，加载失败会打印
`HF_ENDPOINT` / `HF_HUB_DISABLE_XET` / 离线模型目录 / `HF_TOKEN` / socks 代理的处理办法，
然后才回落到微型模型；**正常训练（不加 `--dry-run`）失败则直接非 0 退出，绝不静默下降**。

---

## 7. 推理契约（后端按这个调用，字段名不要改）

```bash
python -I infer_cli.py --model-dir <DIR> --text-file <PATH> [--top-k 5]
```

stdout 只输出**一行** JSON：

```json
{"category":"INFORMATION-TECHNOLOGY","confidence":0.87,
 "top_k":[{"code":"INFORMATION-TECHNOLOGY","score":0.87},{"code":"ENGINEERING","score":0.05}],
 "model_version":"deberta-v3-base@<run_id>",
 "scores":{"ACCOUNTANT":0.001,"ADVOCATE":0.002}}
```

* `scores` 一定包含全部 24 类，浮点数，和为 1（实测误差 0，约束 1e-6）；
* `top_k` 降序，`top_k[0]` 与 `category`/`confidence` 一致；`--top-k` 取值 1..24；
* `model_version` 形如 `<模型短名>@<run_id>`，来自 `best/model_version.json`；
* 成功退出码 0；失败退出码：2 参数/文本错误、3 模型或依赖加载失败、4 显式指定了不可用
  的 CUDA、1 其他；错误只写 stderr，stdout 不输出半截 JSON；
* 设备自动选择：有 CUDA 用 CUDA，否则 CPU；CPU 单条推理在几十秒内（`max_length` 取
  checkpoint 训练时的值，默认 512）。

Python 侧复用：

```python
from infer import ResumeMatcher
m = ResumeMatcher("runs/RUN/best", device=None)   # None/auto
result = m.predict(text, top_k=5)                 # 与 CLI 相同结构
batch = m.predict_batch([text1, text2], top_k=5)
```

后端不需要装 torch、也不需要 import 本目录任何东西——直接起子进程跑 `infer_cli.py`。

---

## 8. 常见错误排查

| 现象 | 原因 / 处理 |
| --- | --- |
| `Unknown scheme for proxy URL ... 'socks://...'` | httpx 只认 `socks5://` 且需要 `socksio`。`unset ALL_PROXY`，或改成 `SOCKS5://` 并 `pip install socksio` |
| 下载超时 / 401 | 设 `HF_ENDPOINT=https://hf-mirror.com`、`HF_HUB_DISABLE_XET=1`；必要时 `HF_TOKEN` |
| `Couldn't instantiate the backend tokenizer ... sentencepiece` | `pip install sentencepiece`（DeBERTa-v3 必需） |
| `python -I` 下 `ModuleNotFoundError: torch` | 依赖装到了 `--user` 目录，被 `-I` 屏蔽；改用 venv 安装 |
| CUDA OOM | 降 `--batch-size`、升 `--grad-accum`，或降 `--max-length` |
| `--fp16` 没提速 | 只在 CUDA 生效；CPU 会打印提示并关闭 |
| 训练指标正常、推理分布很平 | 检查 `label2id.json` 是否与训练时一致；确认 `--model-dir` 是训练输出的 `best/` 而非空的 `dryrun-best/` |
| 结果不可复现 | 已固定 random/numpy/torch/cuda 与 cudnn deterministic，但不同 GPU/驱动仍可能有浮点差异 |

---

## 9. 已知限制

1. 这是 **24 类闭集分类**，永远会给出这 24 类之一，没有"不匹配/其他"类别。
2. `Resume_str` 中位长度约 5.9k 字符；`max_length=512` 会截掉尾部内容。`head_tail`
   是一种缓解手段，但本机未做效果验证。
3. 训练/评估只用 train 训练、val 选模型、test 报数；脚本不会自动合并 val 重训。
4. `jd/jobs_24.yaml` 不参与模型训练，只用于报告中的中英文岗位名。
5. 本目录不含服务化部署（后端由另一个流程负责），也不改 `apps/`、`frontend/`。

---

## 10. 本次已验证范围

* 8 个 Python 文件全部通过 `ast.parse`；`python -I infer_cli.py --help` 可打印帮助。
* `--dry-run --dry-run-tiny`（完全离线随机微型 BERT）跑通：16+16 样本、前向/反向/验证/保存。
* `--dry-run --model-name hf-internal-testing/tiny-random-BertModel` 跑通真实
  HuggingFace 分词器 + `from_pretrained` 路径；CUDA + `--fp16` + `--grad-accum` +
  `--class-weights` + `head_tail` + `--freeze-layers -1` 也各跑通一次。
* 用微型模型训练出正常 `best/` 后，`val.py` / `test.py` 的神经评估、混淆矩阵、报告产物
  均已跑通；**经典基线是完整实测的**（见第 5 节表格）。完整 DeBERTa 训练与神经侧真实
  指标**未实测**（本机只做了 16 条样本的 dry-run）。
* 在隔离模式（`python -I`）下验证了推理契约：stdout 单行 JSON、24 类和为 1、
  `top_k`/`confidence` 一致；模型目录缺失、缺 `label2id.json`、文本缺失/为空、
  `--top-k 99`、显式 `--device cuda` 但 CUDA 不可用等失败路径均为非 0 退出且 stdout 为空。
* 用 `split.csv` 实测统计：train 2283 / val 100 / test 100，24 类每类 val、test 至少 4 条。

---

## 11. 配对（pair）训练：让 JD 真正参与打分

分类模型（`train.py`）只读简历，JD 从未进入前向计算——后端的 `match_score`
实际是"简历最像哪一类岗位"，与具体岗位 JD 无关。`train_pair.py` 改成
cross-encoder：`[CLS] 简历 [SEP] 岗位 JD [SEP]` → 匹配概率。

### 跑法

```bash
# 1) 生成中文训练数据（只翻 train 集，val/test 保持纯英文，翻译体不参与对外指标）
python translate_zh.py --per-class 20 --concurrency 8 --out data/resume_zh.jsonl

# 2) 训练 + 测测试集
PAIR=1 bash run_on_modelscope.sh
# 常用覆盖：PAIR_EPOCHS=5 BATCH_SIZE=16 NEG_PER_POS=1 JD_DROPOUT=0.2
# 冒烟默认开启（PAIR_SMOKE=0 可关），会先跑 48 条训练 / 48 条验证
```

### 训练样本

* 正配对：简历 × 它所属类别的 JD，标签 1
* 负配对：简历 × 随机异类 JD，标签 0，每个正样本配 `--neg-per-pos` 条
* 中文简历配中文 JD、英文配英文，负样本与正样本同语言（避免模型靠语言一致作弊）
* `--jd-dropout 0.2`：训练时随机丢掉 JD 的非首行（首行是岗位名，永远保留）。
  否则模型只要记住 24 段固定文本就能分开正负，线上换成数据库里的 JD 就会失真

### 评测口径（`evaluate_pair.py`）

一条简历 × 24 个 JD 的 **24 选 1 排名**，报 Recall@1/3/5、MRR，
并与 TF-IDF 余弦基线做配对 bootstrap。

三条**证伪判据**（缺一不可）：

| 判据 | 期望 | 说明 |
| --- | --- | --- |
| 负配对敏感性 | 平均 margin 明显大于 0 | 正配概率 − 其余 23 个 JD 平均概率；贴近 0 说明 JD 没起作用 |
| JD 只留标题 | Recall@1 应明显下降 | 不降说明模型没在读 JD 正文 |
| JD 打乱 | Recall@1 ≈ 1/24 = 0.042 | 正确 JD 已不在候选里，还高就是流程有问题 |

### 推理

```bash
python -E infer_cli.py --model-dir <pair-best> --text-file resume.txt --jd-file jd.txt
```

pair 模型输出在旧契约上**多一个字段** `jd_match_score`（0~1，简历与该 JD 的配对概率）；
`confidence`/`scores` 仍是 24 个参考 JD 上的归一化分布，语义不变。后端优先用
`jd_match_score` 作 `match_score`。

### 已知限制（必须写进报告）

1. 配对概率是在"随机异类 JD"当负样本下训出来的，**不是岗位胜任度的校准概率**；
   多数正配都会接近 1，有意义的用法是比较不同岗位之间的相对高低。
2. 模型只见过这 24 段 JD 模板，线上任意 JD 属于分布外输入，`--jd-dropout` 只是缓解。
3. 24 类闭集、没有"不匹配"类别、简历截断等限制同第 9 节。
