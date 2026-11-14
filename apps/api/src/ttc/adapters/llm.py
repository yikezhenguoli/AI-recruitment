import json

import httpx

from ttc.core.config import get_settings
from ttc.core.errors import TTCError


def llm_client(timeout: float) -> httpx.AsyncClient:
    """构造 LLM 直连客户端。

    trust_env=False：部署环境可能设有 ALL_PROXY=socks://...（httpx 只接受
    socks5://），读取环境代理会在 AsyncClient 构造阶段抛 ValueError，
    该异常不属于 httpx.HTTPError，未捕获就会让 LLM 接口返回 500。
    """
    return httpx.AsyncClient(timeout=timeout, trust_env=False)


class LLMAdapter:
    async def extract_claims(self, resume_text: str) -> list[dict]:
        settings = get_settings()
        if not all((settings.llm_base_url, settings.llm_api_key, settings.llm_model)):
            raise TTCError("TTC-5004", "尚未配置简历解析模型", 503)
        prompt = (
            "只抽取原文可逐字定位的教育、工作、项目、论文、专利、奖项、技能陈述。"
            "返回 JSON 对象 {\"claims\":[{\"type\":\"education|work|project|publication|"
            "patent|award|skill|contact|summary\",\"raw_text\":\"原文连续片段\","
            "\"normalized\":{},\"confidence\":0.0}]}。"
            "禁止编造机构全称、时间、学历、个人贡献；未知字段省略。"
        )
        try:
            async with llm_client(settings.llm_timeout_seconds) as client:
                response = await client.post(
                    f"{settings.llm_base_url.rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                    json={"model": settings.llm_model, "temperature": 0,
                          "response_format": {"type": "json_object"},
                          "messages": [{"role": "system", "content": prompt},
                                       {"role": "user", "content": resume_text[:60000]}]},
                )
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise TTCError("TTC-5001", "简历解析模型超时", 504) from exc
        except httpx.HTTPError as exc:
            raise TTCError("TTC-5004", "简历解析模型不可用", 503) from exc
        try:
            data = json.loads(response.json()["choices"][0]["message"]["content"])
            if not isinstance(data["claims"], list):
                raise ValueError("claims is not a list")
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            raise TTCError("TTC-5002", "模型输出不符合解析契约", 502) from exc
        return data["claims"]

    async def explain_match(self, resume_text: str, jd_text: str,
                            match: dict) -> dict:
        """基于简历与 JD 生成匹配解释；只允许引用给定文本。"""
        settings = get_settings()
        if not all((settings.llm_base_url, settings.llm_api_key, settings.llm_model)):
            raise TTCError("TTC-5004", "尚未配置匹配解释模型", 503)
        prompt = (
            "你是招聘辅助助手，只依据下面提供的【简历】与【岗位描述】写匹配解释。"
            "硬性规则：1) 不得编造或推断简历中不存在的经历、学历、时间、公司名、证书、"
            "技能熟练度；2) 无法从简历确认的内容一律写“简历未体现”；"
            "3) 不得判断性别、年龄、婚育、民族、宗教、残障等敏感属性；"
            "4) 结论只是辅助，不替代人工复核。"
            "只输出 JSON 对象，字段为：summary(一句话结论，字符串)、"
            "strengths(优势，字符串数组)、gaps(差距，字符串数组)、"
            "suggestions(面试或补充材料建议，字符串数组)、"
            "risk_notes(风险与需核实项，字符串数组)。"
            "数组元素必须是简短中文句子，不要 Markdown。"
        )
        payload = (
            f"【岗位类别（小模型判断）】{match.get('category')}"
            f"（置信度 {match.get('confidence')}）\n"
            f"【岗位描述】\n{jd_text[:20000]}\n\n"
            f"【简历】\n{resume_text[:40000]}"
        )
        try:
            async with llm_client(settings.llm_timeout_seconds) as client:
                response = await client.post(
                    f"{settings.llm_base_url.rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                    json={"model": settings.llm_model, "temperature": 0.2,
                          "response_format": {"type": "json_object"},
                          "messages": [{"role": "system", "content": prompt},
                                       {"role": "user", "content": payload}]},
                )
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise TTCError("TTC-5001", "匹配解释模型超时", 504) from exc
        except httpx.HTTPError as exc:
            raise TTCError("TTC-5004", "匹配解释模型不可用", 503) from exc
        try:
            data = json.loads(response.json()["choices"][0]["message"]["content"])
            if not isinstance(data, dict):
                raise ValueError("explanation is not an object")
            summary = data.get("summary")
            if not isinstance(summary, str) or not summary.strip():
                raise ValueError("summary is missing")
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            raise TTCError("TTC-5002", "解释模型输出不符合契约", 502) from exc

        def texts(key: str) -> list[str]:
            value = data.get(key)
            if not isinstance(value, list):
                return []
            return [item.strip() for item in value
                    if isinstance(item, str) and item.strip()][:10]

        return {"summary": summary.strip(), "strengths": texts("strengths"),
                "gaps": texts("gaps"), "suggestions": texts("suggestions"),
                "risk_notes": texts("risk_notes")}

    async def build_interview_plan(self, resume_text: str, jd_text: str,
                                   scenario: str = "screen") -> dict:
        """按简历与岗位生成面试问题；只允许锚定简历里出现过的事实。"""
        settings = get_settings()
        if not all((settings.llm_base_url, settings.llm_api_key, settings.llm_model)):
            raise TTCError("TTC-5004", "尚未配置面试问题生成模型", 503)
        prompt = (
            "你是面试提纲设计助手，只依据给出的【简历】与【岗位描述】出初筛问题。"
            "硬性规则：1) 每个问题都必须锚定简历里的具体事实（点名项目、技术、职责、"
            "公司或成果），不得询问简历中完全没有出现过的主题，不得编造经历；"
            "2) 不问性别、年龄、婚育、民族、宗教、残障、身份证与住址等敏感信息；"
            "3) 题目是给语音面试官口头念的，一句话，不超过 40 个字，不要 Markdown；"
            "4) 出 3 到 5 题，顺序为：先深挖简历里最相关的一段经历（具体做了什么、"
            "怎么做的、结果如何），再核实一项与该岗位要求直接相关的技术或职责，"
            "最后一题问动机或与岗位要求的差距（可以问期望薪资范围）。"
            "5) 只输出 JSON 对象，字段为 profile(不超过 80 字的候选人画像，"
            "只写简历里明确出现的技术栈、年限、代表经历)、"
            "questions(数组，元素为 {id, section, text, focus}，"
            "section 取 experience|skill|gap|motivation，focus 是这题想核实什么，"
            "不超过 20 字)。"
        )
        payload = (f"【面试类型】{scenario}\n\n"
                   f"【岗位描述】\n{jd_text[:20000]}\n\n"
                   f"【简历】\n{resume_text[:40000]}")
        try:
            async with llm_client(settings.llm_timeout_seconds) as client:
                response = await client.post(
                    f"{settings.llm_base_url.rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                    json={"model": settings.llm_model, "temperature": 0.2,
                          "response_format": {"type": "json_object"},
                          "messages": [{"role": "system", "content": prompt},
                                       {"role": "user", "content": payload}]},
                )
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise TTCError("TTC-5001", "面试问题生成模型超时", 504) from exc
        except httpx.HTTPError as exc:
            raise TTCError("TTC-5004", "面试问题生成模型不可用", 503) from exc
        try:
            data = json.loads(response.json()["choices"][0]["message"]["content"])
            if not isinstance(data, dict) or not isinstance(data.get("questions"), list):
                raise ValueError("questions is not a list")
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            raise TTCError("TTC-5002", "问题生成模型输出不符合契约", 502) from exc
        return data

    async def summarize_interview(self, plan: dict, turns: list[dict],
                                  job_title: str | None = None) -> dict:
        """把一场面试的转写整理成纪要；只允许复述转写里出现的内容。"""
        settings = get_settings()
        if not all((settings.llm_base_url, settings.llm_api_key, settings.llm_model)):
            raise TTCError("TTC-5004", "尚未配置面试纪要模型", 503)
        prompt = (
            "你是面试记录整理助手，只依据给出的【问题清单】和【通话转写】写纪要。"
            "硬性规则：1) 不得编造转写中没有的经历、数字、公司、结论；"
            "2) 候选人没有回答或回答含糊的，在对应条目里写“未回答”或“回答不完整”；"
            "3) 不评价外貌、口音、性别、年龄、婚育等敏感属性，不做录用判断；"
            "4) 只输出 JSON 对象，字段为 overview(三两句话的整体纪要，字符串)、"
            "qa(数组，元素为 {question, answer_summary})、"
            "followups(建议下一轮进一步确认的问题，字符串数组)、"
            "limitations(本次纪要的局限，字符串数组)。"
            "所有文本用简洁中文，不要 Markdown。"
        )
        questions = [item.get("text", "") for item in plan.get("questions", [])
                     if isinstance(item, dict) and item.get("text")]
        lines = []
        for turn in turns:
            role = turn.get("role")
            speaker = "AI 面试官" if role == "interviewer" else (
                "候选人" if role == "candidate" else "系统")
            lines.append(f"{speaker}：{turn.get('text', '')}")
        title = job_title.strip() if isinstance(job_title, str) else ""
        payload = (
            (f"应聘岗位：{title}\n\n" if title else "") +
            "【问题清单】\n" + "\n".join(f"- {text}" for text in questions) +
            "\n\n【通话转写】\n" + "\n".join(lines)
        )
        try:
            async with llm_client(settings.llm_timeout_seconds) as client:
                response = await client.post(
                    f"{settings.llm_base_url.rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                    json={"model": settings.llm_model, "temperature": 0.2,
                          "response_format": {"type": "json_object"},
                          "messages": [{"role": "system", "content": prompt},
                                       {"role": "user", "content": payload[:60000]}]},
                )
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise TTCError("TTC-5001", "面试纪要模型超时", 504) from exc
        except httpx.HTTPError as exc:
            raise TTCError("TTC-5004", "面试纪要模型不可用", 503) from exc
        try:
            data = json.loads(response.json()["choices"][0]["message"]["content"])
            overview = data.get("overview")
            if not isinstance(overview, str) or not overview.strip():
                raise ValueError("overview is missing")
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            raise TTCError("TTC-5002", "纪要模型输出不符合契约", 502) from exc

        def texts(key: str, limit: int = 10) -> list[str]:
            value = data.get(key)
            if not isinstance(value, list):
                return []
            return [item.strip() for item in value
                    if isinstance(item, str) and item.strip()][:limit]

        qa = []
        for item in data.get("qa", []) if isinstance(data.get("qa"), list) else []:
            if not isinstance(item, dict):
                continue
            question = item.get("question")
            answer = item.get("answer_summary")
            if isinstance(question, str) and isinstance(answer, str):
                qa.append({"question": question.strip(), "answer_summary": answer.strip()})
        return {"overview": overview.strip(), "qa": qa[:20],
                "followups": texts("followups"), "limitations": texts("limitations")}
