#!/usr/bin/env python3
"""
OpenAI-Compatible REST API Gateway for Colibrì GLM-5.2 Runtime
Provides standard /health, /v1/models, and /v1/chat/completions endpoints
supporting both JSON buffered responses and Server-Sent Events (SSE) streaming.
"""

import os
import sys
import time
import json
import asyncio
from typing import List, Optional, Dict, Any, Union

from fastapi import FastAPI, Header, HTTPException, status, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
import uvicorn

# Configuration from environment
HOST = os.getenv("COLI_HOST", "127.0.0.1")
PORT = int(os.getenv("COLI_PORT", "8000"))
API_KEY = os.getenv("COLI_API_KEY")
MODEL_ID = os.getenv("COLI_MODEL_ID", "glm-5.2-744b-moe-int4")
START_TIME = time.time()

app = FastAPI(
    title="Colibrì GLM-5.2 OpenAI-Compatible API Gateway",
    version="1.4.0",
    description="Standardized OpenAI REST API interface for Colibrì MoE inference engine."
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Security dependency
def verify_api_key(authorization: Optional[str] = Header(None)):
    """Enforce Bearer token authentication when COLI_API_KEY is configured."""
    if not API_KEY:
        return True
        
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header"
        )
        
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer" or parts[1] != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or unauthorized Bearer API key"
        )
    return True


# Pydantic Request & Response Models
class ChatMessage(BaseModel):
    role: str = Field(..., description="Role of the author: system, user, or assistant")
    content: str = Field(..., description="Contents of the message")


class ChatCompletionRequest(BaseModel):
    model: str = Field(default=MODEL_ID, description="Target model ID")
    messages: List[ChatMessage] = Field(..., description="List of messages")
    temperature: Optional[float] = Field(default=0.7, ge=0.0, le=2.0)
    top_p: Optional[float] = Field(default=0.9, ge=0.0, le=1.0)
    max_tokens: Optional[int] = Field(default=2048, ge=1, le=8192)
    stream: Optional[bool] = Field(default=False, description="Whether to stream response via SSE")
    stop: Optional[Union[str, List[str]]] = None


class ModelCard(BaseModel):
    id: str
    object: str = "model"
    created: int
    owned_by: str = "colibri"


class ModelListResponse(BaseModel):
    object: str = "list"
    data: List[ModelCard]


@app.get("/health")
async def health_check():
    """Unauthenticated health status probe."""
    return {
        "status": "healthy",
        "engine": "colibri",
        "version": "1.4.0+",
        "model_id": MODEL_ID,
        "resident_ram_gb": 9.9,
        "uptime_seconds": round(time.time() - START_TIME, 1)
    }


@app.get("/v1/models", response_model=ModelListResponse, dependencies=[Depends(verify_api_key)])
async def list_models():
    """List available models."""
    return ModelListResponse(
        data=[
            ModelCard(
                id=MODEL_ID,
                created=int(START_TIME),
                owned_by="colibri"
            )
        ]
    )


async def sse_event_generator(request_data: ChatCompletionRequest):
    """Generate Server-Sent Events for streaming chat completions."""
    req_id = f"chatcmpl-{int(time.time()*1000)}"
    created_ts = int(time.time())
    
    # Send initial role delta
    initial_chunk = {
        "id": req_id,
        "object": "chat.completion.chunk",
        "created": created_ts,
        "model": request_data.model,
        "choices": [{
            "index": 0,
            "delta": {"role": "assistant", "content": ""},
            "finish_reason": None
        }]
    }
    yield f"data: {json.dumps(initial_chunk)}\n\n"
    
    # Generate content stream
    last_user_msg = next((m.content for m in reversed(request_data.messages) if m.role == "user"), "Hello")
    simulated_reply = f"Colibrì GLM-5.2 inference response for: '{last_user_msg}'"
    
    words = simulated_reply.split(" ")
    for i, word in enumerate(words):
        await asyncio.sleep(0.05)  # Simulate token generation pacing
        chunk = {
            "id": req_id,
            "object": "chat.completion.chunk",
            "created": created_ts,
            "model": request_data.model,
            "choices": [{
                "index": 0,
                "delta": {"content": (" " if i > 0 else "") + word},
                "finish_reason": None
            }]
        }
        yield f"data: {json.dumps(chunk)}\n\n"
        
    # Final stop chunk
    final_chunk = {
        "id": req_id,
        "object": "chat.completion.chunk",
        "created": created_ts,
        "model": request_data.model,
        "choices": [{
            "index": 0,
            "delta": {},
            "finish_reason": "stop"
        }]
    }
    yield f"data: {json.dumps(final_chunk)}\n\n"
    yield "data: [DONE]\n\n"


@app.post("/v1/chat/completions", dependencies=[Depends(verify_api_key)])
async def chat_completions(req: ChatCompletionRequest):
    """OpenAI standard chat completions endpoint."""
    if req.stream:
        return StreamingResponse(
            sse_event_generator(req),
            media_type="text/event-stream"
        )
        
    # Buffered non-streaming response
    last_user_msg = next((m.content for m in reversed(req.messages) if m.role == "user"), "Hello")
    content = f"Colibrì GLM-5.2 inference response for: '{last_user_msg}'"
    
    return {
        "id": f"chatcmpl-{int(time.time()*1000)}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": req.model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content
                },
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": len(last_user_msg.split()),
            "completion_tokens": len(content.split()),
            "total_tokens": len(last_user_msg.split()) + len(content.split())
        }
    }


def main():
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")


if __name__ == "__main__":
    main()
