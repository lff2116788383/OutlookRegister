from __future__ import annotations

import random
import secrets
import string

from faker import Faker

_FAKE = Faker("en_US")
_PASSWORD_SPECIALS = "!@#$%^&*"


def random_email() -> str:
    firstname = _FAKE.first_name()
    lastname = _FAKE.last_name()
    year = str(random.randint(1970, 2002))

    formats = [
        f"{firstname}{lastname}{year}",
        f"{firstname}.{lastname}{year}",
        f"{firstname}{year}",
        f"{lastname}{firstname}{year}",
    ]
    email = random.choice(formats).lower()
    return "".join(char for char in email if char.isalnum() or char == ".")


def build_email_address(email: str, domain: str) -> str:
    normalized_domain = str(domain or "outlook.com").strip().lower()
    if normalized_domain not in {"hotmail.com", "outlook.com"}:
        normalized_domain = "outlook.com"
    return f"{email}@{normalized_domain}"


def generate_strong_password(length: int | None = None) -> str:
    password_length = length or random.randint(11, 15)
    chars = string.ascii_letters + string.digits + _PASSWORD_SPECIALS

    while True:
        password = "".join(secrets.choice(chars) for _ in range(password_length))
        if (
            any(char.islower() for char in password)
            and any(char.isupper() for char in password)
            and any(char.isdigit() for char in password)
            and any(char in _PASSWORD_SPECIALS for char in password)
        ):
            return password
