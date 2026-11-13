from typing import Protocol


class LLMPort(Protocol):
    async def extract_claims(self, resume_text: str) -> list[dict]: ...


class StoragePort(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> str: ...

    async def delete(self, uri: str) -> None: ...
