"""Flask 앱 공통 — 세션·네비게이션·메모리 상태."""
from __future__ import annotations

import uuid
from typing import Any

import pandas as pd

import db
from config import normalize_fault_type

try:
    from flask import has_request_context, session
except ImportError:  # pragma: no cover
    has_request_context = lambda: False  # type: ignore
    session = {}  # type: ignore

_MEMORY: dict[str, dict[str, Any]] = {}
_CLI_STATE: dict[str, Any] = {}


def _has_flask() -> bool:
    try:
        return has_request_context()
    except RuntimeError:
        return False


def _ensure_sid() -> str:
    if _has_flask():
        sid = session.get("sid")
        if not sid:
            sid = uuid.uuid4().hex
            session["sid"] = sid
    else:
        sid = _CLI_STATE.setdefault("sid", uuid.uuid4().hex)
    if sid not in _MEMORY:
        _MEMORY[sid] = {
            "grouping_draft": pd.DataFrame(),
            "grouping_message": "",
            "pending_uploads": [],
            "c_allow_unconfirmed": False,
        }
    return sid


def _mem() -> dict[str, Any]:
    return _MEMORY[_ensure_sid()]


def _get(key: str, default: Any = None) -> Any:
    if _has_flask():
        return session.get(key, default)
    return _CLI_STATE.get(key, default)


def _set(key: str, value: Any) -> None:
    if _has_flask():
        session[key] = value
    else:
        _CLI_STATE[key] = value


def get_incidents_df() -> pd.DataFrame:
    db.init_db()
    return db.load_all_incidents()


def get_home_selected_month(df: pd.DataFrame) -> str | None:
    if df.empty:
        return None
    months = sorted(df["연월"].unique())
    current = _get("home_selected_month")
    if current not in months:
        _set("home_selected_month", months[-1])
    return _get("home_selected_month")


def set_home_selected_month(month: str) -> None:
    _set("home_selected_month", month)


def get_grouping_draft() -> pd.DataFrame:
    draft = _mem().get("grouping_draft", pd.DataFrame())
    if isinstance(draft, pd.DataFrame) and not draft.empty:
        return draft
    saved = db.load_grouping_rules(confirmed_only=False)
    if saved.empty:
        return pd.DataFrame()
    draft = saved[["장애코드2", "세부장애", "장애내용", "ai_type", "confirmed_type"]].copy()
    draft["ai_type"] = draft["ai_type"].map(normalize_fault_type)
    draft["confirmed_type"] = draft["confirmed_type"].map(normalize_fault_type)
    _mem()["grouping_draft"] = draft
    return draft


def set_grouping_draft(draft: pd.DataFrame) -> None:
    _mem()["grouping_draft"] = draft


def get_grouping_message() -> str:
    return str(_mem().get("grouping_message") or "")


def set_grouping_message(message: str) -> None:
    _mem()["grouping_message"] = message


def clear_grouping_draft() -> None:
    _mem()["grouping_draft"] = pd.DataFrame()
    _mem()["grouping_message"] = ""


def get_pending_uploads() -> list:
    return list(_mem().get("pending_uploads") or [])


def set_pending_uploads(items: list) -> None:
    _mem()["pending_uploads"] = items


def get_fault_content_filter(month: str, month_df: pd.DataFrame) -> list[str]:
    all_options = sorted(month_df["장애내용"].dropna().astype(str).unique().tolist())
    key = f"fault_content_{month}"
    selected = _get(key)
    if selected is None:
        _set(key, all_options)
        return all_options
    return [o for o in selected if o in all_options]


def set_fault_content_filter(month: str, selected: list[str]) -> None:
    _set(f"fault_content_{month}", selected)


def set_nav_target(target_type: str, target_value: str, selected_month: str) -> None:
    _set("nav_target_type", target_type)
    _set("nav_target_value", target_value)
    _set("nav_selected_month", selected_month)


def get_nav_target() -> tuple[str | None, str | None, str | None]:
    return (
        _get("nav_target_type"),
        _get("nav_target_value"),
        _get("nav_selected_month"),
    )


def set_nav_to_c(selected_month: str, fault_code: str | None = None) -> None:
    _set("nav_c_month", selected_month)
    _set("nav_c_fault_code", fault_code)


def get_nav_to_c() -> tuple[str | None, str | None]:
    return _get("nav_c_month"), _get("nav_c_fault_code")


def allow_c_unconfirmed() -> bool:
    return bool(_mem().get("c_allow_unconfirmed"))


def set_allow_c_unconfirmed(value: bool = True) -> None:
    _mem()["c_allow_unconfirmed"] = value


NAV_TYPE_TO_COLUMN = {
    "기번": "기번",
    "기종": "기종",
    "지점": "지점명",
}
