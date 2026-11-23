"""Small Vertex AI REST adapter; no call happens during import or local mode.

Authentication uses the runtime service account through Application Default
Credentials, so the service never handles a long-lived API key.
"""

import json
from typing import List
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.config import Settings, require_vertex


# One question can make up to three sequential calls (rewrite, embed, generate).
# 3 x 15s stays under the Cloud Run service request timeout of 60s in infra/app.
VERTEX_TIMEOUT_SECONDS = 15
EMBEDDING_DIMENSIONS = 768
_SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]


class VertexUnavailable(RuntimeError):
    """A safe, user-facing description of a Vertex AI request failure."""


class VertexClient:
    def __init__(self, settings: Settings):
        require_vertex(settings)
        self.settings = settings
        self._credentials = None

    def _token(self) -> str:
        try:
            import google.auth
            from google.auth.transport.requests import Request as AuthRequest
        except ImportError:
            raise RuntimeError("google-auth is required for AI_MODE=vertex") from None
        if self._credentials is None:
            self._credentials, _ = google.auth.default(scopes=_SCOPES)
        if not self._credentials.valid:
            self._credentials.refresh(AuthRequest())
        return self._credentials.token

    def _url(self, model: str, method: str) -> str:
        location = self.settings.vertex_location
        host = "aiplatform.googleapis.com" if location == "global" else location + "-aiplatform.googleapis.com"
        return "https://{}/v1/projects/{}/locations/{}/publishers/google/models/{}:{}".format(
            host, self.settings.gcp_project, location, model, method
        )

    def _post(self, model: str, method: str, payload: dict) -> dict:
        try:
            token = self._token()
        except Exception:
            # Credential details must not reach the browser.
            raise VertexUnavailable("AI 服務驗證失敗，請通知系統管理者。") from None
        request = Request(
            self._url(model, method),
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + token},
            method="POST",
        )
        try:
            with urlopen(request, timeout=VERTEX_TIMEOUT_SECONDS) as response:
                return json.load(response)
        except HTTPError as error:
            if error.code == 429:
                raise VertexUnavailable("AI 服務目前請求過多，請稍後再試。") from None
            raise VertexUnavailable("AI 服務暫時無法使用，請稍後再試。") from None
        except (URLError, TimeoutError, OSError, ValueError):
            raise VertexUnavailable("無法連接 AI 服務，請稍後再試。") from None

    def embed(self, text: str, task_type: str, title: str = "") -> List[float]:
        instance = {"content": text, "task_type": task_type}
        if title and task_type == "RETRIEVAL_DOCUMENT":
            instance["title"] = title
        payload = {
            "instances": [instance],
            "parameters": {"outputDimensionality": EMBEDDING_DIMENSIONS, "autoTruncate": True},
        }
        result = self._post(self.settings.embedding_model, "predict", payload)
        try:
            vector = result["predictions"][0]["embeddings"]["values"]
            if not vector or not all(isinstance(value, (int, float)) for value in vector):
                raise ValueError("invalid embedding")
            return [float(value) for value in vector]
        except (KeyError, IndexError, TypeError, ValueError):
            raise VertexUnavailable("AI 服務回傳的向量格式不正確。") from None

    def generate(self, prompt: str) -> str:
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 600},
        }
        result = self._post(self.settings.generation_model, "generateContent", payload)
        try:
            text = "".join(
                part.get("text", "")
                for part in result["candidates"][0]["content"]["parts"]
            ).strip()
            if not text:
                raise ValueError("empty model reply")
            return text
        except (KeyError, IndexError, TypeError, ValueError):
            raise VertexUnavailable("AI 服務沒有回傳可用的回答。") from None
