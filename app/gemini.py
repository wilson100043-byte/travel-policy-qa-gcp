"""Small opt-in Gemini REST adapter; no call happens during import or local mode."""

import json
from typing import List
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.config import Settings, require_gemini_opt_in


# One question can make up to three sequential calls (rewrite, embed, generate).
# 3 x 15s stays under the Cloud Run service request timeout of 60s in infra/app.
GEMINI_TIMEOUT_SECONDS = 15


class GeminiUnavailable(RuntimeError):
    """A safe, user-facing description of a Gemini request failure."""


class GeminiClient:
    def __init__(self, settings: Settings):
        require_gemini_opt_in(settings)
        self.settings = settings

    def _post(self, model: str, method: str, payload: dict) -> dict:
        # The key stays in a request header, never a URL, log, or exception.
        url = "https://generativelanguage.googleapis.com/v1beta/models/{}:{}".format(model, method)
        request = Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "x-goog-api-key": self.settings.gemini_api_key},
            method="POST",
        )
        try:
            with urlopen(request, timeout=GEMINI_TIMEOUT_SECONDS) as response:
                return json.load(response)
        except HTTPError as error:
            if error.code == 429:
                raise GeminiUnavailable("Gemini 免費額度或請求頻率已達上限，請稍後再試。") from None
            raise GeminiUnavailable("Gemini 暫時無法使用；請檢查金鑰、模型與免費方案狀態。") from None
        except (URLError, TimeoutError, OSError, ValueError):
            raise GeminiUnavailable("無法連接 Gemini，請稍後再試。") from None

    def embed(self, text: str, task_type: str, title: str = "") -> List[float]:
        model = self.settings.gemini_embedding_model
        payload = {
            "model": "models/" + model,
            "content": {"parts": [{"text": text}]},
            "taskType": task_type,
            "outputDimensionality": 768,
        }
        if title:
            payload["title"] = title
        result = self._post(model, "embedContent", payload)
        try:
            vector = result["embedding"]["values"]
            if not vector or not all(isinstance(value, (int, float)) for value in vector):
                raise ValueError("invalid embedding")
            return [float(value) for value in vector]
        except (KeyError, TypeError, ValueError):
            raise GeminiUnavailable("Gemini 回傳的向量格式不正確。") from None

    def generate(self, prompt: str) -> str:
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 600},
        }
        result = self._post(self.settings.gemini_generation_model, "generateContent", payload)
        try:
            text = "".join(
                part.get("text", "")
                for part in result["candidates"][0]["content"]["parts"]
            ).strip()
            if not text:
                raise ValueError("empty model reply")
            return text
        except (KeyError, IndexError, TypeError, ValueError):
            raise GeminiUnavailable("Gemini 沒有回傳可用的回答。") from None
