from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import requests

from account_io import TokenAccount, load_token_accounts
from app_config import AppConfig
from logger import logger


@dataclass(slots=True)
class MicrosoftAccountManagerConfig:
    enabled: bool
    base_url: str
    ingest_path: str
    ingest_token: str
    upload_after_oauth: bool
    remark: str


@dataclass(slots=True)
class UploadResult:
    ok: bool
    status_code: int
    message: str
    payload: dict[str, Any]


class MicrosoftAccountManagerClient:
    def __init__(self, config: MicrosoftAccountManagerConfig):
        self.config = config

    def _build_url(self) -> str:
        base_url = self.config.base_url.strip().rstrip("/")
        ingest_path = self.config.ingest_path.strip() or "/api/upload/ingest"
        if not ingest_path.startswith("/"):
            ingest_path = f"/{ingest_path}"
        return f"{base_url}{ingest_path}"

    def _build_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "x-ingest-token": self.config.ingest_token.strip(),
        }

    def upload_token_accounts(self, accounts: list[TokenAccount]) -> UploadResult:
        if not self.config.enabled:
            return UploadResult(ok=False, status_code=0, message="未启用 microsoft-account-manager 上传", payload={})
        if not self.config.base_url.strip():
            return UploadResult(ok=False, status_code=0, message="microsoft-account-manager base_url 未配置", payload={})
        if not self.config.ingest_token.strip():
            return UploadResult(ok=False, status_code=0, message="microsoft-account-manager ingest_token 未配置", payload={})

        url = self._build_url()
        payload = {
            "items": [
                {
                    "account": item.email,
                    "password": item.password,
                    "clientId": item.client_id,
                    "refreshToken": item.refresh_token,
                    "remark": self.config.remark,
                }
                for item in accounts
            ]
        }
        logger.info("Uploading %s token accounts to %s", len(accounts), url)
        response = requests.post(url, headers=self._build_headers(), data=json.dumps(payload), timeout=30)

        try:
            response_payload = response.json()
        except Exception:
            response_payload = {"raw": response.text}

        if not response.ok:
            return UploadResult(
                ok=False,
                status_code=response.status_code,
                message=str(response_payload.get("message") or f"上传失败 ({response.status_code})"),
                payload=response_payload,
            )

        return UploadResult(
            ok=True,
            status_code=response.status_code,
            message=str(response_payload.get("message") or "上传成功"),
            payload=response_payload,
        )

    def upload_token_file(self, path) -> UploadResult:
        accounts = load_token_accounts(path)
        return self.upload_token_accounts(accounts)



def build_microsoft_account_manager_client(config: AppConfig) -> MicrosoftAccountManagerClient:
    mam = config.microsoft_account_manager
    return MicrosoftAccountManagerClient(
        MicrosoftAccountManagerConfig(
            enabled=mam.enabled,
            base_url=mam.base_url,
            ingest_path=mam.ingest_path,
            ingest_token=mam.ingest_token,
            upload_after_oauth=mam.upload_after_oauth,
            remark=mam.remark,
        )
    )
