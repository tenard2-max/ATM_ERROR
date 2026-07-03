# GitHub 등록 및 클라우드 배포 가이드

Flask 분석 앱은 **정적 HTML만으로는 동작하지 않습니다.** Python 서버(로컬 또는 Render 등)가 필요합니다.

## 1. GitHub에 코드 올리기

```powershell
cd "프로젝트폴더"
git init
git add .
git commit -m "Initial commit: ATM fault analysis PoC"
gh repo create atm-fault-poc --public --source=. --remote=origin --push
```

`gh` CLI가 없으면 [GitHub](https://github.com/new)에서 저장소를 만든 뒤:

```powershell
git remote add origin https://github.com/<사용자명>/atm-fault-poc.git
git branch -M main
git push -u origin main
```

## 2. 로컬 실행

```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# .env 에 GEMINI_API_KEY 입력 (선택)
python web_app.py
```

브라우저: http://localhost:8502

`run.bat` 실행해도 동일합니다. DB가 비어 있으면 `sample_data/` 샘플 3개월이 자동 적재됩니다.

## 3. Render.com 배포 (권장)

1. [Render](https://render.com) 가입 → **New → Blueprint** → GitHub 저장소 연결
2. 저장소 루트의 `render.yaml` 자동 인식
3. Environment → `GEMINI_API_KEY` 추가 (AI 분류 사용 시)
4. Deploy 완료 후 표시되는 URL 접속

**참고:** Render 무료 플랜은 재배포 시 SQLite(`data/incidents.db`)가 초기화될 수 있습니다. 데모용으로는 시작 시 샘플 데이터가 다시 적재됩니다.

## 4. 환경 변수

| 변수 | 필수 | 설명 |
|------|------|------|
| `GEMINI_API_KEY` | 선택 | Google Gemini API 키. 없으면 키워드 규칙 폴백 |
| `SECRET_KEY` | 배포 시 권장 | Flask 세션 암호화 |
| `PORT` | 자동 | Render/Heroku 등이 설정 |

## 5. GitHub Pages 한계

GitHub Pages는 **정적 미리보기**만 제공합니다. 저장소 루트 `index.html`은 안내 페이지이며, 차트·업로드·DB는 Flask 서버에서만 동작합니다.

| 접속 방법 | 결과 |
|-----------|------|
| GitHub Pages (`*.github.io`) | 안내 페이지만 표시 |
| `python web_app.py` | 전체 분석 기능 사용 |
| Render 배포 URL | 전체 분석 기능 사용 |

Render 배포 후 `site-config.js`의 `liveAppUrl`에 URL을 넣으면 GitHub Pages에서 자동으로 앱으로 이동합니다.

```javascript
window.SITE_CONFIG = {
  liveAppUrl: "https://your-app.onrender.com",
  githubRepo: "https://github.com/사용자명/저장소명",
};
```
