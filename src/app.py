"""Web app: a small FastAPI server around the copilot.

Run locally (from the repo folder):
    uv run uvicorn app:app --app-dir src --port 8000
Then open http://localhost:8000
"""
import os
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from copilot import Copilot

# Protect your OpenAI credit from strangers: limits per visitor and per day
PER_IP_PER_HOUR = int(os.getenv("PER_IP_PER_HOUR", "10"))
MAX_PER_DAY = int(os.getenv("MAX_PER_DAY", "300"))
WEB_DIR = Path(__file__).resolve().parent.parent / "web"

state = {}
model_lock = threading.Lock()          # one question at a time through the models (saves RAM)
ip_history = defaultdict(deque)        # ip -> timestamps of recent questions
day_counter = {"day": None, "count": 0}


@asynccontextmanager
async def lifespan(app):
    state["copilot"] = Copilot()       # load the models ONCE at startup, not per question
    yield


app = FastAPI(title="Bilingual RAG Copilot (EU AI Act + GDPR)", lifespan=lifespan)


class Question(BaseModel):
    question: str = Field(min_length=3, max_length=500)


def check_limits(ip):
    now = time.time()
    today = time.strftime("%Y-%m-%d")
    if day_counter["day"] != today:
        day_counter.update(day=today, count=0)
    if day_counter["count"] >= MAX_PER_DAY:
        raise HTTPException(429, "Daily demo limit reached - please try again tomorrow.")
    history = ip_history[ip]
    while history and now - history[0] > 3600:
        history.popleft()
    if len(history) >= PER_IP_PER_HOUR:
        raise HTTPException(429, f"Limit of {PER_IP_PER_HOUR} questions per hour reached.")
    history.append(now)
    day_counter["count"] += 1


@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/health")
def health():
    return {"status": "ok", "models_loaded": "copilot" in state}


@app.post("/ask")
def ask(q: Question, request: Request):
    # behind a proxy (e.g. Hugging Face) the real visitor IP is in X-Forwarded-For
    ip = request.headers.get("x-forwarded-for", request.client.host).split(",")[0].strip()
    check_limits(ip)
    with model_lock:
        result = state["copilot"].answer(q.question)
    return {k: result[k] for k in
            ["question", "lang", "answerable", "answer", "citations", "sources", "latency_s"]}
