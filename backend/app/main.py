from __future__ import annotations

import json
import hashlib
import os
import re
import sqlite3
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import litellm
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from litellm import Cache
from pydantic import BaseModel, Field, field_validator

APP_DIR = Path(__file__).resolve().parent
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")
DEFAULT_MODEL = os.getenv("LLM_MODEL", "gemini/gemini-2.0-flash")
DEFAULT_SYSTEM_PROMPT = os.getenv(
    "DEFAULT_SYSTEM_PROMPT", "You are a helpful, concise assistant. Be accurate and clear."
)
ENABLE_FAILURE_SIMULATION = os.getenv("ENABLE_FAILURE_SIMULATION", "false").lower() == "true"
ALLOWED_ORIGINS = [x.strip() for x in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",") if x.strip()]


def parse_keys() -> list[tuple[str, str]]:
    raw = os.getenv("LLM_API_KEYS", "")
    return [(f"key_{i+1}", key.strip()) for i, key in enumerate(raw.split(",")) if key.strip()]


KEYS = parse_keys()
CACHE_SEEN: set[str] = set()


def db_path() -> str:
    value = DATABASE_URL
    if value.startswith("sqlite:////"):
        return "/" + value[len("sqlite:////"):]
    if value.startswith("sqlite:///"):
        return value[len("sqlite:///"):]
    if value.startswith("sqlite://"):
        return value[len("sqlite://"):]
    raise RuntimeError("DATABASE_URL must be a SQLite URL")


def connect() -> sqlite3.Connection:
    path = db_path()
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=20)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database() -> None:
    with connect() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            system_prompt TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('user','assistant')),
            content TEXT NOT NULL,
            metadata TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(session_id) REFERENCES sessions(session_id)
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_session_id_id ON messages(session_id, id)")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def configure_cache() -> None:
    # LiteLLM's built-in local cache; memory-backed by design for this single-instance demo.
    litellm.cache = Cache(type="local")
    litellm.enable_cache()


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    configure_cache()
    yield


app = FastAPI(title="LYFTR AI Chat API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Simulate-Failure"],
)


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=4000)
    system_prompt: str | None = Field(default=None, max_length=4000)

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("session_id cannot be empty")
        return value.strip()

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message cannot be empty")
        return value


class ChatMetadata(BaseModel):
    resolution_source: str
    model: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    key_id: str | None
    fallback_attempts: int


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    metadata: ChatMetadata


def parse_simulation(header_value: str | None) -> dict[str, int]:
    if not ENABLE_FAILURE_SIMULATION or not header_value:
        return {}
    simulated: dict[str, int] = {}
    for pair in header_value.split(","):
        if "=" not in pair:
            continue
        key_id, status = pair.strip().split("=", 1)
        try:
            code = int(status)
        except ValueError:
            continue
        if code in {429, 500, 502, 503}:
            simulated[key_id.strip()] = code
    return simulated


def is_retryable_provider_error(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None)
    if status in {429, 500, 502, 503}:
        return True
    name = type(exc).__name__.lower()
    message = str(exc).lower()
    return any(token in name or token in message for token in (
        "ratelimit", "quota", "internalserver", "serviceunavailable", "timeout", "502", "503", "500", "429"
    ))


def cached_response(response: Any) -> bool:
    hidden = getattr(response, "_hidden_params", {}) or {}
    if hidden.get("cache_hit") is True:
        return True
    # LiteLLM versions may expose cache metadata in response headers/hidden params.
    cache_info = hidden.get("cache") or hidden.get("cache_hit")
    return bool(cache_info)


def token_count(response: Any, field: str) -> int:
    usage = getattr(response, "usage", None)
    value = getattr(usage, field, 0) if usage is not None else 0
    return int(value or 0)



def run_completion(
    messages: list[dict[str, str]],
    simulation: dict[str, int]
) -> tuple[Any, str | None, int, bool]:

    if not KEYS:
        raise HTTPException(
            status_code=503,
            detail="all providers unavailable"
        )

    failures = 0
    last_error = None

    for key_id, api_key in KEYS:

        if simulation.get("*") or simulation.get(key_id):
            failures += 1
            last_error = RuntimeError(
                f"Simulated provider failure for {key_id}"
            )
            continue

        try:
            response = litellm.completion(
                model=DEFAULT_MODEL,
                messages=messages,
                api_key=api_key,
                caching=True,
                num_retries=0,
                timeout=25,
            )

            return (
                response,
                key_id,
                failures,
                cached_response(response)
            )

        except Exception as exc:
            failures += 1
            last_error = exc

            # Log diagnostic information without exposing API keys.
            safe_message = str(exc)

            for _, configured_key in KEYS:
                safe_message = safe_message.replace(
                    configured_key,
                    "[REDACTED]"
                )

            safe_message = re.sub(
                r"(?i)(api[_ -]?key|token|authorization)"
                r"(\s*[:=]\s*)[^\s,;]+",
                r"\1\2[REDACTED]",
                safe_message
            )

            print(
                f"Provider attempt {key_id} failed: "
                f"{type(exc).__name__}; "
                f"status={getattr(exc, 'status_code', None)}; "
                f"message={safe_message[:500]}",
                flush=True
            )

            continue

    raise HTTPException(
        status_code=503,
        detail="all providers unavailable"
    ) from last_error


@app.get("/health")
def health() -> dict[str, Any]:
    try:
        with connect() as conn:
            conn.execute("SELECT 1").fetchone()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    return {"status": "ok", "keys_configured": len(KEYS), "cache_enabled": True}


@app.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, x_simulate_failure: str | None = Header(default=None)) -> ChatResponse:
    with connect() as conn:
        session = conn.execute("SELECT * FROM sessions WHERE session_id=?", (payload.session_id,)).fetchone()
        if session is None:
            system_prompt = (payload.system_prompt or DEFAULT_SYSTEM_PROMPT).strip()
            if not system_prompt:
                system_prompt = DEFAULT_SYSTEM_PROMPT
            history: list[dict[str, str]] = []
        else:
            system_prompt = session["system_prompt"]
            history = [
                {"role": row["role"], "content": row["content"]}
                for row in conn.execute(
                    "SELECT role, content FROM messages WHERE session_id=? ORDER BY id", (payload.session_id,)
                ).fetchall()
            ]

    messages = [{"role": "system", "content": system_prompt}, *history, {"role": "user", "content": payload.message}]
    cache_fingerprint = hashlib.sha256(json.dumps([DEFAULT_MODEL, messages], sort_keys=True).encode()).hexdigest()
    known_cache_entry = cache_fingerprint in CACHE_SEEN
    start = time.perf_counter()
    response, key_id, fallback_attempts, provider_cache_hit = run_completion(messages, parse_simulation(x_simulate_failure))
    elapsed = max(0, int((time.perf_counter() - start) * 1000))
    cache_hit = provider_cache_hit or known_cache_entry
    CACHE_SEEN.add(cache_fingerprint)
    try:
        reply = response.choices[0].message.content
    except Exception as exc:
        raise HTTPException(status_code=503, detail="all providers unavailable") from exc
    if isinstance(reply, list):
        reply = "".join(str(part.get("text", "")) if isinstance(part, dict) else str(part) for part in reply)
    reply = str(reply or "").strip()
    if not reply:
        raise HTTPException(status_code=503, detail="all providers unavailable")

    # If LiteLLM cache metadata is not exposed by this version, preserve the correct
    # source by using its cache-hit signal when available; latency is measured server-side.
    source = "LLM_CACHE" if cache_hit else "LIVE_INFERENCE"
    metadata = ChatMetadata(
        resolution_source=source,
        model=DEFAULT_MODEL,
        latency_ms=elapsed,
        input_tokens=token_count(response, "prompt_tokens"),
        output_tokens=token_count(response, "completion_tokens"),
        key_id=None if cache_hit else key_id,
        fallback_attempts=0 if cache_hit else fallback_attempts,
    )

    timestamp = now_iso()
    with connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO sessions(session_id, system_prompt, created_at) VALUES(?,?,?)",
            (payload.session_id, system_prompt, timestamp),
        )
        conn.execute(
            "INSERT INTO messages(session_id, role, content, metadata, created_at) VALUES(?,?,?,?,?)",
            (payload.session_id, "user", payload.message, None, timestamp),
        )
        conn.execute(
            "INSERT INTO messages(session_id, role, content, metadata, created_at) VALUES(?,?,?,?,?)",
            (payload.session_id, "assistant", reply, metadata.model_dump_json(), now_iso()),
        )
    return ChatResponse(session_id=payload.session_id, reply=reply, metadata=metadata)


@app.get("/sessions/{session_id}/messages")
def get_messages(session_id: str) -> dict[str, Any]:
    with connect() as conn:
        session = conn.execute("SELECT session_id FROM sessions WHERE session_id=?", (session_id,)).fetchone()
        if session is None:
            raise HTTPException(status_code=404, detail="session not found")
        rows = conn.execute(
            "SELECT role, content, metadata FROM messages WHERE session_id=? ORDER BY id", (session_id,)
        ).fetchall()
    messages: list[dict[str, Any]] = []
    for row in rows:
        item: dict[str, Any] = {"role": row["role"], "content": row["content"]}
        if row["metadata"]:
            item["metadata"] = json.loads(row["metadata"])
        messages.append(item)
    return {"session_id": session_id, "messages": messages}
