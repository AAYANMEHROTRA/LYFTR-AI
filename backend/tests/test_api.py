import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_app.db")
os.environ.setdefault("LLM_API_KEYS", "test-key-one,test-key-two")
os.environ.setdefault("ENABLE_FAILURE_SIMULATION", "true")

from fastapi.testclient import TestClient
from app import main


def fake_response(text="Hello from test"):
    class Usage:
        prompt_tokens = 12
        completion_tokens = 4
    class Message:
        content = text
    class Choice:
        message = Message()
    class Response:
        choices = [Choice()]
        usage = Usage()
        _hidden_params = {}
    return Response()


def test_health(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "DATABASE_URL", f"sqlite:///{tmp_path / 'health.db'}")
    with TestClient(main.app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["keys_configured"] >= 2


def test_chat_and_history(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "DATABASE_URL", f"sqlite:///{tmp_path / 'chat.db'}")
    monkeypatch.setattr(main, "run_completion", lambda messages, simulation: (fake_response(), "key_1", 0, False))
    with TestClient(main.app) as client:
        response = client.post("/chat", json={"session_id": "test-session", "message": "Hi"})
        assert response.status_code == 200
        body = response.json()
        assert body["reply"] == "Hello from test"
        assert body["metadata"]["resolution_source"] == "LIVE_INFERENCE"
        history = client.get("/sessions/test-session/messages")
        assert history.status_code == 200
        assert [m["role"] for m in history.json()["messages"]] == ["user", "assistant"]


def test_validation_and_unknown_session(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "DATABASE_URL", f"sqlite:///{tmp_path / 'errors.db'}")
    with TestClient(main.app) as client:
        assert client.post("/chat", json={"session_id": "s1", "message": "   "}).status_code == 422
        assert client.get("/sessions/missing").status_code == 404


def test_simulated_failover(monkeypatch):
    monkeypatch.setattr(main, "ENABLE_FAILURE_SIMULATION", True)
    assert main.parse_simulation("key_1=429,key_2=500") == {"key_1": 429, "key_2": 500}
