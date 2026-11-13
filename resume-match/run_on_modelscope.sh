#!/usr/bin/env bash
# 在 ModelScope Notebook（PAI-DSW）里一键跑通简历-岗位匹配训练。
#
# 用法：把 resume-match-code.tar.gz 和 Resume.csv.gz 传到 /mnt/workspace/，
# 然后执行：
#     bash run_on_modelscope.sh
#
# 可用环境变量覆盖：
#     MODEL_ID      默认 microsoft/deberta-v3-base（魔搭镜像，内网下载快）
#     EPOCHS        默认 8
#     BATCH_SIZE    默认 16（24GB 显存够用；OOM 就降到 8）
#     MAX_LENGTH    默认 512
#     WORKDIR       默认 /mnt/workspace/resume-match
set -euo pipefail

WORKDIR="${WORKDIR:-/mnt/workspace/resume-match}"
MODEL_ID="${MODEL_ID:-microsoft/deberta-v3-base}"
MODEL_DIR="${MODEL_DIR:-/mnt/workspace/models/deberta-v3-base}"
EPOCHS="${EPOCHS:-8}"
BATCH_SIZE="${BATCH_SIZE:-16}"
MAX_LENGTH="${MAX_LENGTH:-512}"
PIP_INDEX="${PIP_INDEX:-https://mirrors.aliyun.com/pypi/simple/}"

echo "== 1/5 环境检查 =="
python -V
df -h /mnt/workspace | tail -1
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
else
  echo "警告：没有 nvidia-smi，训练会退回 CPU，非常慢"
fi

echo "== 2/5 解压代码与数据 =="
mkdir -p "$WORKDIR"
tar -xzf /mnt/workspace/resume-match-code.tar.gz -C "$WORKDIR"
gzip -dc /mnt/workspace/Resume.csv.gz > "$WORKDIR/Resume.csv"
ls -lh "$WORKDIR/Resume.csv"

echo "== 3/5 安装依赖 =="
python -m pip install -q -U pip
python -m pip install -q -r "$WORKDIR/requirements-train.txt" -i "$PIP_INDEX"
python -m pip install -q modelscope -i "$PIP_INDEX"

echo "== 4/5 下载基座模型 =="
if [ ! -f "$MODEL_DIR/config.json" ]; then
  modelscope download --model "$MODEL_ID" --local_dir "$MODEL_DIR"
else
  echo "已存在，跳过：$MODEL_DIR"
fi
ls -lh "$MODEL_DIR" | head

echo "== 5/5 开始训练 =="
# 默认 fp32：ModelScope 上的 microsoft/deberta-v3-base 权重是 fp16，
# DeBERTa-v3 在 fp16 参数下前向直接 NaN（2026-11-14 实测全权重变 NaN）。
# 想试混合精度再传 AMP=--bf16，但脚本已强制把参数转成 fp32，autocast 自己做半精度。
AMP="${AMP:-}"
RUN_DIR="$WORKDIR/runs/$(date +%Y%m%d-%H%M%S)"
cd "$WORKDIR"

if [ "${SMOKE:-0}" = "1" ]; then
  echo "冒烟测试：64 条样本 1 个 epoch，先确认 loss 不是 NaN"
  python train.py \
    --csv "$WORKDIR/Resume.csv" --split "$WORKDIR/splits/split.csv" \
    --model-name "$MODEL_DIR" --out-dir "$WORKDIR/runs/smoke" \
    --epochs 1 --batch-size "$BATCH_SIZE" --max-length "$MAX_LENGTH" \
    --lr 2e-5 --limit-train 64 --limit-val 64 $AMP
  echo "冒烟通过，继续全量训练"
fi

if [ "${PAIR:-0}" = "1" ]; then
  echo "== 简历-JD 配对训练（cross-encoder）=="
  PAIR_EPOCHS="${PAIR_EPOCHS:-5}"
  if [ ! -f "$WORKDIR/data/resume_zh.jsonl" ]; then
    echo "错误：缺少 data/resume_zh.jsonl（中文训练数据）" >&2
    exit 1
  fi

  if [ "${PAIR_SMOKE:-1}" = "1" ]; then
    echo "--- 冒烟：48 条训练 / 48 条验证，确认链路与 loss 正常 ---"
    python train_pair.py \
      --csv "$WORKDIR/Resume.csv" \
      --split "$WORKDIR/splits/split.csv" \
      --jd "$WORKDIR/jd/jobs_24.yaml" \
      --zh-data "$WORKDIR/data/resume_zh.jsonl" \
      --model-name "$MODEL_DIR" \
      --out-dir "$WORKDIR/runs/pair-smoke" \
      --epochs 1 --batch-size "$BATCH_SIZE" --max-length "$MAX_LENGTH" \
      --lr 2e-5 --limit-train 48 --limit-val 48 --patience 1 $AMP
    python - <<'PY'
import json, math, sys
path = "runs/pair-smoke/metrics.json"
report = json.load(open(path))
loss = report["history"][0]["train_loss"]
recall = report["best_val"]["recall_at_1"]
if not math.isfinite(loss) or not math.isfinite(recall):
    sys.exit(f"冒烟失败：train_loss={loss} recall@1={recall}")
print(f"冒烟通过：train_loss={loss:.4f} val Recall@1={recall:.4f}")
PY
  fi

  python train_pair.py \
    --csv "$WORKDIR/Resume.csv" \
    --split "$WORKDIR/splits/split.csv" \
    --jd "$WORKDIR/jd/jobs_24.yaml" \
    --zh-data "$WORKDIR/data/resume_zh.jsonl" \
    --model-name "$MODEL_DIR" \
    --out-dir "$RUN_DIR" \
    --epochs "$PAIR_EPOCHS" \
    --batch-size "$BATCH_SIZE" \
    --max-length "$MAX_LENGTH" \
    --lr 2e-5 \
    --neg-per-pos "${NEG_PER_POS:-1}" \
    --jd-dropout "${JD_DROPOUT:-0.2}" \
    $AMP \
    2>&1 | tee "$WORKDIR/train-pair-console.log"

  echo
  echo "评测测试集（24 选 1 + 证伪判据）："
  python evaluate_pair.py \
    --model-dir "$RUN_DIR/best" \
    --csv "$WORKDIR/Resume.csv" \
    --split "$WORKDIR/splits/split.csv" \
    --jd "$WORKDIR/jd/jobs_24.yaml" \
    --which test 2>&1 | tee "$WORKDIR/eval-pair-console.log"

  echo
  echo "训练完成，产物在：$RUN_DIR"
  echo "打包下载："
  echo "  cd $(dirname "$RUN_DIR") && tar -czf /mnt/workspace/resume-match-pair.tar.gz $(basename "$RUN_DIR")"
  exit 0
fi

python train.py \
  --csv "$WORKDIR/Resume.csv" \
  --split "$WORKDIR/splits/split.csv" \
  --model-name "$MODEL_DIR" \
  --out-dir "$RUN_DIR" \
  --epochs "$EPOCHS" \
  --batch-size "$BATCH_SIZE" \
  --max-length "$MAX_LENGTH" \
  --lr 2e-5 \
  $AMP \
  2>&1 | tee "$WORKDIR/train-console.log"

echo
echo "训练完成，产物在：$RUN_DIR"
echo "评估测试集："
echo "  cd $WORKDIR && python test.py --model-dir $RUN_DIR/best --csv $WORKDIR/Resume.csv --split $WORKDIR/splits/split.csv"
echo "打包下载："
echo "  cd $(dirname "$RUN_DIR") && tar -czf /mnt/workspace/resume-match-run.tar.gz $(basename "$RUN_DIR")"
