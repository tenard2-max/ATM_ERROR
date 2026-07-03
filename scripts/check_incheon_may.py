"""2026-05 인천공항 장애 건수 확인."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import db
import pandas as pd

db.init_db()
df = db.load_all_incidents()
may = df[df["연월"] == "2026-05"]

print("=== 2026-05 전체 ===")
print(f"총 건수: {len(may):,}")

print('\n=== 지점명 "인천" 포함 ===')
incheon = may[may["지점명"].astype(str).str.contains("인천", na=False)]
print(incheon["지점명"].value_counts())
print(f"합계: {len(incheon):,}건")

print('\n=== 지점명 == "인천공항" ===')
exact = may[may["지점명"] == "인천공항"]
print(f"건수: {len(exact):,}")

print("\n=== 1411건과 일치하는 지점 ===")
vc = may["지점명"].value_counts()
match = vc[vc == 1411]
if len(match):
    for name, cnt in match.items():
        print(f"  {name}: {cnt:,}건")
else:
    print("  없음")

print("\n=== TOP 10 지점 (2026-05) ===")
print(vc.head(10))
