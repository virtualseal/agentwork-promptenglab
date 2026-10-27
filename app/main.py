from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import logging

from writing.generator import generate_post

app = FastAPI(title="Revve Content Engine")


class GenerateRequest(BaseModel):
    topic: str = Field(min_length=5, max_length=500)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "application": "revve-content-engine"
    }


@app.post("/generate")
def generate(request: GenerateRequest):
    try:
        return generate_post(request.topic)
    except (RuntimeError, OSError, ValueError, KeyError, TypeError) as exc:
        logging.getLogger(__name__).warning(
            "Generation failed at provider boundary: %s", type(exc).__name__
        )
        raise HTTPException(
            status_code=502,
            detail="Claude generation unavailable. Check proxy access and application logs."
        )

