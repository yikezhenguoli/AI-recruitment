import fs from "node:fs/promises";
import path from "node:path";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const INK = "#050807";
const PANEL = "#0D1512";
const PANEL_2 = "#111B16";
const PANEL_3 = "#17221C";
const TEXT = "#E9FFF3";
const WHITE = "#F5FAF6";
const MUTED = "#86A095";
const DIM = "#53685E";
const ACID = "#AFFF38";
const CYAN = "#51E9FF";
const ORANGE = "#FF9D3D";
const PINK = "#FF4E9B";
const BORDER = "#2B3E34";
const BORDER_SOFT = "#223028";
const SANS = "Hiragino Sans GB";
const MONO = "Menlo";
const W = 1280;
const H = 720;

const OUT_DIR = path.resolve("output");
const BUILD_DIR = path.resolve(".");
const DRAFT_PATH = path.join(BUILD_DIR, "ttc-enterprise-draft.pptx");
const PRODUCT_IMAGE = path.join(BUILD_DIR, "product-login.png");

function bg(slide, angle = 145) {
  slide.background.fill = {
    type: "gradient",
    gradientKind: "linear",
    angleDeg: angle,
    stops: [
      { offset: 0, color: "#101A16" },
      { offset: 60000, color: "#080E0B" },
      { offset: 100000, color: INK },
    ],
  };
}

function rect(slide, position, fill, line = null, name = undefined) {
  return slide.shapes.add({
    geometry: "rect",
    name,
    position,
    fill,
    line: line ?? { style: "solid", fill: "none", width: 0 },
  });
}

function addText(slide, name, text, position, style = {}) {
  const shape = slide.shapes.add({
    geometry: "textbox",
    name,
    position,
    fill: "none",
    line: { style: "solid", fill: "none", width: 0 },
  });
  shape.text = text;
  shape.text.style = {
    fontSize: style.size ?? 17,
    color: style.color ?? TEXT,
    bold: style.bold ?? false,
    typeface: style.font ?? SANS,
    alignment: style.align ?? "left",
    verticalAlignment: style.valign ?? "top",
    lineSpacing: style.lineSpacing ?? 1.08,
    insets: style.insets ?? 0,
    autoFit: "none",
    wrap: "square",
  };
  return shape;
}

function addRichText(slide, name, paragraphs, position, style = {}) {
  const shape = slide.shapes.add({
    geometry: "textbox",
    name,
    position,
    fill: "none",
    line: { style: "solid", fill: "none", width: 0 },
  });
  shape.text.set(paragraphs);
  shape.text.style = {
    fontSize: style.size ?? 18,
    color: style.color ?? TEXT,
    bold: style.bold ?? false,
    typeface: style.font ?? SANS,
    alignment: style.align ?? "left",
    verticalAlignment: style.valign ?? "top",
    lineSpacing: style.lineSpacing ?? 1.06,
    insets: style.insets ?? 0,
    autoFit: "none",
    wrap: "square",
  };
  for (const paragraph of paragraphs) {
    for (const item of paragraph) {
      if (!item || typeof item === "string" || !item.style) continue;
      const range = shape.text.get(item.run);
      if (item.style.color) range.color = item.style.color;
      if (item.style.bold !== undefined) range.bold = item.style.bold;
    }
  }
  return shape;
}

function addRule(slide, left, top, width, color = BORDER, height = 1) {
  return rect(slide, { left, top, width, height }, color);
}

function addPanel(slide, name, position, fill = PANEL, border = BORDER_SOFT, width = 1) {
  return rect(
    slide,
    position,
    fill,
    { style: "solid", fill: border, width },
    name,
  );
}

function addPill(slide, text, left, top, width, hot = false) {
  addPanel(
    slide,
    `pill-${text}`,
    { left, top, width, height: 29 },
    hot ? "#13200F" : "#0C1411",
    hot ? "#5C8D27" : BORDER_SOFT,
    1,
  );
  addText(
    slide,
    `pill-text-${text}`,
    text,
    { left: left + 11, top: top + 8, width: width - 22, height: 14 },
    { size: 10, font: MONO, color: hot ? ACID : MUTED },
  );
}

function chrome(slide, page) {
  rect(
    slide,
    { left: 14, top: 14, width: 1252, height: 692 },
    "none",
    { style: "solid", fill: BORDER_SOFT, width: 1 },
  );

  const gridColor = "#122019";
  for (let x = 80; x < 1260; x += 160) {
    rect(slide, { left: x, top: 15, width: 1, height: 690 }, gridColor);
  }
  for (let y = 80; y < 710; y += 110) {
    rect(slide, { left: 15, top: y, width: 1250, height: 1 }, gridColor);
  }

  addRule(slide, 27, 27, 30, ACID, 1);
  addRule(slide, 27, 27, 1, ACID, 30);
  addRule(slide, 1223, 693, 30, CYAN, 1);
  addRule(slide, 1252, 664, 1, CYAN, 30);

  addText(
    slide,
    "page-number",
    `${String(page).padStart(2, "0")} / 12`,
    { left: 1144, top: 31, width: 90, height: 16 },
    { size: 10, font: MONO, color: DIM, align: "right" },
  );
}

function eyebrow(slide, text, top = 57, width = 520, color = ACID) {
  addText(
    slide,
    `eyebrow-${top}`,
    `// ${text}`,
    { left: 64, top, width, height: 18 },
    { size: 11, font: MONO, color, bold: true },
  );
}

function title(slide, position, text, size = 44) {
  return addText(slide, "slide-title", text, position, {
    size,
    bold: true,
    color: WHITE,
    lineSpacing: 0.98,
  });
}

function titleRich(slide, position, paragraphs, size = 44) {
  return addRichText(slide, "slide-title", paragraphs, position, {
    size,
    bold: true,
    color: WHITE,
    lineSpacing: 0.98,
  });
}

function lead(slide, top, text, height = 58, width = 1030) {
  return addText(
    slide,
    "lead",
    text,
    { left: 64, top, width, height },
    { size: 17, color: MUTED, lineSpacing: 1.45 },
  );
}

function footer(slide, leftText, rightText = "", top = 670) {
  addRule(slide, 64, top, 1152, BORDER_SOFT, 1);
  addText(
    slide,
    "footer-left",
    leftText,
    { left: 64, top: top + 9, width: 780, height: 18 },
    { size: 10, font: MONO, color: DIM },
  );
  if (rightText) {
    addText(
      slide,
      "footer-right",
      rightText,
      { left: 842, top: top + 9, width: 374, height: 18 },
      { size: 10, font: MONO, color: DIM, align: "right" },
    );
  }
}

function card(slide, name, x, y, w, h, heading, body, index, accent = ACID, bodySize = 15) {
  addPanel(slide, name, { left: x, top: y, width: w, height: h }, PANEL, BORDER_SOFT, 1);
  addRule(slide, x, y, Math.max(72, w * 0.34), accent, 1);
  addText(
    slide,
    `${name}-index`,
    index,
    { left: x + 18, top: y + 18, width: w - 36, height: 17 },
    { size: 10, font: MONO, color: accent },
  );
  addText(
    slide,
    `${name}-heading`,
    heading,
    { left: x + 18, top: y + 55, width: w - 36, height: 54 },
    { size: 20, bold: true, color: TEXT, lineSpacing: 1.02 },
  );
  addText(
    slide,
    `${name}-body`,
    body,
    { left: x + 18, top: y + 120, width: w - 36, height: h - 136 },
    { size: bodySize, color: MUTED, lineSpacing: 1.45 },
  );
}

function terminal(
  slide,
  name,
  x,
  y,
  w,
  h,
  header,
  rows,
  fontSize = 12,
  lineSpacing = 1.52,
) {
  addPanel(slide, name, { left: x, top: y, width: w, height: h }, "#030705", "#326042", 1);
  addRule(slide, x, y, w, "#1B3525", 1);
  addText(
    slide,
    `${name}-header`,
    header,
    { left: x + 14, top: y + 9, width: w - 28, height: 15 },
    { size: 9, font: MONO, color: DIM, align: "right" },
  );
  const dots = [PINK, ORANGE, ACID];
  dots.forEach((color, i) => {
    slide.shapes.add({
      geometry: "ellipse",
      name: `${name}-dot-${i + 1}`,
      position: { left: x + 12 + i * 12, top: y + 11, width: 6, height: 6 },
      fill: color,
      line: { style: "solid", fill: "none", width: 0 },
    });
  });
  addRule(slide, x, y + 30, w, "#15301E", 1);
  return addRichText(
    slide,
    `${name}-body`,
    rows.map((runs) => runs.map((r) => (typeof r === "string" ? r : r))),
    { left: x + 16, top: y + 42, width: w - 32, height: h - 52 },
    { size: fontSize, font: MONO, color: "#B8D6C5", lineSpacing },
  );
}

function bulletPanel(slide, x, y, w, h, heading, body, accent = ACID, bodySize = 15) {
  addRule(slide, x, y + 6, 3, accent, h - 12);
  addText(
    slide,
    `bullet-${y}-${heading}`,
    heading,
    { left: x + 16, top: y, width: w - 18, height: 27 },
    { size: 17, bold: true, color: TEXT },
  );
  addText(
    slide,
    `bullet-body-${y}-${heading}`,
    body,
    { left: x + 16, top: y + 31, width: w - 18, height: h - 32 },
    { size: bodySize, color: MUTED, lineSpacing: 1.38 },
  );
}

function addArchBox(slide, text, small, x, y, w, h, accent = false) {
  addPanel(
    slide,
    `arch-${text}`,
    { left: x, top: y, width: w, height: h },
    accent ? "#17250E" : "#0B1817",
    accent ? "#4E7A27" : "#21423C",
    1,
  );
  addText(
    slide,
    `arch-title-${text}`,
    text,
    { left: x + 10, top: y + (small ? 14 : 17), width: w - 20, height: 24 },
    { size: small ? 11 : 13, font: MONO, color: accent ? ACID : "#CCE5DC", bold: true, align: "center" },
  );
  if (small) {
    addText(
      slide,
      `arch-small-${text}`,
      small,
      { left: x + 8, top: y + 42, width: w - 16, height: 16 },
      { size: 8, font: MONO, color: DIM, align: "center" },
    );
  }
}

function imageBlob(imagePath) {
  return fs.readFile(imagePath).then((bytes) =>
    bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength),
  );
}

const p = Presentation.create({ slideSize: { width: W, height: H } });

// 01 Cover
{
  const s = p.slides.add();
  bg(s, 135);
  chrome(s, 1);
  eyebrow(s, "TALENT INTELLIGENCE INFRASTRUCTURE", 88, 590);
  titleRich(
    s,
    { left: 64, top: 125, width: 580, height: 200 },
    [
      [{ run: "招聘，", style: { color: WHITE } }],
      [{ run: "进入证据时代。", style: { color: ACID } }],
    ],
    62,
  );
  addRule(s, 64, 334, 350, "#42731F", 2);
  addText(
    s,
    "cover-lead",
    "TTC 把岗位画像、简历核验、授权式 AI 语音面试、人工接管与 Offer 决策连成一条可追溯的企业招聘链路。",
    { left: 64, top: 365, width: 610, height: 76 },
    { size: 18, color: MUTED, lineSpacing: 1.52 },
  );
  addPill(s, "EVIDENCE-FIRST", 64, 464, 151, true);
  addPill(s, "HUMAN-IN-THE-LOOP", 224, 464, 181, false);
  addPill(s, "MULTI-TENANT", 414, 464, 139, false);
  addPill(s, "REALTIME VOICE", 562, 464, 151, false);

  terminal(
    s,
    "cover-terminal",
    64,
    517,
    620,
    128,
    "ttc://mission",
    [
      [
        { run: "$ ", style: { color: ACID, bold: true } },
        { run: "deploy --target enterprise-hiring", style: { color: CYAN } },
      ],
      [{ run: "# AI 负责提取证据，HR 保留最终判断权", style: { color: DIM } }],
      [
        { run: "talent-os@enterprise:~$", style: { color: ACID } },
        { run: "█", style: { color: ACID } },
      ],
    ],
  );

  const cx = 1000;
  const cy = 330;
  s.shapes.add({
    geometry: "ellipse",
    name: "orbit-outer",
    position: { left: cx - 170, top: cy - 170, width: 340, height: 340 },
    fill: "none",
    line: { style: "solid", fill: "#51E9FF55", width: 1 },
  });
  s.shapes.add({
    geometry: "ellipse",
    name: "orbit-middle",
    position: { left: cx - 125, top: cy - 125, width: 250, height: 250 },
    fill: "none",
    line: { style: "dashed", fill: "#AFFF3866", width: 1 },
  });
  s.shapes.add({
    geometry: "ellipse",
    name: "orbit-inner",
    position: { left: cx - 55, top: cy - 55, width: 110, height: 110 },
    fill: ACID,
    line: { style: "solid", fill: "#FF4E9B88", width: 2 },
  });
  addText(
    s,
    "orbit-core",
    "TTC",
    { left: cx - 45, top: cy - 16, width: 90, height: 32 },
    { size: 25, font: MONO, bold: true, color: INK, align: "center", valign: "middle" },
  );
  [
    ["JOB PROFILE", 780, 264, 103],
    ["RESUME CLAIMS", 918, 194, 136],
    ["VOICE SIGNAL", 1080, 322, 112],
    ["HUMAN REVIEW", 923, 471, 126],
  ].forEach(([label, x, y, w]) => {
    addPanel(s, `orbit-label-${label}`, { left: x, top: y, width: w, height: 26 }, "#07100B", "#294B25", 1);
    addText(
      s,
      `orbit-label-text-${label}`,
      label,
      { left: x + 8, top: y + 7, width: w - 16, height: 12 },
      { size: 9, font: MONO, color: MUTED, align: "center" },
    );
  });
  footer(s, "TTC://TALENT_OS", "EVIDENCE-FIRST SYSTEM ONLINE", 674);
  s.speakerNotes.text = "来源：demo/ttc-enterprise-pitch.html，第 1 页「封面」。";
}

// 02 Problem
{
  const s = p.slides.add();
  bg(s, 150);
  chrome(s, 2);
  eyebrow(s, "THE BROKEN PIPELINE");
  titleRich(
    s,
    { left: 64, top: 96, width: 940, height: 104 },
    [
      [{ run: "招聘不缺 AI 工具，" }],
      [{ run: "缺的是一条" }, { run: "可信决策链", style: { color: ORANGE } }, { run: "。" }],
    ],
    42,
  );
  lead(
    s,
    213,
    "JD 在表格里、简历在邮箱里、面试在会议中、结论在 HR 的脑内。信息越丰富，组织反而越难复现一个录用判断。",
    50,
    1120,
  );
  const cards = [
    ["ERR // SILO", "流程割裂", "岗位变更、简历版本、面试记录与 Offer 决策彼此脱节。"],
    ["ERR // BLACKBOX", "筛选黑箱", "一个匹配分无法说清依据，也难以定位简历中的原始证据。"],
    ["ERR // CONSENT", "语音风险", "通用 AI 面试缺少授权、撤回、旁听边界与人工接管机制。"],
    ["ERR // DRIFT", "判断漂移", "JD、规则和模型无声更新，历史评估无法解释、比较或复盘。"],
  ];
  cards.forEach(([code, h, body], i) => {
    const x = 64 + i * 282;
    card(s, `problem-${i + 1}`, x, 318, 268, 250, h, body, code, i === 1 ? CYAN : i === 2 ? PINK : ACID, 16);
    addText(
      s,
      `problem-watermark-${i + 1}`,
      String(i + 1).padStart(2, "0"),
      { left: x + 214, top: 516, width: 44, height: 42 },
      { size: 31, font: MONO, bold: true, color: "#26362D", align: "right" },
    );
  });
  footer(
    s,
    "结果是：效率提升建立在不可解释、不可治理的判断之上",
    "LATENCY ↑ / TRUST ↓",
    616,
  );
  s.speakerNotes.text = "来源：demo/ttc-enterprise-pitch.html，第 2 页「问题」。";
}

// 03 Loop
{
  const s = p.slides.add();
  bg(s, 140);
  chrome(s, 3);
  eyebrow(s, "ONE OPERATING LOOP");
  titleRich(
    s,
    { left: 64, top: 96, width: 1080, height: 104 },
    [
      [{ run: "不是单点工具，" }],
      [
        { run: "而是" },
        { run: "双端协同的招聘操作系统", style: { color: ACID } },
        { run: "。" },
      ],
    ],
    42,
  );
  const stages = [
    ["01 / DEFINE", "岗位画像", "JD 生成与抽取\n版本与权重绑定"],
    ["02 / VERIFY", "简历证据", "Claims + 原文定位\nDOI 元数据核验"],
    ["03 / CONVERSE", "语音初筛", "授权式实时对话\n追问去重与旁听接管"],
    ["04 / REVIEW", "独立评估", "匹配、能力、言行\n分账呈现"],
    ["05 / DECIDE", "面试与 Offer", "人工排期、录用\n候选人反馈闭环"],
  ];
  const nodeW = 196;
  const nodeH = 178;
  stages.forEach(([code, h, body], i) => {
    const x = 64 + i * 221;
    addPanel(s, `loop-node-${i + 1}`, { left: x, top: 240, width: nodeW, height: nodeH }, PANEL, BORDER, 1);
    addRule(s, x, 240, 74, i === 2 ? CYAN : ACID, 2);
    addText(
      s,
      `loop-code-${i + 1}`,
      code,
      { left: x + 16, top: 258, width: nodeW - 32, height: 16 },
      { size: 9, font: MONO, color: i === 2 ? CYAN : ACID },
    );
    addText(
      s,
      `loop-heading-${i + 1}`,
      h,
      { left: x + 16, top: 315, width: nodeW - 32, height: 34 },
      { size: 18, bold: true, color: TEXT },
    );
    addText(
      s,
      `loop-body-${i + 1}`,
      body,
      { left: x + 16, top: 361, width: nodeW - 32, height: 47 },
      { size: 11, font: MONO, color: MUTED, lineSpacing: 1.34 },
    );
    if (i < stages.length - 1) {
      addText(
        s,
        `loop-arrow-${i + 1}`,
        "→",
        { left: x + nodeW + 3, top: 321, width: 20, height: 24 },
        { size: 20, font: MONO, color: CYAN, align: "center" },
      );
    }
  });
  addPanel(s, "frontend-hr", { left: 64, top: 454, width: 553, height: 74 }, "#0C1713", BORDER_SOFT, 1);
  addPanel(s, "frontend-candidate", { left: 633, top: 454, width: 583, height: 74 }, "#0C1713", BORDER_SOFT, 1);
  bulletPanel(s, 82, 469, 520, 48, "企业 HR 工作台", "岗位、候选人、会话、面试、Offer、人才库", ACID, 13);
  bulletPanel(s, 651, 469, 548, 48, "候选人门户", "岗位、投递、授权、AI 面试、隐私请求", CYAN, 13);
  footer(
    s,
    "FRONTENDS 2    BUSINESS STAGES 5    TRACEABLE HANDOFFS 端到端",
    "TRACEABILITY: ON",
    630,
  );
  s.speakerNotes.text = "来源：demo/ttc-enterprise-pitch.html，第 3 页「双端闭环」。";
}

// 04 Architecture
{
  const s = p.slides.add();
  bg(s, 135);
  chrome(s, 4);
  eyebrow(s, "SYSTEM ARCHITECTURE");
  titleRich(
    s,
    { left: 64, top: 96, width: 1100, height: 92 },
    [
      [
        { run: "业务规则在核心，" },
        { run: "模型与供应商可替换", style: { color: CYAN } },
        { run: "。" },
      ],
    ],
    41,
  );
  const points = [
    ["api → domains → adapters", "路由管理鉴权与事务，领域层承载规则，外部能力经适配器接入。", ACID],
    ["异步任务基础设施", "简历解析、Crossref 检索、超时收尾和报告生成交由 Worker。", ORANGE],
    ["统一实时通道", "REST、WebSocket、实时语音经同一身份与租户边界。", CYAN],
    ["可替换技术底座", "LLM 可接 OpenAI 兼容接口，语音支持 OpenAI Realtime / 通义千问。", PINK],
  ];
  points.forEach(([h, body, accent], i) => {
    bulletPanel(s, 64, 218 + i * 96, 416, 84, h, body, accent, 13);
  });

  addPanel(s, "architecture-canvas", { left: 500, top: 197, width: 716, height: 430 }, "#08100D", BORDER, 1);
  addArchBox(s, "企业 HR 工作台", "REACT 18 · VITE · :5173", 530, 224, 321, 70, true);
  addArchBox(s, "候选人门户", "REACT 18 · VITE · :5175", 865, 224, 321, 70, true);
  addRule(s, 690, 294, 1, "#4C7D35", 18);
  addRule(s, 1025, 294, 1, "#4C7D35", 18);
  addArchBox(s, "FastAPI · /api/v1 · REST + WebSocket", "AUTH · TENANT · REQUEST ID", 530, 321, 656, 67, false);
  addRule(s, 858, 388, 1, "#4C7D35", 18);
  addArchBox(s, "API ROUTES", "业务边界", 530, 415, 149, 73, false);
  addArchBox(s, "DOMAIN RULES", "面试 · 能力 · 言行", 699, 415, 149, 73, true);
  addArchBox(s, "TASK WORKER", "解析 · 报告", 868, 415, 149, 73, false);
  addArchBox(s, "ADAPTERS", "模型 · 存储 · 语音", 1037, 415, 149, 73, false);
  addRule(s, 858, 488, 1, "#31594A", 18);
  const infra = [
    ["PostgreSQL", "16"],
    ["S3 / MinIO", "FILES"],
    ["LLM", "COMPATIBLE"],
    ["Realtime", "SDP / WS"],
    ["Resume model", "SUBPROCESS"],
  ];
  infra.forEach(([h, small], i) => {
    addArchBox(s, h, small, 530 + i * 134.5, 515, 121, 73, false);
  });
  footer(
    s,
    "ARCHITECTURE  API → DOMAINS → ADAPTERS",
    "DATA  PostgreSQL + Object Storage",
    638,
  );
  s.speakerNotes.text = "来源：demo/ttc-enterprise-pitch.html，第 4 页「技术架构」。";
}

// 05 Evidence
{
  const s = p.slides.add();
  bg(s, 145);
  chrome(s, 5);
  eyebrow(s, "INNOVATION 01 / EVIDENCE", 57, 520);
  titleRich(
    s,
    { left: 64, top: 96, width: 1060, height: 108 },
    [
      [{ run: "每一个 AI 结论，" }],
      [{ run: "都能回到" }, { run: "原文的那一行", style: { color: ACID } }, { run: "。" }],
    ],
    42,
  );
  const data = [
    ["CLAIM_001", "声明可定位", "简历中的教育、经历、项目与成果被拆为 Claim，保留原文、字符位置和版本，而不是只输出一段摘要。", "SOURCE TEXT + OFFSET + VERSION", ACID],
    ["VERIFY_002", "外部信息谨慎核验", "仅对简历中可定位的 DOI 查询 Crossref 元数据，明确区分“成果存在”与“候选人贡献”，不制造过度推断。", "METADATA ≠ AUTHORSHIP", CYAN],
    ["VERSION_003", "岗位判断可复现", "JD、权重方案与面试方案绑定岗位版本；历史评估不会被下一次规则更新悄然覆盖。", "IMMUTABLE DECISION CONTEXT", PINK],
  ];
  data.forEach(([code, h, body, tag, accent], i) => {
    const x = 64 + i * 385;
    card(s, `evidence-${i + 1}`, x, 255, 365, 286, h, body, code, accent, 16);
    addText(
      s,
      `evidence-tag-${i + 1}`,
      tag,
      { left: x + 18, top: 491, width: 329, height: 26 },
      { size: 9, font: MONO, color: accent },
    );
  });
  footer(s, "INNOVATION  从“AI 说匹配”升级为“证据支持这个判断”", "TRACEABILITY: ON", 626);
  s.speakerNotes.text = "来源：demo/ttc-enterprise-pitch.html，第 5 页「证据链」。";
}

// 06 Voice and consent
{
  const s = p.slides.add();
  bg(s, 145);
  chrome(s, 6);
  eyebrow(s, "INNOVATION 02 / VOICE");
  titleRich(
    s,
    { left: 64, top: 96, width: 1080, height: 108 },
    [
      [{ run: "AI 可以主导对话，" }],
      [
        { run: "但不能越过" },
        { run: "授权与人工控制", style: { color: CYAN } },
        { run: "。" },
      ],
    ],
    42,
  );
  const bullets = [
    ["双重授权检查", "创建会话与接通前都核验有效授权；撤回后阻止后续处理。", ACID],
    ["HR 默认静音旁听", "不能误用候选人实时通道，明确操作后才可接管麦克风。", CYAN],
    ["问题账本", "生成期与运行期双重去重，识别同义改写与变相重问。", ORANGE],
    ["可暂停、可恢复、可交还", "人工介入不推翻对话上下文，AI 继续追问。", PINK],
  ];
  bullets.forEach(([h, body, accent], i) => {
    bulletPanel(s, 64, 238 + i * 88, 484, 77, h, body, accent, 14);
  });
  terminal(
    s,
    "voice-terminal",
    606,
    221,
    610,
    330,
    "voice_session / guardrail",
    [
      [{ run: "[00:00] ", style: { color: ACID } }, { run: "consent.verify ", style: { color: CYAN } }, { run: "✓ PASS", style: { color: ACID } }],
      [{ run: "[00:01] ", style: { color: ACID } }, { run: "candidate.connect ", style: { color: CYAN } }, { run: "✓ ALLOWED", style: { color: ACID } }],
      [{ run: "[00:02] ", style: { color: ACID } }, { run: "hr.observe ", style: { color: CYAN } }, { run: "muted by default", style: { color: CYAN } }],
      [{ run: "[02:16] ", style: { color: ACID } }, { run: "question.ledger ", style: { color: CYAN } }, { run: "deduplicated", style: { color: ACID } }],
      [{ run: "[05:41] ", style: { color: ACID } }, { run: "hr.control ", style: { color: CYAN } }, { run: "take microphone", style: { color: ORANGE } }],
      [{ run: "[07:18] ", style: { color: ACID } }, { run: "hr.release ", style: { color: CYAN } }, { run: "AI resumes", style: { color: CYAN } }],
      [{ run: "[end]   ", style: { color: ACID } }, { run: "report.queue ", style: { color: CYAN } }, { run: "✓", style: { color: ACID } }],
    ],
    12,
    1.52,
  );
  footer(s, "AI AUTONOMY  bounded    CONSENT  revocable", "HUMAN CONTROL  always available", 646);
  s.speakerNotes.text = "来源：demo/ttc-enterprise-pitch.html，第 6 页「实时面试」。";
}

// 07 Assessment governance
{
  const s = p.slides.add();
  bg(s, 145);
  chrome(s, 7);
  eyebrow(s, "INNOVATION 03 / ASSESSMENT");
  titleRich(
    s,
    { left: 64, top: 94, width: 900, height: 94 },
    [
      [{ run: "拒绝“人才总分”，" }],
      [{ run: "用三本账保留判断边界。" }],
    ],
    38,
  );
  const ledgers = [
    ["JOB_MATCH", "岗位匹配", "岗位要求与当前材料的匹配程度。", CYAN],
    ["CAPABILITY", "能力证据", "本次面试中出现的岗位相关行为证据。", ACID],
    ["CONDUCT", "言行风险", "仅评价转写中可观察到的言语行为。", PINK],
  ];
  ledgers.forEach(([code, h, body, accent], i) => {
    const x = 64 + i * 385;
    addPanel(s, `ledger-${i + 1}`, { left: x, top: 211, width: 365, height: 105 }, PANEL, accent, 1);
    addText(s, `ledger-code-${i + 1}`, code, { left: x + 16, top: 226, width: 200, height: 16 }, { size: 9, font: MONO, color: DIM });
    addText(s, `ledger-head-${i + 1}`, h, { left: x + 16, top: 249, width: 220, height: 25 }, { size: 18, bold: true, color: accent });
    addText(s, `ledger-body-${i + 1}`, body, { left: x + 16, top: 279, width: 330, height: 24 }, { size: 12, color: MUTED });
  });

  terminal(
    s,
    "assessment-code",
    64,
    346,
    590,
    276,
    "assessment_contract.json    human_review_required",
    [
      [{ run: "{", style: { color: TEXT } }],
      [{ run: '  "job_match"', style: { color: CYAN } }, { run: ": {", style: { color: TEXT } }],
      [{ run: '    "score"', style: { color: CYAN } }, { run: ": ", style: { color: TEXT } }, { run: "null", style: { color: PINK } }, { run: ",", style: { color: TEXT } }],
      [{ run: '    "reason"', style: { color: CYAN } }, { run: ': ', style: { color: TEXT } }, { run: '"evidence_insufficient"', style: { color: DIM } }],
      [{ run: "  }," }],
      [{ run: '  "capability"', style: { color: CYAN } }, { run: ": {", style: { color: TEXT } }],
      [{ run: '    "dimensions"', style: { color: CYAN } }, { run: ": [...],", style: { color: TEXT } }],
      [{ run: '    "citation_required"', style: { color: CYAN } }, { run: ": ", style: { color: TEXT } }, { run: "true", style: { color: ACID } }],
      [{ run: "  }," }],
      [{ run: '  "conduct"', style: { color: CYAN } }, { run: ": {", style: { color: TEXT } }],
      [{ run: '    "veto"', style: { color: CYAN } }, { run: ": ", style: { color: TEXT } }, { run: "false", style: { color: PINK } }, { run: ",", style: { color: TEXT } }],
      [{ run: '    "raw_turn_required"', style: { color: CYAN } }, { run: ": ", style: { color: TEXT } }, { run: "true", style: { color: ACID } }],
      [{ run: "  }" }],
      [{ run: "}" }],
    ],
    10,
    1.18,
  );
  const guards = [
    ["没有证据，就不编造分数", "有效覆盖不足时保留空值并提示人工复核。", ACID],
    ["严重风险必须绑定原始轮次", "避免模型生成无法定位的“一票否决”。", ORANGE],
    ["AI 结论不是最终录用决定", "招聘人员始终拥有复核、修订与裁决权。", CYAN],
  ];
  guards.forEach(([h, body, accent], i) => {
    bulletPanel(s, 700, 362 + i * 83, 516, 72, h, body, accent, 14);
  });
  footer(s, "ASSESSMENT CONTRACT  nullable scores + citations + human review", "GOVERNANCE: ON", 648);
  s.speakerNotes.text = "来源：demo/ttc-enterprise-pitch.html，第 7 页「评估治理」。";
}

// 08 Differentiation table
{
  const s = p.slides.add();
  bg(s, 150);
  chrome(s, 8);
  eyebrow(s, "POSITIONING / WHY TTC");
  titleRich(
    s,
    { left: 64, top: 94, width: 1060, height: 78 },
    [
      [
        { run: "从“功能更强”走向" },
        { run: "系统更可信", style: { color: ACID } },
        { run: "。" },
      ],
    ],
    40,
  );
  const values = [
    ["能力维度", "传统 ATS", "单点简历工具", "通用 AI 面试", "TTC"],
    ["业务闭环", "流程记录为主", "只覆盖筛选", "只覆盖对话", "岗位 → 面试 → Offer 双端闭环"],
    ["结论依据", "字段与备注", "匹配分 / 标签", "对话摘要", "原文 Claim + 证据 + 引用"],
    ["岗位上下文", "常被覆盖", "弱", "依赖临场提示", "JD、权重、方案版本绑定"],
    ["语音治理", "通常没有", "没有", "授权机制不一", "授权、撤回、旁听、接管"],
    ["人工控制", "事后操作", "人工看结果", "难以实时介入", "暂停、恢复、接管、交还"],
    ["模型可替换", "不涉及", "供应商绑定", "供应商绑定", "Adapter 层解耦与明确降级"],
    ["判断治理", "历史难复现", "分数不可解释", "合并成单一结论", "分账评估、空值、人工复核"],
  ];
  const table = s.tables.add({
    rows: 8,
    columns: 5,
    left: 64,
    top: 204,
    width: 1152,
    height: 430,
    values,
    columnTracks: [
      { mode: "fr", value: 1.0 },
      { mode: "fr", value: 1.15 },
      { mode: "fr", value: 1.3 },
      { mode: "fr", value: 1.2 },
      { mode: "fr", value: 2.15 },
    ],
  });
  table.styleOptions = { headerRow: true, bandedRows: false, firstColumn: true };
  table.rows[0].height = 46;
  for (let r = 1; r < 8; r += 1) table.rows[r].height = 49;
  table.borders.assign({ style: "solid", fill: BORDER_SOFT, width: 1 });
  for (let r = 0; r < 8; r += 1) {
    for (let c = 0; c < 5; c += 1) {
      const cell = table.getCell(r, c);
      cell.fill = c === 4 ? "#17250E" : r === 0 ? "#0A120E" : "#0D1512";
      cell.text.style = {
        fontSize: r === 0 ? 11 : 13,
        typeface: c === 0 ? MONO : SANS,
        bold: r === 0 || c === 0 || c === 4,
        color: c === 4 ? (r === 0 ? ACID : "#DCFFC6") : c === 0 ? TEXT : MUTED,
        verticalAlignment: "middle",
        insets: { left: 10, right: 10, top: 6, bottom: 6 },
        alignment: "left",
      };
    }
  }
  footer(s, "MOAT  不是某个模型，而是可审计的业务操作系统", "TRUST AS INFRASTRUCTURE", 650);
  s.speakerNotes.text = "来源：demo/ttc-enterprise-pitch.html，第 8 页「差异化」。";
}

// 09 Data and model foundation
{
  const s = p.slides.add();
  bg(s, 145);
  chrome(s, 9);
  eyebrow(s, "DATA & MODEL FOUNDATION");
  titleRich(
    s,
    { left: 64, top: 96, width: 1060, height: 88 },
    [
      [
        { run: "模型只是组件，" },
        { run: "数据与评测", style: { color: CYAN } },
        { run: "才是底座。" },
      ],
    ],
    41,
  );
  const metrics = [
    ["100", "模拟简历"],
    ["742", "经历单元"],
    ["1,035", "面试问题"],
    ["300", "追问链"],
  ];
  metrics.forEach(([n, label], i) => {
    const x = 64 + i * 292;
    addPanel(s, `metric-${i + 1}`, { left: x, top: 220, width: 278, height: 122 }, "#101B16", BORDER, 1);
    addText(s, `metric-number-${i + 1}`, n, { left: x + 18, top: 240, width: 208, height: 48 }, { size: 42, font: MONO, bold: true, color: i === 2 ? ACID : TEXT });
    addText(s, `metric-label-${i + 1}`, label, { left: x + 18, top: 300, width: 220, height: 20 }, { size: 13, color: MUTED });
  });
  addPanel(s, "pipeline-note", { left: 64, top: 389, width: 607, height: 174 }, "#0B1714", "#1E4B45", 1);
  addRule(s, 64, 389, 4, CYAN, 174);
  addText(s, "pipeline-note-title", "可运行的数据流水线", { left: 86, top: 406, width: 560, height: 26 }, { size: 17, bold: true, color: TEXT });
  addText(
    s,
    "pipeline-note-body",
    "配置 → 生成 → 去重 → 体验提取 → 问题与追问链 → 严格校验 → 人工验收。未通过闸门，不直接进入全量阶段。",
    { left: 86, top: 445, width: 550, height: 94 },
    { size: 15, color: MUTED, lineSpacing: 1.48 },
  );
  addPanel(s, "model-note", { left: 692, top: 389, width: 524, height: 174 }, "#0D1913", BORDER_SOFT, 1);
  addRule(s, 692, 389, 4, ACID, 174);
  addText(s, "model-note-title", "简历分类模型", { left: 714, top: 406, width: 470, height: 26 }, { size: 17, bold: true, color: TEXT });
  addText(
    s,
    "model-note-body",
    "覆盖 24 类英文岗位，\n独立子进程推理。在线匹配与分类职责分开，\n避免把“岗位类别概率”包装成“候选人-JD 语义分”。",
    { left: 714, top: 445, width: 466, height: 94 },
    { size: 15, color: MUTED, lineSpacing: 1.48 },
  );
  footer(s, "PIPELINE  config → generate → validate → accept", "SYNTHETIC DATA FIRST", 614);
  s.speakerNotes.text = "来源：demo/ttc-enterprise-pitch.html，第 9 页「数据资产」。";
}

// 10 Enterprise value
{
  const s = p.slides.add();
  bg(s, 145);
  chrome(s, 10);
  eyebrow(s, "ENTERPRISE VALUE");
  titleRich(
    s,
    { left: 64, top: 96, width: 1120, height: 108 },
    [
      [{ run: "把招聘从成本中心，" }],
      [
        { run: "升级为" },
        { run: "可积累的人才资产系统", style: { color: ACID } },
        { run: "。" },
      ],
    ],
    40,
  );
  const values = [
    ["01", "更快形成有效候选人名单", "自动解析、证据定位与语音初筛连续执行，减少 HR 在工具切换、重复问询和手工整理上的时间。", 88, ACID],
    ["02", "提高面试与判断质量", "问题围绕岗位与证据缺口生成，同义问题被拦截；面试结论必须引用候选人的原始回答。", 82, CYAN],
    ["03", "降低 AI 招聘合规风险", "授权可撤回、HR 可控、原始音频默认不落盘、敏感判断不合并成一个黑箱总分。", 94, PINK],
    ["04", "沉淀可复用组织能力", "岗位版本、证据、评估与人才库持续积累，企业不再依赖某位招聘人员离开后仍能复现判断。", 79, ORANGE],
  ];
  values.forEach(([n, h, body, meter, accent], i) => {
    const x = 64 + i * 292;
    card(s, `value-${i + 1}`, x, 235, 278, 315, h, body, n, accent, 14);
    addRule(s, x + 18, 512, 242, "#26392F", 2);
    addRule(s, x + 18, 512, (242 * meter) / 100, accent, 2);
  });
  addRule(s, 64, 587, 1152, BORDER_SOFT, 1);
  addText(s, "kpi-title", "可观测 KPI", { left: 64, top: 603, width: 125, height: 18 }, { size: 10, font: MONO, color: ACID });
  addText(
    s,
    "kpi-list",
    "筛选周期     面试有效覆盖率     证据冲突率     人工复核用时     Offer 转化     候选人体验",
    { left: 210, top: 601, width: 1006, height: 22 },
    { size: 12, color: MUTED },
  );
  footer(s, "VALUE  speed + quality + governance + organizational memory", "OBSERVABLE BY DESIGN", 643);
  s.speakerNotes.text = "来源：demo/ttc-enterprise-pitch.html，第 10 页「商业价值」。";
}

// 11 Live product
{
  const s = p.slides.add();
  bg(s, 145);
  chrome(s, 11);
  eyebrow(s, "LIVE PRODUCT / EMBEDDED");
  title(s, { left: 64, top: 94, width: 880, height: 62 }, "真实工作台，直接进入。", 39);
  addText(
    s,
    "live-lead",
    "本地企业 HR 工作台；候选人门户运行在 127.0.0.1:5175。",
    { left: 64, top: 162, width: 760, height: 24 },
    { size: 15, color: MUTED },
  );
  addPill(s, "LOCALHOST", 966, 154, 101, true);
  addPill(s, "REACT / API / WS", 1078, 154, 138, false);

  addPanel(s, "browser-frame", { left: 110, top: 199, width: 1060, height: 430 }, "#07100C", "#4A762B", 1);
  addPanel(s, "browser-bar", { left: 110, top: 199, width: 1060, height: 34 }, "#080D0B", "#294B25", 1);
  [PINK, ORANGE, ACID].forEach((color, i) => {
    s.shapes.add({
      geometry: "ellipse",
      name: `browser-dot-${i + 1}`,
      position: { left: 124 + i * 12, top: 212, width: 6, height: 6 },
      fill: color,
      line: { style: "solid", fill: "none", width: 0 },
    });
  });
  const url = addText(
    s,
    "browser-url",
    "http://127.0.0.1:5173",
    { left: 166, top: 208, width: 950, height: 16 },
    { size: 10, font: MONO, color: MUTED },
  );
  url.hyperlink = { uri: "http://127.0.0.1:5173", isExternal: true };
  const bytes = await imageBlob(PRODUCT_IMAGE);
  s.images.add({
    blob: bytes,
    contentType: "image/png",
    alt: "TTC 企业招聘工作台登录页",
    fit: "cover",
    position: { left: 111, top: 233, width: 1058, height: 395 },
  });
  addText(
    s,
    "demo-foot-left",
    "启动：cd apps/web && npm run dev",
    { left: 110, top: 643, width: 500, height: 18 },
    { size: 10, font: MONO, color: ACID },
  );
  addText(
    s,
    "demo-foot-right",
    "若页面为空，请先启动前端、API 与 Worker",
    { left: 664, top: 643, width: 506, height: 18 },
    { size: 10, font: MONO, color: DIM, align: "right" },
  );
  footer(s, "LIVE PRODUCT  http://127.0.0.1:5173", "CANDIDATE PORTAL  :5175", 671);
  s.speakerNotes.text =
    "来源：demo/ttc-enterprise-pitch.html，第 11 页「真实演示」。工作台画面取自本地运行中的演示登录页；PPT 中保留可点击的本地地址。";
}

// 12 Rollout
{
  const s = p.slides.add();
  bg(s, 145);
  chrome(s, 12);
  eyebrow(s, "FROM PILOT TO PLATFORM");
  title(s, { left: 64, top: 94, width: 1080, height: 62 }, "先证明价值，再扩展到组织。", 40);
  const packages = [
    ["PHASE 01 / PROVE", "单岗位业务验证", "选择高价值岗位，跑通 JD 版本、\n简历证据、语音初筛与报告复核。\n以招聘周期、有效面试覆盖和\n人工复核时间验证 ROI。", "POC    岗位级", true],
    ["PHASE 02 / SCALE", "部门级复制", "沉淀岗位模板、权重规则与面试方案；\n接入企业存储、模型与实时语音供应商，\n保持多租户隔离。", "模块化    私有化 / 混合部署", false],
    ["PHASE 03 / GOVERN", "企业级人才 OS", "扩展人才库检索、审计、数据保留策略\n与外部 ATS 集成，让每一次招聘判断\n成为可复用资产。", "治理    系统集成", false],
  ];
  const widths = [410, 365, 365];
  let x = 64;
  packages.forEach(([phase, h, body, tags, primary], i) => {
    const w = widths[i];
    addPanel(
      s,
      `package-${i + 1}`,
      { left: x, top: 205, width: w, height: 229 },
      primary ? "#16250E" : PANEL,
      primary ? "#5A8D2B" : BORDER_SOFT,
      1,
    );
    addText(s, `package-phase-${i + 1}`, phase, { left: x + 20, top: 223, width: w - 40, height: 16 }, { size: 9, font: MONO, color: ACID });
    addText(s, `package-head-${i + 1}`, h, { left: x + 20, top: 265, width: w - 40, height: 32 }, { size: 21, bold: true, color: TEXT });
    addText(s, `package-body-${i + 1}`, body, { left: x + 20, top: 309, width: w - 40, height: 82 }, { size: 13, color: MUTED, lineSpacing: 1.40 });
    addText(s, `package-tags-${i + 1}`, tags, { left: x + 20, top: 400, width: w - 40, height: 20 }, { size: 10, font: MONO, color: primary ? ACID : MUTED });
    x += w + 17;
  });

  titleRich(
    s,
    { left: 64, top: 467, width: 690, height: 116 },
    [
      [{ run: "AI 加速。", style: { color: ACID } }],
      [{ run: "人做决定。", style: { color: WHITE } }],
    ],
    58,
  );
  addRule(s, 816, 479, 1, "#5C8D27", 95);
  addText(
    s,
    "manifesto",
    "企业真正购买的不是一个模型，而是一条更快、更准、更敢审计的招聘决策链。",
    { left: 846, top: 485, width: 368, height: 88 },
    { size: 16, color: MUTED, lineSpacing: 1.52 },
  );
  footer(s, "NEXT COMMAND  open http://127.0.0.1:5173", "END OF TRANSMISSION", 630);
  s.speakerNotes.text = "来源：demo/ttc-enterprise-pitch.html，第 12 页「落地路径」。";
}

await fs.mkdir(OUT_DIR, { recursive: true });
for (let i = 0; i < p.slides.items.length; i += 1) {
  const slide = p.slides.items[i];
  const png = await p.export({ slide, format: "png", scale: 1.25 });
  await fs.writeFile(
    path.join(BUILD_DIR, `preview-${String(i + 1).padStart(2, "0")}.png`),
    Buffer.from(await png.arrayBuffer()),
  );
}
const montage = await p.export({ format: "webp", montage: true, scale: 0.75 });
await fs.writeFile(path.join(BUILD_DIR, "deck-montage.webp"), Buffer.from(await montage.arrayBuffer()));
const draft = await PresentationFile.exportPptx(p);
await draft.save(DRAFT_PATH);
console.log(JSON.stringify({ slides: p.slides.items.length, draft: DRAFT_PATH }));
