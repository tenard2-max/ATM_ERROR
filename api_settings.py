"""Gemini API 키 .env 저장·로드."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from config import BASE_DIR

ENV_PATH = BASE_DIR / ".env"
ENV_KEY = "GEMINI_API_KEY"


def load_env() -> None:
    if ENV_PATH.exists():
        load_dotenv(ENV_PATH, override=True)


def get_api_key() -> str | None:
    load_env()
    key = os.getenv(ENV_KEY)
    if key and key.strip():
        return key.strip()
    return None


def mask_api_key(key: str | None) -> str:
    if not key:
        return "미설정"
    if len(key) <= 8:
        return "*" * len(key)
    return f"{key[:4]}...{key[-4:]}"


def save_api_key(key: str) -> None:
    cleaned = key.strip()
    if not cleaned:
        raise ValueError("API 키를 입력해주세요.")

    lines: list[str] = []
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.strip().startswith(f"{ENV_KEY}="):
                lines.append(line)
    lines.append(f"{ENV_KEY}={cleaned}")
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ[ENV_KEY] = cleaned
    load_env(override=True)


def delete_api_key() -> None:
    if not ENV_PATH.exists():
        os.environ.pop(ENV_KEY, None)
        return
    lines = [
        line
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith(f"{ENV_KEY}=")
    ]
    if lines:
        ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    else:
        ENV_PATH.unlink(missing_ok=True)
    os.environ.pop(ENV_KEY, None)
