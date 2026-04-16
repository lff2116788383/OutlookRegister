from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

DELIMITER = "----"


@dataclass(slots=True)
class EmailAccount:
    email: str
    password: str

    def to_line(self) -> str:
        return f"{self.email.strip().lower()}{DELIMITER}{self.password.strip()}"


@dataclass(slots=True)
class TokenAccount:
    email: str
    password: str
    client_id: str
    refresh_token: str

    def to_line(self) -> str:
        return (
            f"{self.email.strip().lower()}{DELIMITER}{self.password.strip()}"
            f"{DELIMITER}{self.client_id.strip()}{DELIMITER}{self.refresh_token.strip()}"
        )


def _iter_clean_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        lines.append(line)
    return lines



def parse_email_account_line(line: str) -> EmailAccount:
    normalized = str(line or "").strip()
    if not normalized:
        raise ValueError("账号行不能为空")

    if DELIMITER in normalized:
        parts = [part.strip() for part in normalized.split(DELIMITER)]
    elif ":" in normalized:
        parts = [part.strip() for part in normalized.split(":", 1)]
    else:
        parts = []

    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError("邮箱账号格式必须为 email----password")

    return EmailAccount(email=parts[0].lower(), password=parts[1])



def parse_token_account_line(line: str) -> TokenAccount:
    normalized = str(line or "").strip()
    if not normalized:
        raise ValueError("Token 账号行不能为空")

    parts = [part.strip() for part in normalized.split(DELIMITER)]
    if len(parts) != 4 or any(not item for item in parts):
        raise ValueError("Token 账号格式必须为 email----password----client_id----refresh_token")

    return TokenAccount(
        email=parts[0].lower(),
        password=parts[1],
        client_id=parts[2],
        refresh_token=parts[3],
    )



def load_email_accounts(path: Path) -> list[EmailAccount]:
    if not path.exists():
        return []

    seen: set[str] = set()
    items: list[EmailAccount] = []
    for line in _iter_clean_lines(path.read_text(encoding="utf-8")):
        account = parse_email_account_line(line)
        key = account.email.lower()
        if key in seen:
            continue
        seen.add(key)
        items.append(account)
    return items



def load_token_accounts(path: Path) -> list[TokenAccount]:
    if not path.exists():
        return []

    seen: set[str] = set()
    items: list[TokenAccount] = []
    for line in _iter_clean_lines(path.read_text(encoding="utf-8")):
        account = parse_token_account_line(line)
        key = account.email.lower()
        if key in seen:
            continue
        seen.add(key)
        items.append(account)
    return items



def export_email_accounts(path: Path, accounts: list[EmailAccount]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    seen: set[str] = set()
    for account in accounts:
        key = account.email.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        lines.append(account.to_line())
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")



def export_token_accounts(path: Path, accounts: list[TokenAccount]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    seen: set[str] = set()
    for account in accounts:
        key = account.email.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        lines.append(account.to_line())
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
