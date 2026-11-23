"""FastAPI entrypoint for the local UI and the private Cloud Run service."""

from typing import List, Literal

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.config import load_settings
from app.gemini import GeminiUnavailable
from app.rag import ask


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    history: List[Turn] = Field(default_factory=list, max_length=20)


app = FastAPI(title="差旅報帳規定問答示範", version="0.1.0")


@app.get("/api/health")
def health():
    settings = load_settings()
    return {"status": "ok", "mode": settings.ai_mode, "storage": settings.storage_mode}


@app.post("/api/ask")
def ask_route(request: AskRequest):
    settings = load_settings()
    try:
        history = [turn.model_dump() for turn in request.history[-6:]]
        return ask(request.question, history, settings)
    except GeminiUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from None
    except (FileNotFoundError, ValueError, RuntimeError):
        raise HTTPException(status_code=503, detail="問答索引尚未準備好，請檢查文件及執行索引建立。") from None
    except Exception:
        # Cloud credentials and third-party errors must not reach the browser.
        raise HTTPException(status_code=503, detail="問答服務暫時無法使用，請稍後重試。") from None


# StaticFiles is mounted after the API routes, so it cannot swallow /api/*.
_web_dir = load_settings().web_dir
if _web_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(_web_dir), html=True), name="web")
