import json

import httpx

from ttc.core.config import get_settings
from ttc.core.errors import TTCError


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
            async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
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
