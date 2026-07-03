"""접속 비밀번호 (기본 00000) — Flask 세션 + DB 저장."""
from __future__ import annotations

from werkzeug.security import check_password_hash, generate_password_hash

import db

PASSWORD_SETTING_KEY = "access_password_hash"
DEFAULT_PASSWORD = "00000"


def init_default_password() -> None:
    if not db.get_setting(PASSWORD_SETTING_KEY):
        db.set_setting(PASSWORD_SETTING_KEY, generate_password_hash(DEFAULT_PASSWORD))


def verify_password(plain: str) -> bool:
    stored = db.get_setting(PASSWORD_SETTING_KEY)
    if not stored:
        init_default_password()
        stored = db.get_setting(PASSWORD_SETTING_KEY)
    return check_password_hash(stored or "", plain or "")


def change_password(current: str, new_password: str) -> tuple[bool, str]:
    if not verify_password(current):
        return False, "현재 비밀번호가 올바르지 않습니다."
    new_password = (new_password or "").strip()
    if not new_password:
        return False, "새 비밀번호를 입력하세요."
    db.set_setting(PASSWORD_SETTING_KEY, generate_password_hash(new_password))
    return True, "비밀번호가 변경되었습니다."
