import asyncio
import os
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from ttc.core.config import get_settings


class Storage:
    def __init__(self) -> None:
        settings = get_settings()
        self.bucket = settings.s3_bucket_resumes
        self.client = None
        if settings.s3_endpoint and settings.s3_access_key and settings.s3_secret_key:
            self.client = boto3.client(
                "s3", endpoint_url=settings.s3_endpoint,
                aws_access_key_id=settings.s3_access_key,
                aws_secret_access_key=settings.s3_secret_key,
                region_name="us-east-1",
            )
        elif not settings.demo_mode:
            raise RuntimeError("S3 credentials are required outside DEMO_MODE")
        self.root = Path.home() / ".local/share/ttc-demo-resumes"

    def _local_path(self, key: str) -> Path:
        target = (self.root / key).resolve()
        if not target.is_relative_to(self.root.resolve()):
            raise ValueError("Invalid object key")
        return target

    def _put_sync(self, key: str, data: bytes, content_type: str) -> str:
        if self.client is not None:
            try:
                self.client.head_bucket(Bucket=self.bucket)
            except ClientError as exc:
                code = exc.response["Error"]["Code"]
                if code not in ("404", "NoSuchBucket"):
                    raise
                self.client.create_bucket(Bucket=self.bucket)
            self.client.put_object(Bucket=self.bucket, Key=key, Body=data,
                                   ContentType=content_type)
            return f"s3://{self.bucket}/{key}"
        target = self._local_path(key)
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as output:
            output.write(data)
        return f"local://{key}"

    async def put(self, key: str, data: bytes, content_type: str) -> str:
        return await asyncio.to_thread(self._put_sync, key, data, content_type)

    def _get_sync(self, uri: str) -> bytes:
        if uri.startswith("s3://"):
            bucket, key = uri[5:].split("/", 1)
            if self.client is None or bucket != self.bucket:
                raise RuntimeError("S3 storage unavailable")
            response = self.client.get_object(Bucket=bucket, Key=key)
            return response["Body"].read()
        if uri.startswith("local://"):
            return self._local_path(uri[8:]).read_bytes()
        raise ValueError("Unknown object URI")

    async def get(self, uri: str) -> bytes:
        return await asyncio.to_thread(self._get_sync, uri)

    def _delete_sync(self, uri: str) -> None:
        if uri.startswith("s3://"):
            bucket, key = uri[5:].split("/", 1)
            if self.client is None or bucket != self.bucket:
                raise RuntimeError("S3 storage unavailable")
            self.client.delete_object(Bucket=bucket, Key=key)
        elif uri.startswith("local://"):
            self._local_path(uri[8:]).unlink(missing_ok=True)
        else:
            raise ValueError("Unknown object URI")

    async def delete(self, uri: str) -> None:
        await asyncio.to_thread(self._delete_sync, uri)
