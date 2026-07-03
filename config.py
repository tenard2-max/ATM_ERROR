"""프로젝트 공통 설정."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
MAPPING_DIR = BASE_DIR / "mapping"
SAMPLE_DIR = BASE_DIR / "sample_data"
DB_PATH = DATA_DIR / "incidents.db"
MAPPING_FILE = MAPPING_DIR / "장애코드.xlsx"

import os

# 로컬 기본 8502 / 클라우드(Render 등)는 PORT 환경변수 사용
PORT = int(os.environ.get("PORT", "8502"))
APP_URL = os.environ.get("APP_URL", f"http://localhost:{PORT}")
LOCAL_APP_URL = APP_URL

MAX_UPLOAD_FILES = 12
ANOMALY_WINDOW = 3
ANOMALY_SIGMA = 2
TOP_N = 10
PRIORITY_TOP_N = 20

PRIORITY_WEIGHTS = {
    "최근3개월건수": 0.40,
    "전월대비증가율": 0.30,
    "이상치횟수": 0.20,
    "기종대비편차": 0.10,
}

REQUIRED_COLUMNS = [
    "점번",
    "지점명",
    "기번",
    "기종",
    "발생일자",
    "세부장애",
    "장애내용",
]

OPTIONAL_COLUMNS = ["장애코드2"]

MAPPING_SOURCE_COL = "세부장애"
MAPPING_TARGET_COL = "장애코드2"

FAULT_TYPES = ["현금부", "카드부", "통장부", "통신", "기타"]

LEGACY_FAULT_TYPE_MAP = {
    "카드류": "카드부",
    "현금류": "현금부",
    "통신류": "통신",
    "기구류": "기타",
}


def normalize_fault_type(label: str | None) -> str:
    if not label:
        return ""
    text = str(label).strip()
    return LEGACY_FAULT_TYPE_MAP.get(text, text)


PASSBOOK_FAULT_CONTENTS = (
    "통장 Jam 또는 잔류",
    "통장 미수취",
    "통장걸림",
    "통장부 매체 인식 불가(MS)",
)

FAULT_CONTENT_TYPE_MAP: dict[str, str] = {
    content: "통장부" for content in PASSBOOK_FAULT_CONTENTS
}

GEMINI_MODEL = "gemini-2.0-flash"

KEYWORD_RULES = [
    (["통장", "통장부"], "통장부"),
    (["카드", "명세", "IC"], "카드부"),
    (["현금", "입금", "출금", "지폐", "동전", "캐시"], "현금부"),
    (["통신", "네트워크", "LAN", "회선", "접속", "링크"], "통신"),
    (["기구", "도어", "잠금", "센서", "프린터", "키보드", "화면", "디스플레이"], "기타"),
]


def classify_fault_content(description: str) -> str:
    """장애내용 → 모듈 유형 (키워드 폴백)."""
    text = str(description).strip()
    if text in FAULT_CONTENT_TYPE_MAP:
        return FAULT_CONTENT_TYPE_MAP[text]
    for keywords, label in KEYWORD_RULES:
        if any(word in text for word in keywords):
            return label
    return "기타"
