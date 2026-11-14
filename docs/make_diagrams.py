"""生成 TTC 平台的项目架构图与 AI 模型架构图（PNG）。

排版自检：渲染后逐条检查文字包围盒是否落在卡片内，越界会打印 OVERFLOW。
"""

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

# matplotlib 只注册了 NotoSansCJK-*.ttc 的第一个 face（JP），字形覆盖简体中文。
plt.rcParams["font.family"] = ["Noto Sans CJK JP", "WenQuanYi Micro Hei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

BG = "#f6f7f9"
INK = "#111827"
MUTED = "#5b6472"
WHITE = "#ffffff"

PALETTE = {
    "front": "#2563eb",
    "api": "#7c3aed",
    "domain": "#0891b2",
    "adapter": "#0d9488",
    "external": "#ea580c",
    "data": "#16a34a",
    "model": "#db2777",
    "offline": "#9aa3af",
}

CHECKS = []  # (卡片标题, patch, [text artist])


def new_canvas(width, height):
    fig, ax = plt.subplots(figsize=(width, height))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")
    CHECKS.clear()
    return fig, ax


def card(ax, x0, y0, x1, y1, title, lines, color, title_size=9.8,
         line_size=8.0, dashed=False, line_gap=None):
    ax.add_patch(FancyBboxPatch(
        (x0, y0), x1 - x0, y1 - y0,
        boxstyle="round,pad=0.0,rounding_size=1.0",
        linewidth=1.2, edgecolor=color,
        facecolor="#fbfbfc" if dashed else WHITE,
        linestyle=(0, (4, 3)) if dashed else "solid", zorder=3,
    ))
    # 顶部色条
    ax.add_patch(FancyBboxPatch(
        (x0, y1 - 0.85), x1 - x0, 0.85,
        boxstyle="round,pad=0.0,rounding_size=0.5",
        linewidth=0, facecolor=color, alpha=0.85, zorder=4,
    ))
    texts = [
        ax.text(x0 + 1.3, y1 - 2.5, title, ha="left", va="top",
                fontsize=title_size, fontweight="bold", color=color, zorder=5),
    ]
    n = max(1, len(lines))
    if line_gap is None:
        line_gap = max(1.4, min(3.1, (y1 - y0 - 5.0) / n))
    y = y1 - 5.0
    for line in lines:
        bold = line.startswith("#")
        texts.append(ax.text(
            x0 + 1.3, y, line[1:] if bold else line, ha="left", va="top",
            fontsize=line_size, color=INK if bold else MUTED, zorder=5,
            fontweight="bold" if bold else "normal",
        ))
        y -= line_gap
    CHECKS.append((title, (x0, y0, x1, y1), texts))


def band(ax, x0, y0, x1, y1, label, color):
    ax.add_patch(FancyBboxPatch(
        (x0, y0), x1 - x0, y1 - y0,
        boxstyle="round,pad=0.0,rounding_size=1.0",
        linewidth=0, facecolor=color, alpha=0.055, zorder=1,
    ))
    ax.text(x0 + 1.0, y1 - 0.35, label, ha="left", va="top", fontsize=7.8,
            color=color, fontweight="bold", zorder=2)


def arrow(ax, x0, y0, x1, y1, color="#94a3b8", lw=1.6):
    ax.add_patch(FancyArrowPatch(
        (x0, y0), (x1, y1), arrowstyle="-|>", mutation_scale=11,
        linewidth=lw, color=color, zorder=6, shrinkA=1, shrinkB=1,
    ))


def heading(ax, main, sub):
    ax.text(4, 97.0, main, ha="left", va="top", fontsize=17,
            fontweight="bold", color=INK)
    ax.text(4, 92.0, sub, ha="left", va="top", fontsize=9.0, color=MUTED)


def verify(fig, ax, label):
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    inv = ax.transData.inverted()
    bad = 0
    for name, (x0, y0, x1, y1), texts in CHECKS:
        for text in texts:
            box = text.get_window_extent(renderer)
            (dx0, dy0), (dx1, dy1) = inv.transform([[box.x0, box.y0], [box.x1, box.y1]])
            if dx0 < x0 - 0.2 or dx1 > x1 + 0.2 or dy0 < y0 - 0.2 or dy1 > y1 + 0.2:
                bad += 1
                print(f"OVERFLOW[{label}] {name}: {text.get_text()[:36]!r}")
    print(f"[{label}] 卡片 {len(CHECKS)} 个，越界文字 {bad} 处")


# ---------------------------------------------------------------- 项目架构图
def project_architecture(path):
    fig, ax = new_canvas(16, 12)
    heading(ax, "TTC 才多对 · 平台架构",
            "分层与适配器设计：api → domains → adapters，领域层只依赖 ports 中的 Protocol")

    # 接入端
    band(ax, 3, 77.4, 97, 90.5, "接入端", PALETTE["front"])
    card(ax, 5, 78.6, 47, 88.3, "HR 工作台  apps/web", [
        "React 18 + Vite · 127.0.0.1:5173",
        "岗位 / 候选人 / 简历 / 匹配 / 面试 / Offer",
        "液态玻璃视觉 · 双账本评估报告",
    ], PALETTE["front"])
    card(ax, 53, 78.6, 95, 88.3, "候选人端  apps/candidate-web", [
        "React + Vite · HTTPS 127.0.0.1:5175",
        "自助注册 · 授权 · 语音面试 · 结果查看",
        "HTTPS 为必须：http 下浏览器不开放麦克风",
    ], PALETTE["front"])

    arrow(ax, 26, 78.6, 26, 75.6)
    arrow(ax, 74, 78.6, 74, 75.6)

    # 接入层
    band(ax, 3, 62.9, 97, 77.2, "接入层", PALETTE["api"])
    card(ax, 5, 64.5, 50, 75.2, "FastAPI  /api/v1", [
        "21 个路由模块：auth jobs resumes candidates",
        "match interviews offers applications consents",
        "evidence talent backup privacy portal progress",
        "JWT 鉴权 · 租户隔离 · 审计 · 统一错误码",
    ], PALETTE["api"])
    card(ax, 52, 64.5, 95, 75.2, "WebSocket 语音中转", [
        "/voice-sessions/{id}/realtime",
        "浏览器 PCM ⇄ 后端 ⇄ DashScope",
        "密钥只留在服务端 · 撤回授权即断连",
        "连接即置会话 live，断开记一次结束",
    ], PALETTE["api"])

    arrow(ax, 26, 64.5, 26, 60.6)
    arrow(ax, 74, 64.5, 74, 60.6)

    # 领域层
    band(ax, 3, 39, 97, 61.5, "领域层  domains", PALETTE["domain"])
    card(ax, 5, 40.5, 27.5, 59.2, "resume", [
        "validate_document",
        "extract_text_with_meta",
        "parse_resume → Claims",
        "timeline 时间线冲突检测",
        "扫描件走 OCR 适配链",
    ], PALETTE["domain"], title_size=9.4)
    card(ax, 29.2, 40.5, 51.7, 59.2, "interview", [
        "build_plan 生成面试计划",
        "latest_resume_text",
        "current_jd",
        "session_instructions",
        "会话 / 转写 / 纪要落库",
    ], PALETTE["domain"], title_size=9.4)
    card(ax, 53.4, 40.5, 75.9, 59.2, "talent", [
        "index_candidate",
        "search_candidates",
        "similar_to",
        "远程 embedding / 本地哈希向量",
        "向量写入与召回重建",
    ], PALETTE["domain"], title_size=9.4)
    card(ax, 77.6, 40.5, 95, 59.2, "backup / core", [
        "snapshot 快照与导出",
        "auth · security",
        "audit · config",
        "errors · contracts",
        "跨域公共能力",
    ], PALETTE["domain"], title_size=9.4)

    arrow(ax, 50, 40.5, 50, 36.6)

    # 适配器层
    band(ax, 3, 21.7, 97, 38.1, "适配器层  adapters（供应商实现都在这里）", PALETTE["adapter"])
    card(ax, 5, 23.5, 24, 36.2, "LLMAdapter", [
        "DeepSeek chat/completions",
        "claims · 解释 · 计划 · 纪要",
        "失败降级，不阻塞主流程",
    ], PALETTE["adapter"], title_size=9.2)
    card(ax, 25.6, 23.5, 44.6, 36.2, "MatcherAdapter", [
        "子进程调用 infer_cli.py",
        "stdout 单行 JSON 契约",
        "缺失时关键词兜底（默认关）",
    ], PALETTE["adapter"], title_size=9.2)
    card(ax, 46.2, 23.5, 65.2, 36.2, "QwenRealtimeAdapter", [
        "DashScope Realtime WebSocket",
        "server_vad 0.65 / 600ms",
        "stub 适配器用于离线演示",
    ], PALETTE["adapter"], title_size=9.2)
    card(ax, 66.8, 23.5, 80.5, 36.2, "StorageAdapter", [
        "简历文件落盘",
        "本地目录实现",
        "可替换为对象存储",
    ], PALETTE["adapter"], title_size=9.2)
    card(ax, 82.1, 23.5, 95, 36.2, "ports.py", [
        "Protocol 定义",
        "领域只认协议",
        "可替换 / 可降级",
    ], PALETTE["adapter"], title_size=9.2)

    arrow(ax, 24, 23.5, 24, 19.6)
    arrow(ax, 60, 23.5, 60, 19.6)

    # 基础设施
    band(ax, 3, 4.4, 97, 20.8, "基础设施与外部服务", PALETTE["external"])
    card(ax, 5, 6.5, 25, 19.2, "PostgreSQL 16", [
        "业务数据 · JSONB · timestamptz",
        "Alembic 0001 → 0006",
        "UUID 主键 · 租户隔离",
    ], PALETTE["data"], title_size=9.2)
    card(ax, 26.6, 6.5, 46.6, 19.2, "任务 Worker", [
        "ttc.tasks.runner",
        "解析 / 匹配等耗时任务",
        "进度接口 + WebSocket 通知",
    ], PALETTE["data"], title_size=9.2)
    card(ax, 48.2, 6.5, 68.2, 19.2, "DeepSeek API", [
        "简历 Claim 抽取",
        "匹配解释 · 出题 · 纪要",
        "失败即降级，不阻塞主流程",
    ], PALETTE["external"], title_size=9.2)
    card(ax, 69.8, 6.5, 95, 19.2, "DashScope", [
        "Qwen Omni Realtime（语音面试）",
        "Qwen-VL 链（扫描件 OCR）",
        "模型与密钥均由 .env 配置",
    ], PALETTE["external"], title_size=9.2)

    ax.text(4, 3.4,
            "约束：领域层不 import 供应商实现；外部模型 / 语音 / 存储 / 检索统一经适配器接入，可替换、可降级。",
            fontsize=8.2, color=MUTED, ha="left", va="top")
    ax.text(4, 0.9,
            "时间统一 RFC 3339 UTC；列表接口游标分页（默认 20 / 上限 100）。",
            fontsize=8.2, color=MUTED, ha="left", va="top")

    verify(fig, ax, "项目架构")
    fig.savefig(path, dpi=200, facecolor=BG, bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)


# ------------------------------------------------------------ AI 模型架构图
def model_architecture(path):
    fig, ax = new_canvas(18, 12.5)
    heading(ax, "TTC · AI 模型架构",
            "在线链路（实线）与离线实验（虚线）；参数与降级行为均取自当前代码")

    # 泳道一
    band(ax, 3, 61, 97, 88.5, "泳道一 · 简历理解与岗位匹配（在线）", PALETTE["model"])
    card(ax, 4.5, 62.5, 25, 86.2, "① 文档 → 文本", [
        "PDF：pypdf 直读",
        "DOCX：python-docx 直读",
        "扫描件：pdftoppm 200dpi",
        "#无文本才触发 OCR",
        "加密/损坏文件直接报错",
    ], PALETTE["front"], title_size=9.6)
    card(ax, 26.6, 62.5, 47.1, 86.2, "② VLM OCR 链", [
        "qwen-vl-ocr → qwen3.5-ocr",
        "→ qwen3-vl-plus",
        "#质量闸门：≥20 字 / 乱码<2%",
        "链上全失败即报错",
        "仅未配 VLM 时用 tesseract",
    ], PALETTE["external"], title_size=9.6)
    card(ax, 48.7, 62.5, 69.2, 86.2, "③ Claim 抽取", [
        "LLM：extract_claims",
        "拆 education / work / project",
        "publication / patent / award / skill",
        "#规则时间线冲突检测",
        "每条保留原文定位与置信度",
    ], PALETTE["adapter"], title_size=9.6)
    card(ax, 70.8, 62.5, 95.5, 86.2, "④ 岗位匹配", [
        "resume-match/infer_cli.py（子进程）",
        "DeBERTa-v3-base · 24 类分类",
        "test acc 0.78 · macro-F1 0.74",
        "#上行为真实简历读数（n=100）",
        "#契约：stdout 单行 JSON",
        "失败可落关键词兜底（默认关）",
        "LLM：explain_match 生成解释",
    ], PALETTE["model"], title_size=9.6)

    arrow(ax, 25, 74, 26.6, 74)
    arrow(ax, 47.1, 74, 48.7, 74)
    arrow(ax, 69.2, 74, 70.8, 74)

    # 泳道二
    band(ax, 3, 36, 97, 59.5, "泳道二 · 授权式语音面试（在线）", PALETTE["model"])
    card(ax, 4.5, 37.5, 28, 57.2, "⑤ 面试计划", [
        "LLM：build_interview_plan",
        "输入：最新简历文本 + 岗位 JD",
        "输出：候选人画像 + 3–6 题",
        "每题带关注点",
        "#生成失败 → 回退固定清单",
        "不影响会话创建",
    ], PALETTE["adapter"], title_size=9.6)
    card(ax, 29.6, 37.5, 66, 57.2, "⑥ 实时语音对话  Qwen Omni Realtime", [
        "浏览器 16kHz PCM ⇄ 后端中转 ⇄ DashScope 24kHz",
        "server_vad：threshold 0.65 · silence 600ms · prefix 300ms",
        "interrupt_response：候选人开口即打断播报",
        "前端看门狗：双方静默 15s 主动请重述；回复卡住 20s 取消重试",
        "#为什么改阈值：默认 0.5 会把面试官自己的播报判成候选人插话",
    ], PALETTE["external"], title_size=9.6)
    card(ax, 67.6, 37.5, 95.5, 57.2, "⑦ 面试纪要", [
        "LLM：summarize_interview",
        "输入：计划 + 完整转写",
        "输出：表现分析 · 追问建议",
        "简历一致性分类：",
        "一致 / 补充 / 冲突 / 待核验",
        "供 HR 人工复核，不自动决策",
    ], PALETTE["adapter"], title_size=9.6)

    arrow(ax, 28, 47, 29.6, 47)
    arrow(ax, 66, 47, 67.6, 47)

    # 泳道三
    band(ax, 3, 13, 97, 34.5, "泳道三 · 离线模型实验（未接入在线链路）", PALETTE["offline"])
    card(ax, 4.5, 14.4, 33, 32.2, "GBDT v3（对照实验）", [
        "HistGradientBoostingClassifier",
        "14 维特征：字符 n-gram 余弦、技能命中",
        "年限 / 学历差、意向标题、长度比",
        "test Recall@1 0.98（vs TF-IDF 0.89）",
        "#500 条全合成简历",
        "合成数据读数，不代表真实泛化",
    ], PALETTE["offline"], title_size=9.4, dashed=True)
    card(ax, 34.6, 14.4, 63.1, 32.2, "TF-IDF 基线", [
        "char 2–4 gram · sublinear_tf · min_df=2",
        "test Recall@1 0.89 · MRR 0.937",
        "word 版（中文未分词）R@1 0.09，仅作参考",
        "#结论：排序依赖简历与 JD 正文对应",
        "shuffled_jd 塌到随机水平，反证非泄漏",
    ], PALETTE["offline"], title_size=9.4, dashed=True)
    card(ax, 64.7, 14.4, 95.5, 32.2, "RISM（经历—面试维度多标签）", [
        "BAAI/bge-small-zh-v1.5 文本嵌入",
        "15 类标签：数据证据 / 风险意识 /",
        "降本增效 / 技术决策 / 团队协作 …",
        "已备数据与 embedding 缓存",
        "#训练代码未入库（仓库内为占位空文件）",
        "状态：实验准备阶段",
    ], PALETTE["offline"], title_size=9.4, dashed=True)

    ax.text(4, 11.0,
            "标注说明：# 开头的行是阈值、降级规则或结论；未标 # 的行是模型的输入输出。",
            fontsize=8.2, color=MUTED, ha="left", va="top")
    ax.text(4, 8.4,
            "在线链路上共有 4 处 LLM 调用点（claims / 解释 / 出题 / 纪要）与 1 段实时语音会话；"
            "任一 LLM 失败都应降级而不是阻断业务流程。",
            fontsize=8.2, color=MUTED, ha="left", va="top")
    ax.text(4, 5.8,
            "匹配指标来源：resume-match/gbdt_v3/metrics.json（合成简历，test n=100）。"
            "24 类测试集每类仅 3–5 条，单次评估 95% 区间约 ±9 个百分点。",
            fontsize=8.2, color=MUTED, ha="left", va="top")
    ax.text(4, 3.2,
            "注意：④ 的 0.78 来自真实简历（Resume.csv，2483 条），泳道三的 0.98 来自合成简历；"
            "两者数据源与任务口径不同，不能直接相减比较。",
            fontsize=8.2, color="#b45309", ha="left", va="top")

    verify(fig, ax, "模型架构")
    fig.savefig(path, dpi=200, facecolor=BG, bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)


if __name__ == "__main__":
    out = "/home/ylf/AI-recruitment/docs"
    project_architecture(f"{out}/architecture.png")
    model_architecture(f"{out}/model-architecture.png")
    print("done")
