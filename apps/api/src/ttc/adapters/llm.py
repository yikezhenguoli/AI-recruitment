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
            '返回 JSON 对象 {"claims":[{"type":"education|work|project|publication|'
            'patent|award|skill|contact|summary","raw_text":"原文连续片段",'
            '"normalized":{},"confidence":0.0}]}。'
            "禁止编造机构全称、时间、学历、个人贡献；未知字段省略。"
        )
        try:
            async with llm_client(settings.llm_timeout_seconds) as client:
                response = await client.post(
                    f"{settings.llm_base_url.rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                    json={
                        "model": settings.llm_model,
                        "temperature": 0,
                        "response_format": {"type": "json_object"},
                        "messages": [
                            {"role": "system", "content": prompt},
                            {"role": "user", "content": resume_text[:60000]},
                        ],
                    },
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

    async def explain_match(self, resume_text: str, jd_text: str, match: dict) -> dict:
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
                    json={
                        "model": settings.llm_model,
                        "temperature": 0.2,
                        "response_format": {"type": "json_object"},
                        "messages": [
                            {"role": "system", "content": prompt},
                            {"role": "user", "content": payload},
                        ],
                    },
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
            return [item.strip() for item in value if isinstance(item, str) and item.strip()][:10]

        return {
            "summary": summary.strip(),
            "strengths": texts("strengths"),
            "gaps": texts("gaps"),
            "suggestions": texts("suggestions"),
            "risk_notes": texts("risk_notes"),
        }

    async def build_interview_plan(
        self,
        resume_text: str,
        jd_text: str,
        scenario: str = "screen",
        job_context: dict | None = None,
    ) -> dict:
        """生成 3～5 个初始问题；后续追问由实时语音模型根据回答动态产生。"""
        settings = get_settings()
        if not all((settings.llm_base_url, settings.llm_api_key, settings.llm_model)):
            raise TTCError("TTC-5004", "尚未配置面试问题生成模型", 503)
        prompt = (
            "你是实时 AI 面试的开场问题设计助手。只依据给出的【简历】【岗位描述】"
            "和【岗位结构化快照】，设计 3～5 道初始问题。"
            "这些初始问题只确定本轮对话的主题和切入点，不需要预生成追问；"
            "实时面试官会根据候选人的实际回答继续追问或切换话题。"
            "硬性规则：1) 每个初始问题都必须锚定简历里的具体事实（项目、技术、职责、"
            "公司或成果），并说明它对应的岗位要求，不得编造简历经历；"
            "2) 初始问题之间不得相同或语义相同，禁止只替换近义词、调整语序或"
            "缩小/扩大范围来制造新问题；同一事实只能从互不重叠的考察意图切入；"
            "3) 不问性别、年龄、婚育、民族、宗教、残障、身份证与住址等敏感信息；"
            "4) 问题是给语音面试官口头念的，一句话，不超过 60 个字，不要 Markdown；"
            "5) 初始问题应覆盖：最相关经历的具体贡献与实现、岗位核心技能或职责、"
            "一个需要核实的差距或风险、求职动机，可按岗位相关性合并；"
            "6) 只输出 JSON 对象，字段为 profile(不超过 120 字的候选人画像，"
            "只写简历里明确出现的技术栈、年限、代表经历)、"
            "questions(恰好 3～5 个，元素为 {section, text, focus, job_relevance, "
            "resume_anchor}，section 取 experience|skill|gap|motivation；"
            "focus 是本题想核实的能力，不超过 30 字；job_relevance 说明对应的岗位要求，"
            "resume_anchor 指明问题依据的简历事实，各不超过 60 字)。"
        )
        context_text = json.dumps(job_context or {}, ensure_ascii=False)
        payload = (
            f"【面试类型】{scenario}\n\n"
            f"【岗位结构化快照】\n{context_text[:12000]}\n\n"
            f"【岗位原始描述】\n{jd_text[:20000]}\n\n"
            f"【简历】\n{resume_text[:40000]}"
        )
        try:
            async with llm_client(settings.llm_timeout_seconds) as client:
                response = await client.post(
                    f"{settings.llm_base_url.rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                    json={
                        "model": settings.llm_model,
                        "temperature": 0.2,
                        "response_format": {"type": "json_object"},
                        "messages": [
                            {"role": "system", "content": prompt},
                            {"role": "user", "content": payload},
                        ],
                    },
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

    async def summarize_interview(
        self, plan: dict, turns: list[dict], job_title: str | None = None
    ) -> dict:
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
        questions = [
            item.get("text", "")
            for item in plan.get("questions", [])
            if isinstance(item, dict) and item.get("text")
        ]
        lines = []
        for turn in turns:
            role = turn.get("role")
            speaker = (
                "AI 面试官"
                if role == "interviewer"
                else (
                    "候选人"
                    if role == "candidate"
                    else ("HR" if role == "hr" else "系统")
                )
            )
            lines.append(f"{speaker}：{turn.get('text', '')}")
        title = job_title.strip() if isinstance(job_title, str) else ""
        payload = (
            (f"应聘岗位：{title}\n\n" if title else "")
            + "【问题清单】\n"
            + "\n".join(f"- {text}" for text in questions)
            + "\n\n【通话转写】\n"
            + "\n".join(lines)
        )
        try:
            async with llm_client(settings.llm_timeout_seconds) as client:
                response = await client.post(
                    f"{settings.llm_base_url.rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                    json={
                        "model": settings.llm_model,
                        "temperature": 0.2,
                        "response_format": {"type": "json_object"},
                        "messages": [
                            {"role": "system", "content": prompt},
                            {"role": "user", "content": payload[:60000]},
                        ],
                    },
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
            return [item.strip() for item in value if isinstance(item, str) and item.strip()][
                :limit
            ]

        qa = []
        for item in data.get("qa", []) if isinstance(data.get("qa"), list) else []:
            if not isinstance(item, dict):
                continue
            question = item.get("question")
            answer = item.get("answer_summary")
            if isinstance(question, str) and isinstance(answer, str):
                qa.append({"question": question.strip(), "answer_summary": answer.strip()})
        return {
            "overview": overview.strip(),
            "qa": qa[:20],
            "followups": texts("followups"),
            "limitations": texts("limitations"),
        }

    async def assess_interview_capability(
        self,
        plan: dict,
        turns: list[dict],
        job_title: str | None = None,
    ) -> dict:
        """依据回答内容评估岗位相关能力证据，不做通用能力或人格测评。"""
        settings = get_settings()
        if not all((settings.llm_base_url, settings.llm_api_key, settings.llm_model)):
            raise TTCError("TTC-5004", "尚未配置面试能力评估模型", 503)
        prompt = (
            "你是面试回答能力评估助手。只依据【岗位信息】【初始问题】和【通话转写】"
            "评价候选人在本次回答中展示出的岗位相关能力证据。不得根据外貌、声线、"
            "口音、性别、年龄、婚育、民族、宗教、残障、人格、情绪或表达是否流利推断能力。\n"
            "评分维度及权重必须为：job_knowledge(岗位知识与技能,20)、"
            "relevant_experience(相关经历深度,25)、problem_solving(分析与问题解决,20)、"
            "ownership_impact(个人贡献与结果,20)、learning_adaptability(学习与迁移,15)。"
            "每项 0-100。只评价回答中明确出现的内容：候选人没有回答、回答含糊或只重复"
            "面试官问题时，对应维度 score 必须为 null；不得因为候选人声称会某技能就直接"
            "认定其已掌握，必须结合具体职责、做法、决策、结果或异常处理等证据。"
            "技术或业务正确性只有在岗位信息或通用专业知识足以判断时才评价；无法确认时"
            "降低评分置信度并写入 verification_questions，不得把不确定内容写成事实。\n"
            "硬性证据规则：每个有分数的维度必须给出 evidence_turn_ids，且只能引用输入中"
            "候选人发言的轮次 ID；不得引用面试官或系统轮次，不得编造轮次、引语或候选人"
            "没有说过的经历、指标和成果。候选人对同一问题的多轮回答可以共同作为证据。\n"
            "只输出 JSON 对象，字段为：summary(本次能力证据的一句话结论)、"
            "dimensions(数组，元素为 {key,score,reason,evidence_turn_ids})、"
            "strengths(字符串数组)、gaps(字符串数组)、"
            "verification_questions(建议下一轮核验的问题，字符串数组)、"
            "review_required(布尔)、limitations(字符串数组)。"
            "所有文本使用简洁中文，不要 Markdown。"
        )
        questions = [
            item.get("text", "")
            for item in plan.get("questions", [])
            if isinstance(item, dict) and item.get("text")
        ]
        job_context = plan.get("job_context")
        context = json.dumps(
            job_context if isinstance(job_context, dict) else {},
            ensure_ascii=False,
        )
        lines = []
        for turn in turns:
            role = turn.get("role")
            speaker = (
                "AI 面试官"
                if role == "interviewer"
                else (
                    "候选人"
                    if role == "candidate"
                    else ("HR" if role == "hr" else "系统")
                )
            )
            lines.append(
                f"[turn:{turn.get('id', '')}] {speaker}：{turn.get('text', '')}"
            )
        title = job_title.strip() if isinstance(job_title, str) else ""
        payload = (
            (f"应聘岗位：{title}\n\n" if title else "")
            + f"【岗位信息】\n{context[:16000]}\n\n"
            + "【初始问题】\n"
            + "\n".join(f"- {text}" for text in questions)
            + "\n\n【通话转写】\n"
            + "\n".join(lines)
        )
        try:
            async with llm_client(settings.llm_timeout_seconds) as client:
                response = await client.post(
                    f"{settings.llm_base_url.rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                    json={
                        "model": settings.llm_model,
                        "temperature": 0,
                        "response_format": {"type": "json_object"},
                        "messages": [
                            {"role": "system", "content": prompt},
                            {"role": "user", "content": payload[:60000]},
                        ],
                    },
                )
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise TTCError("TTC-5001", "面试能力评估模型超时", 504) from exc
        except httpx.HTTPError as exc:
            raise TTCError("TTC-5004", "面试能力评估模型不可用", 503) from exc
        try:
            data = json.loads(response.json()["choices"][0]["message"]["content"])
            if not isinstance(data, dict):
                raise ValueError("capability assessment is not an object")
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            raise TTCError("TTC-5002", "能力评估模型输出不符合契约", 502) from exc
        return data

    async def assess_interview_conduct(self, turns: list[dict]) -> dict:
        """审核面试转写中的言行，并要求严重事件绑定原始轮次 ID。"""
        settings = get_settings()
        if not all((settings.llm_base_url, settings.llm_api_key, settings.llm_model)):
            raise TTCError("TTC-5004", "尚未配置面试言行审核模型", 503)
        prompt = (
            "你是面试言行审核助手。仅依据给出的候选人原始转写，审核其在本次面试中的"
            "尊重、秩序、作答态度和职业化表达。只评价可观察到的言语行为，不评价外貌、"
            "声线、口音、情绪稳定性、人格、能力，也不推断性别、年龄、婚育、民族、宗教、"
            "残障等敏感属性。\n"
            "评分维度及权重必须为：respect(尊重与边界,30)、order(秩序与配合,30)、"
            "integrity(诚信与作答态度,25)、professionalism(职业化表达,15)。每项 0-100 分。\n"
            "以下严重事件必须在 incidents 中如实记录，severity 设为 severe，并使 veto=true："
            "1) disruption：故意扰乱面试秩序；"
            "2) intentional_non_answer：经澄清后仍故意胡言乱语、答非所问或持续用无意义内容"
            "阻挠面试；"
            "3) hostility：顶撞、辱骂、威胁面试官或进行人身攻击；"
            "4) inappropriate_speech：发表歧视、侮辱、性骚扰、暴力威胁、违法煽动等不当言论。"
            "普通分歧、合理质疑、请求澄清、紧张、沉默、简短回答或一次说“不知道”，"
            "不得认定为严重事件或故意不配合。候选人引用不当说法进行谴责、澄清或反驳时，"
            "不得把引用本身当作其发表不当言论。\n"
            "硬性证据规则：每个 incident 的 evidence_turn_ids 必须只使用输入中 candidates "
            "发言的轮次 ID；不得使用面试官轮次，不得编造引语、轮次或事件。"
            "无法定位到原始候选人轮次的严重事件不要输出。"
            "若无严重事件，veto 必须为 false。存在 moderate 事件时应 review_required=true。"
            "只输出 JSON 对象，字段为："
            "summary(一句话审核结论), score(0-100 的建议总分), "
            "dimensions(数组，元素为 {key,score,reason,evidence_turn_ids}), "
            "incidents(数组，元素为 {category,severity:minor|moderate|severe,"
            "description,evidence_turn_ids}), veto(布尔), veto_reasons(字符串数组), "
            "review_required(布尔), limitations(字符串数组)。"
            "所有文本使用简洁中文，不要 Markdown。"
        )
        lines = []
        for turn in turns:
            role = turn.get("role")
            speaker = (
                "AI 面试官"
                if role == "interviewer"
                else (
                    "候选人"
                    if role == "candidate"
                    else ("HR" if role == "hr" else "系统")
                )
            )
            turn_id = str(turn.get("id") or "")
            lines.append(f"[turn:{turn_id}] {speaker}：{turn.get('text', '')}")
        payload = "\n".join(lines)
        try:
            async with llm_client(settings.llm_timeout_seconds) as client:
                response = await client.post(
                    f"{settings.llm_base_url.rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                    json={
                        "model": settings.llm_model,
                        "temperature": 0,
                        "response_format": {"type": "json_object"},
                        "messages": [
                            {"role": "system", "content": prompt},
                            {"role": "user", "content": payload[:60000]},
                        ],
                    },
                )
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise TTCError("TTC-5001", "面试言行审核模型超时", 504) from exc
        except httpx.HTTPError as exc:
            raise TTCError("TTC-5004", "面试言行审核模型不可用", 503) from exc
        try:
            data = json.loads(response.json()["choices"][0]["message"]["content"])
            if not isinstance(data, dict):
                raise ValueError("conduct assessment is not an object")
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            raise TTCError("TTC-5002", "言行审核模型输出不符合契约", 502) from exc
        return data
