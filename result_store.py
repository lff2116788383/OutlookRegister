from __future__ import annotations

from app_config import LOGGED_EMAIL_PATH, OUTLOOK_TOKEN_PATH, UNLOGGED_EMAIL_PATH


class ResultStore:
    def save_registered_email(self, email: str, password: str, oauth_enabled: bool) -> None:
        file_path = LOGGED_EMAIL_PATH if oauth_enabled else UNLOGGED_EMAIL_PATH
        with file_path.open("a", encoding="utf-8") as file:
            file.write(f"{email}@outlook.com: {password}\n")

    def save_token_result(
        self,
        email: str,
        password: str,
        refresh_token: str,
        access_token: str,
        expire_at: float,
    ) -> None:
        with OUTLOOK_TOKEN_PATH.open("a", encoding="utf-8") as file:
            file.write(
                f"{email}@outlook.com---{password}---{refresh_token}---{access_token}---{expire_at}\n"
            )
