"""
Unit and integration tests for OpenAI-compatible REST API endpoints and SSE streaming.
"""

import os
import sys
import pytest
from fastapi.testclient import TestClient

# Set test environment
os.environ["COLI_API_KEY"] = "test_secret_key_123"
os.environ["COLI_MODEL_ID"] = "glm-5.2-744b-moe-int4"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))
import app as api_module
from app import app


@pytest.fixture
def client():
    # Update app global state for testing
    api_module.API_KEY = "test_secret_key_123"
    return TestClient(app)


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["engine"] == "colibri"
    assert data["model_id"] == "glm-5.2-744b-moe-int4"
    assert data["resident_ram_gb"] == 9.9


def test_models_endpoint_unauthorized(client):
    response = client.get("/v1/models")
    assert response.status_code == 401
    assert "Missing Authorization header" in response.text


def test_models_endpoint_authorized(client):
    headers = {"Authorization": "Bearer test_secret_key_123"}
    response = client.get("/v1/models", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["object"] == "list"
    assert len(data["data"]) == 1
    assert data["data"][0]["id"] == "glm-5.2-744b-moe-int4"


def test_chat_completions_buffered(client):
    headers = {"Authorization": "Bearer test_secret_key_123"}
    payload = {
        "model": "glm-5.2-744b-moe-int4",
        "messages": [
            {"role": "user", "content": "Explain recursion in simple terms."}
        ],
        "temperature": 0.7,
        "stream": False
    }
    response = client.post("/v1/chat/completions", headers=headers, json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["object"] == "chat.completion"
    assert data["model"] == "glm-5.2-744b-moe-int4"
    assert len(data["choices"]) == 1
    assert data["choices"][0]["message"]["role"] == "assistant"
    assert "Colibrì GLM-5.2 inference response" in data["choices"][0]["message"]["content"]


def test_chat_completions_streaming(client):
    headers = {"Authorization": "Bearer test_secret_key_123"}
    payload = {
        "model": "glm-5.2-744b-moe-int4",
        "messages": [
            {"role": "user", "content": "Write a hello world function."}
        ],
        "stream": True
    }
    response = client.post("/v1/chat/completions", headers=headers, json=payload)
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    
    stream_content = response.text
    assert "data: " in stream_content
    assert "data: [DONE]" in stream_content
