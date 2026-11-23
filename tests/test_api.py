from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_and_static_home(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_MODE", "local")
    monkeypatch.setenv("STORAGE_MODE", "local")
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["mode"] == "local"
    assert client.get("/").status_code == 200


def test_ask_real_policies_and_followup(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_MODE", "local")
    monkeypatch.setenv("STORAGE_MODE", "local")
    monkeypatch.setenv("INDEX_PATH", str(tmp_path / "index.json"))
    first = client.post("/api/ask", json={"question": "住宿費每晚可以報多少？", "history": []})
    assert first.status_code == 200
    payload = first.json()
    assert "2,500" in payload["answer"]
    assert payload["mode"] == "local"
    assert payload["sources"][0]["section"].startswith("二、住宿上限")
    assert set(payload["sources"][0]) == {"document", "section", "excerpt"}

    follow = client.post("/api/ask", json={
        "question": "那發票要附什麼？",
        "history": [
            {"role": "user", "content": "住宿費每晚可以報多少？"},
            {"role": "assistant", "content": payload["answer"]},
        ],
    })
    assert follow.status_code == 200
    assert "住宿" in follow.json()["answer"]
    assert "發票" in follow.json()["answer"]


def test_natural_lodging_question_and_receipt_followup(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_MODE", "local")
    monkeypatch.setenv("STORAGE_MODE", "local")
    monkeypatch.setenv("INDEX_PATH", str(tmp_path / "index.json"))
    question = "現在出差住宿每晚最多可以報多少？"
    first = client.post("/api/ask", json={"question": question, "history": []})
    assert first.status_code == 200
    payload = first.json()
    assert "2,500" in payload["answer"]
    assert "現行" in payload["sources"][0]["document"]
    assert "住宿上限" in payload["sources"][0]["section"]
    follow = client.post("/api/ask", json={
        "question": "那需要附什麼憑證？",
        "history": [
            {"role": "user", "content": question},
            {"role": "assistant", "content": payload["answer"]},
        ],
    })
    assert follow.status_code == 200
    assert "住宿業者開立的發票或正式收據" in follow.json()["answer"]
    assert "現行" in follow.json()["sources"][0]["document"]


def test_unknown_and_old_policy_do_not_quote_stale_amount(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_MODE", "local")
    monkeypatch.setenv("STORAGE_MODE", "local")
    monkeypatch.setenv("INDEX_PATH", str(tmp_path / "index.json"))
    unknown = client.post("/api/ask", json={"question": "有沒有寵物醫療補助？", "history": []}).json()
    assert unknown["sources"] == []
    assert "找不到" in unknown["answer"]
    unsupported = client.post("/api/ask", json={"question": "交通費可以報買車嗎？", "history": []}).json()
    assert unsupported["sources"] == []
    old = client.post("/api/ask", json={"question": "舊版住宿上限是多少？", "history": []}).json()
    assert old["sources"] == []
    assert "2,000" not in old["answer"]
    dated_old = client.post("/api/ask", json={"question": "2026-06-30 的住宿上限？", "history": []}).json()
    assert dated_old["sources"] == []
    assert "舊版" in dated_old["answer"]
    current_meal = client.post("/api/ask", json={"question": "2026 年 3 月餐費每天上限是多少？", "history": []}).json()
    assert "300" in current_meal["answer"]


def test_local_mode_never_calls_vertex_even_with_project(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_MODE", "local")
    monkeypatch.setenv("STORAGE_MODE", "local")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "demo-project")
    monkeypatch.setenv("INDEX_PATH", str(tmp_path / "index.json"))

    def fail_if_called(*args, **kwargs):
        raise AssertionError("remote Vertex AI call in local mode")

    monkeypatch.setattr("app.vertex.urlopen", fail_if_called)
    response = client.post("/api/ask", json={"question": "住宿上限是多少？", "history": []})
    assert response.status_code == 200
    assert "2,500" in response.json()["answer"]


def test_empty_question_is_rejected():
    assert client.post("/api/ask", json={"question": "", "history": []}).status_code == 422
