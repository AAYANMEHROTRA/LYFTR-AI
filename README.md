# LYFTR AI — LLM Chatbot with Key Failover and Response Caching

A full-stack chatbot built with React, FastAPI, SQLite and LiteLLM. It stores multi-turn conversations, uses LiteLLM's local response cache, tracks per-request token usage, and tries the next configured provider key when a request fails.

## 1. Live URLs

- Frontend: **ADD YOUR DEPLOYED FRONTEND URL**
- Backend: **ADD YOUR DEPLOYED BACKEND URL**
- Health: `ADD_BACKEND_URL/health`
- GitHub: **ADD YOUR PUBLIC REPOSITORY URL**

## 2. Run locally: with Docker and without

### Docker (recommended)

1. Copy `.env.example` to `.env`.
2. Put two Gemini API keys in `LLM_API_KEYS`, separated by a comma. Do not add spaces or quotes around the keys.
3. Keep `ENABLE_FAILURE_SIMULATION=true` for the required demo.
4. Run `make up` (or `docker compose up --build -d`).
5. Open <http://localhost:3000>. API docs: <http://localhost:8000/docs>.
6. Stop with `make down`.

The SQLite database is stored in the named Docker volume mounted at `/data` and survives container recreation.

### Without Docker

Backend (Python 3.13 recommended):

```bash
cd backend
python -m venv .venv
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

Set the environment variables from the root `.env` file in your shell, then run:

```bash
uvicorn app.main:app --reload --port 8000
```

Frontend in a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Set `VITE_API_BASE_URL=http://localhost:8000` in the frontend environment when running outside Docker.

## 3. Design decisions: key fallback, caching, SQLite session storage

- **Key fallback:** `LLM_API_KEYS` is parsed in order into `key_1`, `key_2`, etc. Each request attempts keys sequentially. Rate-limit, quota, provider and server failures advance to the next key. The API returns only the key identifier, never the secret.
- **Failure demonstration:** when `ENABLE_FAILURE_SIMULATION=true`, `X-Simulate-Failure` can simulate 429/500/502/503 failures for selected keys without calling those providers. `key_1=429` should use key 2; `*=429` should produce a clean 503.
- **Caching:** LiteLLM's built-in in-memory cache is enabled. Cache inputs include the selected model and complete message list (system prompt, saved history and new user message). Cache is in-memory, so it is cleared when the backend process restarts.
- **SQLite:** sessions and messages are persisted in SQLite. The database schema is created on startup. Each successful request stores a user row and an assistant row with JSON metadata.
- **Session context:** the frontend creates a new session ID on page load and sends only the latest user message. The backend reconstructs the full context from SQLite.

## 4. Verification: how to see failover, cache hits and per-message token usage

Use Swagger at `/docs` or curl. Replace the URL as needed.

```bash
# Health
curl http://localhost:8000/health

# First request — expect LIVE_INFERENCE
curl -X POST http://localhost:8000/chat -H 'Content-Type: application/json' \
  -d '{"session_id":"cache-demo-1","message":"Explain caching in one sentence."}'

# Repeat the same first message in a NEW session — expect LLM_CACHE
curl -X POST http://localhost:8000/chat -H 'Content-Type: application/json' \
  -d '{"session_id":"cache-demo-2","message":"Explain caching in one sentence."}'

# Fail over from key_1 to key_2 — expect HTTP 200 and key_id=key_2
curl -X POST http://localhost:8000/chat -H 'Content-Type: application/json' \
  -H 'X-Simulate-Failure: key_1=429' \
  -d '{"session_id":"failover-demo","message":"Say hello."}'

# All keys fail — expect HTTP 503 and no history write
curl -X POST http://localhost:8000/chat -H 'Content-Type: application/json' \
  -H 'X-Simulate-Failure: *=429' \
  -d '{"session_id":"all-fail-demo","message":"Say hello."}'

# Session history
curl http://localhost:8000/sessions/failover-demo/messages
```

Every assistant response includes its own `resolution_source`, `model`, `latency_ms`, `input_tokens`, `output_tokens`, `key_id`, and `fallback_attempts`. Tokens are per request, not conversation totals.

## 5. Setup Used

- Editor: Visual Studio Code
- AI tools: ChatGPT and Google Gemini API
- Runtime: Python 3.13, Node.js, Docker Compose

## 6. Bonus features (if any)

- Optional per-session system prompt field.
- Health indicator in the UI.
- Responsive dark interface and suggested prompts.
- Automated backend API tests.

## Security notes

- Never commit `.env` or expose API keys in screenshots, source code, browser code, or the public repository.
- Rotate any key that is accidentally exposed.
- The demo failure hook should be disabled after evaluation if the service is kept online.
