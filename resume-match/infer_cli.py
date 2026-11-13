#!/usr/bin/env python3
"""简历 → 24 类岗位匹配的推理入口（与后端约定的硬契约）。

用法（必须能这样跑通）：
    python -I infer_cli.py --model-dir <DIR> --text-file <PATH> [--top-k 5]

stdout 只输出一行 JSON：
    {"category":"INFORMATION-TECHNOLOGY","confidence":0.87,
     "top_k":[{"code":"INFORMATION-TECHNOLOGY","score":0.87},{"code":"ENGINEERING","score":0.05}],
     "model_version":"deberta-v3-base@<run_id>",
     "scores":{"ACCOUNTANT":0.001,...}}   # 24 个类别，和为 1

约定：
  * 成功退出码 0；
  * 任何失败（模型目录不存在、缺 label2id、缺 torch、文本读不了）退出码非 0，
    错误只写 stderr，stdout 不输出半截 JSON；
  * 自动选设备：有 CUDA 用 CUDA，否则 CPU。

关于 `python -I`：隔离模式会把脚本目录从 sys.path 里去掉，所以本文件在 main()
里显式把脚本目录插回去，再 import 同目录的 infer.py（模块顶层不依赖 torch，
因此没装 torch 的机器上 `--help` 也能正常打印）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="infer_cli.py",
        description="对一份英文简历纯文本做 24 类岗位匹配，输出一行 JSON 到 stdout。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python -I infer_cli.py --model-dir runs/20260101-120000/best --text-file resume.txt\n"
            "  python -I infer_cli.py --model-dir best --text-file resume.txt --top-k 3\n"
            "\n"
            "退出码: 0 成功；2 参数/文本错误；3 模型或依赖加载失败；4 显式指定了不可用的 CUDA；1 其他。\n"
        ),
    )
    parser.add_argument("--model-dir", required=True, help="train.py / train_pair.py 保存的 best/ 目录")
    parser.add_argument("--text-file", required=True, help="UTF-8 简历纯文本文件")
    parser.add_argument(
        "--jd-file",
        default=None,
        help="UTF-8 岗位 JD 纯文本文件；pair 模型会额外输出 jd_match_score",
    )
    parser.add_argument("--top-k", type=int, default=5, help="返回前 k 个岗位（默认 5，最大 24）")
    parser.add_argument(
        "--device",
        default="auto",
        help="auto（默认，有 CUDA 用 CUDA 否则 CPU）/ cpu / cuda / cuda:0",
    )
    parser.add_argument("--max-length", type=int, default=None, help="覆盖 checkpoint 里的 max_length")
    parser.add_argument(
        "--allow-dry-run",
        action="store_true",
        help="允许加载 --dry-run 生成的随机权重检查点（仅用于验证链路）",
    )
    return parser


def _read_text(path_str: str) -> str:
    path = Path(path_str).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"找不到 --text-file: {path}")
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise UnicodeDecodeError(
            exc.encoding, exc.object, exc.start, exc.end, f"{path} 不是合法 UTF-8 文本"
        ) from exc
    if not text.strip():
        raise ValueError(f"文本文件为空: {path}")
    return text


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # 先读文本：输入错误不该走到加载模型那一步。
    try:
        text = _read_text(args.text_file)
    except FileNotFoundError as exc:
        print(f"infer_cli: error: {exc}", file=sys.stderr)
        return 2
    except (UnicodeDecodeError, ValueError) as exc:
        print(f"infer_cli: error: 读取文本失败: {exc}", file=sys.stderr)
        return 2

    jd_text = None
    if args.jd_file:
        try:
            jd_text = _read_text(args.jd_file)
        except FileNotFoundError as exc:
            print(f"infer_cli: error: {exc}", file=sys.stderr)
            return 2
        except (UnicodeDecodeError, ValueError) as exc:
            print(f"infer_cli: error: 读取 JD 失败: {exc}", file=sys.stderr)
            return 2

    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from infer import MatcherError, ResumeMatcher  # noqa: PLC0415 - 延迟到 argparse 之后

        matcher = ResumeMatcher(
            model_dir=args.model_dir,
            device=args.device,
            max_length=args.max_length,
            allow_dry_run=args.allow_dry_run,
        )
        result = matcher.predict(text, top_k=args.top_k, jd_text=jd_text)
    except MatcherError as exc:
        print(f"infer_cli: error: {exc}", file=sys.stderr)
        return int(exc.exit_code)
    except Exception as exc:  # noqa: BLE001 - CLI 边界，保证不留下半截 JSON
        print(f"infer_cli: error: 未预期失败: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    # 只在这一刻写 stdout，且一次写完。
    line = json.dumps(result, ensure_ascii=False)
    sys.stdout.write(line + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
