# PICT InC 2026 — Event Chatbot

A lightweight FastAPI chatbot that answers questions about **PICT InC 2026** (Impetus, Concepts & Pradnya) using the Groq LLM API. The bot strictly uses `info.txt` as its knowledge source — no hallucination, no off-topic answers.

---

## Features

- **Groq LLM** (llama3-8b-8192) with low temperature for factual answers
- **Multi-key fallback** — provide multiple Groq API keys separated by commas; if one key fails, the next is tried automatically
- **In-memory rate limiting** — 10 requests/minute per IP
- **In-memory response caching** — duplicate questions skip the API call entirely
- **CORS enabled** — ready to embed in any frontend
- **Render-ready** — one-click deploy with `render.yaml`

---

## Local Setup

### 1. Clone the repository

```bash
git clone https://github.com/your-username/pictinc-chatbot.git
cd pictinc-chatbot
```

### 2. Create a virtual environment

```bash
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS / Linux
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Copy the example file and add your Groq API key(s):

```bash
cp .env.example .env
```

Edit `.env`:

```
GROQ_API_KEY=gsk_your_key_here
```

You can provide **multiple keys** separated by commas for automatic fallback:

```
GROQ_API_KEY=gsk_key_one,gsk_key_two,gsk_key_three
```

If the first key hits a rate limit or fails, the app tries the next one.

### 5. Run the server

```bash
uvicorn main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`.

---

## API Usage

### Health check

```bash
curl http://localhost:8000/health
```

Response:

```json
{ "status": "ok", "model": "llama3-8b-8192" }
```

### Ask a question

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "What are the dates for PICT InC 2026?"}'
```

Response:

```json
{ "answer": "PICT InC 2026 is scheduled for 27, 28, and 29 March 2026." }
```

---

## Deploy on Render

1. Push this repo to GitHub.
2. Go to [render.com](https://render.com) → **New** → **Web Service**.
3. Connect your GitHub repository.
4. Render auto-detects `render.yaml`. Confirm the settings.
5. Add the environment variable:
   - `GROQ_API_KEY` = your Groq API key(s)
6. Click **Deploy**.

> **Note:** Render free tier instances spin down after 15 minutes of inactivity. The first request after idle will take ~30–50 seconds (cold start). Subsequent requests are fast.

---

## Project Structure

```
├── main.py            ← All application logic
├── info.txt           ← Event knowledge base (edit this to update answers)
├── requirements.txt   ← Python dependencies
├── render.yaml        ← Render deployment config
├── .env.example       ← Environment variable template
└── README.md          ← You are here
```

---

## License

Built for PICT InC 2026 by the organizing team.
