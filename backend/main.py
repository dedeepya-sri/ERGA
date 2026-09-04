"""
FastAPI app entrypoint.

Run locally with:
    cd backend
    uvicorn main:app --reload --port 8000
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import assessments, reports, reviews, submissions
from config.settings import config
from database.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="ERGA — Explainable Rubric-Grounded Automated Grading",
    description=(
        "Rubric-grounded, evidence-based, confidence-aware, human-in-the-loop "
        "grading engine for descriptive exam answers."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# The Vite dev server defaults to :5173; adjust/add origins for other setups.
app.add_middleware(
    CORSMiddleware,
    # Vite defaults to :5173 but auto-increments (5174, 5175, ...) if that
    # port is taken, and a mismatch here fails EVERY request with an
    # opaque browser-console-only CORS error — not just the endpoint you
    # happened to be testing. Matching any localhost/127.0.0.1 port is
    # safe for a local dev/prototype tool with no auth system (Section 50)
    # and avoids that whole class of "nothing works and there's no visible
    # error" confusion.
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(assessments.router)
app.include_router(submissions.router)
app.include_router(reviews.router)
app.include_router(reports.router)


@app.get("/api/health")
def health() -> dict:
    """Reports which engines are actually active — never silently claim a different one is running."""
    return {
        "status": "ok",
        "embedding_engine": config.embedding.engine,
        "nli_engine": config.nli.engine,
        "ocr_engine": config.ocr.engine,
        "scoring_mode": config.scoring.mode,
    }
