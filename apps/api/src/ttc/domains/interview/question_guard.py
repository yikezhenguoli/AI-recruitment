"""Deterministic guard against repeated and paraphrased interview questions."""

from __future__ import annotations

import re
from collections.abc import Iterable

_SPACE_RE = re.compile(r"\s+")
_PUNCTUATION_RE = re.compile(r"[^\w\u3400-\u9fff]+", re.UNICODE)
_LATIN_RE = re.compile(r"[a-z0-9][a-z0-9+#._-]*", re.IGNORECASE)
_CJK_SEQUENCE_RE = re.compile(r"[\u3400-\u9fff]+")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？!?；;\n])")

_GENERIC_PHRASES = tuple(
    sorted(
        {
            "请你",
            "请您",
            "请具体",
            "请详细",
            "请简单",
            "具体说明",
            "详细说明",
            "请说明",
            "请介绍",
            "介绍一下",
            "说说",
            "讲一讲",
            "谈一谈",
            "描述一下",
            "能否",
            "可以",
            "以及",
            "然后",
            "那么",
            "一下",
            "具体",
            "详细",
            "当时",
            "目前",
            "简单",
            "主要",
            "相关",
        },
        key=len,
        reverse=True,
    )
)
_TRAILING_GENERIC_RE = re.compile(r"[你您的了吗呢吧啊呀]*[？?！!。；;]*$")

# Order matters: the first matching intent is the question's primary intent.
_INTENTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "motivation",
        ("为什么选择这个岗位", "选择我们", "选择这个岗位", "求职意愿", "到岗", "加入我们"),
    ),
    (
        "collaboration",
        ("协作", "团队", "沟通", "跨部门", "冲突处理", "如何配合"),
    ),
    (
        "learning",
        ("学到", "收获", "成长", "复盘", "反思", "总结"),
    ),
    (
        "outcome",
        ("结果", "效果", "指标", "数据", "成果", "提升", "验证", "衡量"),
    ),
    (
        "contribution",
        ("个人贡献", "贡献", "负责", "职责", "角色", "参与", "主导", "承担", "做了"),
    ),
    (
        "difficulty",
        ("困难", "挑战", "失败", "冲突", "风险", "边界"),
    ),
    (
        "troubleshooting",
        (
            "定位",
            "排查",
            "故障",
            "异常",
            "失效",
            "不一致",
            "线上问题",
            "性能问题",
        ),
    ),
    (
        "method",
        (
            "如何",
            "怎么",
            "怎样",
            "实现",
            "设计",
            "流程",
            "步骤",
            "方案",
            "思路",
            "处理",
            "定位",
            "排查",
            "保证",
            "避免",
        ),
    ),
    (
        "rationale",
        ("为什么", "为何", "原因", "依据", "考虑", "取舍", "比较"),
    ),
    (
        "introduction",
        ("介绍", "概述", "谈谈", "说说", "经历"),
    ),
)

_TOPIC_REMOVE_PHRASES = tuple(
    sorted(
        {
            *(
                marker
                for _, markers in _INTENTS
                for marker in markers
            ),
            "什么",
            "哪些",
            "哪一",
            "哪一个",
            "哪部分",
            "哪一块",
            "是否",
            "有没有",
            "能不能",
            "会不会",
            "请问",
            "请",
            "你",
            "您",
            "的",
            "了",
            "吗",
            "呢",
            "吧",
            "这个",
            "那个",
            "这段",
            "这段经历",
            "是",
            "一次",
            "一种",
            "遇到",
            "面临",
            "最大",
            "最小",
            "核心",
            "从",
            "里",
            "中",
            "方面",
            "情况",
        },
        key=len,
        reverse=True,
    )
)

_TOPIC_ALIASES = tuple(
    sorted(
        {
            "上一家公司": "离职",
            "上一份工作": "离职",
            "离开公司": "离职",
            "离开上一份工作": "离职",
            "离职原因": "离职",
            "负责范围": "职责",
            "职责范围": "职责",
            "工作职责": "职责",
            "岗位职责": "职责",
            "工作内容": "职责",
            "模块": "职责",
            "项目经历": "项目",
            "最大的收获": "成长",
            "学到什么": "成长",
            "学到了什么": "成长",
            "学到": "成长",
            "收获": "成长",
        }.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    )
)


def normalize_question(text: str) -> str:
    """Normalize whitespace, punctuation and polite wording for exact matching."""
    value = _SPACE_RE.sub("", str(text or "")).casefold()
    value = _PUNCTUATION_RE.sub("", value)
    for phrase in _GENERIC_PHRASES:
        value = value.replace(phrase, "")
    return _TRAILING_GENERIC_RE.sub("", value)


def _intent(text: str) -> str:
    normalized = _SPACE_RE.sub("", str(text or "")).casefold()
    for name, markers in _INTENTS:
        if any(marker in normalized for marker in markers):
            return name
    return "general"


def _topic_features(text: str) -> tuple[str, set[str]]:
    topic = normalize_question(text)
    for source, target in _TOPIC_ALIASES:
        topic = topic.replace(source, target)
    for phrase in _TOPIC_REMOVE_PHRASES:
        topic = topic.replace(phrase, "")
    topic = _TRAILING_GENERIC_RE.sub("", topic)

    features = set(_LATIN_RE.findall(topic))
    for sequence in _CJK_SEQUENCE_RE.findall(topic):
        if len(sequence) == 1:
            features.add(sequence)
            continue
        features.update(sequence[index : index + 2] for index in range(len(sequence) - 1))
    return topic, features


def semantic_similarity(left: str, right: str) -> float:
    """Heuristic similarity focused on the question topic and intent.

    This is deliberately conservative: sharing a topic alone is not enough.
    Two questions must also have the same primary intent, unless their wording
    is almost identical after normalization.
    """
    left_normalized = normalize_question(left)
    right_normalized = normalize_question(right)
    if not left_normalized or not right_normalized:
        return 0.0
    if left_normalized == right_normalized:
        return 1.0

    left_chars = {
        left_normalized[index : index + 2]
        for index in range(max(1, len(left_normalized) - 1))
    }
    right_chars = {
        right_normalized[index : index + 2]
        for index in range(max(1, len(right_normalized) - 1))
    }
    lexical = (
        2 * len(left_chars & right_chars) / max(1, len(left_chars) + len(right_chars))
    )

    left_topic_text, left_topic = _topic_features(left)
    right_topic_text, right_topic = _topic_features(right)
    topic_overlap = (
        len(left_topic & right_topic) / max(1, min(len(left_topic), len(right_topic)))
        if left_topic and right_topic
        else 0.0
    )
    same_intent = _intent(left) == _intent(right) != "general"
    if same_intent:
        if topic_overlap >= 0.5 or (not left_topic and not right_topic):
            return max(0.82, lexical)
        if left_topic_text == right_topic_text and left_topic:
            return max(0.86, lexical)
        return lexical
    # Similar wording with different intents usually asks about a different
    # aspect of the same experience, so it must not be collapsed by default.
    return lexical * 0.5


def questions_equivalent(left: str, right: str) -> bool:
    return semantic_similarity(left, right) >= 0.78


def _looks_like_question(sentence: str) -> bool:
    value = _SPACE_RE.sub("", sentence)
    if not value:
        return False
    if any(mark in value for mark in "?？"):
        return True
    if any(
        marker in value
        for marker in (
            "什么",
            "哪些",
            "哪一",
            "哪块",
            "如何",
            "怎么",
            "怎样",
            "为什么",
            "为何",
            "是否",
            "有没有",
            "请说明",
            "请介绍",
            "谈谈",
            "说说",
        )
    ):
        return True
    return False


def extract_questions(text: str) -> list[str]:
    """Extract interviewer questions from a possibly multi-sentence response."""
    value = str(text or "").strip()
    if not value:
        return []
    sentences = [item.strip() for item in _SENTENCE_SPLIT_RE.split(value) if item.strip()]
    questions = [sentence for sentence in sentences if _looks_like_question(sentence)]
    if questions:
        return questions
    return [value] if _looks_like_question(value) else []


def deduplicate_questions(items: Iterable[dict]) -> list[dict]:
    """Keep the first item when question texts are equal or semantically equal."""
    unique: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        if any(questions_equivalent(text, existing["text"]) for existing in unique):
            continue
        unique.append({**item, "text": text.strip()})
    return unique


class QuestionLedger:
    """Track questions actually spoken during one live interview."""

    def __init__(self, limit: int = 20):
        self.limit = limit
        self.questions: list[str] = []

    def add(self, text: str) -> bool:
        added = False
        for question in extract_questions(text):
            cleaned = question.strip()[:240]
            if not cleaned:
                continue
            if any(questions_equivalent(cleaned, asked) for asked in self.questions):
                continue
            self.questions.append(cleaned)
            added = True
            if len(self.questions) >= self.limit:
                del self.questions[: len(self.questions) - self.limit]
        return added

    def render(self) -> str:
        lines = [
            "【问题去重硬约束】",
            "每轮只能提出一个问题。不得重复已经问过的问题，也不得换同义词、"
            "改写句式、缩小或扩大范围后再次提出同一问题；“再说明一下”“具体展开”"
            "也算重复。每次生成下一问前，必须先对照下方已问清单检查主题和考察意图。",
        ]
        if self.questions:
            lines.append("已经实际问过的问题（均禁止再次提出或语义改写）：")
            lines.extend(
                f"{index}. {question}" for index, question in enumerate(self.questions, 1)
            )
        else:
            lines.append("目前尚未实际提问。")
        lines.append(
            "如果当前主题已回答充分，必须进入尚未覆盖的岗位主题或收尾；"
            "如果回答不足，只能询问该回答中尚未出现的新细节，不得重问原题。"
            "唯一例外是候选人明确说“没听清/请再说一遍”时，可原样复述刚才那道题一次。"
        )
        return "\n".join(lines)


def response_instructions(base: str, ledger: QuestionLedger, extra: str = "") -> str:
    parts = [base.strip(), ledger.render()]
    if extra.strip():
        parts.append(extra.strip())
    return "\n\n".join(part for part in parts if part)
