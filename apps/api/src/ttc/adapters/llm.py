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
