# Vit_S GroupwareService FastAPI

Vitamine-S GroupwareService의 AI 기능을 담당하는 FastAPI 서버입니다.

---

## 기술 스택

| 항목 | 내용 |
|------|------|
| Language | Python |
| Framework | FastAPI |
| ASGI Server | Uvicorn |
| Config | Pydantic Settings, python-dotenv |
| AI Client | Google GenAI |
| Template | Jinja2 |
| Test | Pytest |

---

## 프로젝트 구조

```text
app/
├── __init__.py
├── main.py
└── core/
    ├── __init__.py
    └── config.py
```

---

## 환경 설정

`.env.example`을 복사해 `.env`를 생성합니다.

```bash
cp .env.example .env
```

Windows CMD에서는 다음 명령어를 사용할 수 있습니다.

```cmd
copy .env.example .env
```

---

## 가상환경 설정

```bash
python -m venv .venv
```

Windows CMD:

```cmd
.venv\Scripts\activate.bat
```

PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

---

## 의존성 설치

```bash
pip install -r requirements.txt
```

---

## 서버 실행

```bash
uvicorn app.main:app --reload --port 8000
```

---

## API 문서

서버 실행 후 아래 주소에서 Swagger 문서를 확인할 수 있습니다.

```text
http://127.0.0.1:8000/docs
```

---

## Health Check

```text
GET /health
```