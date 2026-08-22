#!/usr/bin/env python3
"""
Colibrì Runtime & API Health Check Probe
Polls the REST API gateway health and model endpoints to verify operational readiness.
"""

import sys
import os
import time
import json
import argparse
import requests
from typing import Dict, Any, Optional

try:
    from rich.console import Console
    console = Console()
except ImportError:
    console = None


def probe_health_endpoint(host: str = "127.0.0.1", port: int = 8000, timeout: float = 5.0) -> Dict[str, Any]:
    """Check GET /health endpoint."""
    url = f"http://{host}:{port}/health"
    start = time.perf_counter()
    try:
        resp = requests.get(url, timeout=timeout)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        if resp.status_code == 200:
            return {"healthy": True, "status_code": 200, "latency_ms": duration_ms, "data": resp.json()}
        return {"healthy": False, "status_code": resp.status_code, "latency_ms": duration_ms, "error": resp.text}
    except Exception as e:
        return {"healthy": False, "status_code": 0, "latency_ms": 0.0, "error": str(e)}


def probe_models_endpoint(host: str = "127.0.0.1", port: int = 8000, api_key: Optional[str] = None, timeout: float = 5.0) -> Dict[str, Any]:
    """Check GET /v1/models endpoint with Bearer authentication."""
    url = f"http://{host}:{port}/v1/models"
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    start = time.perf_counter()
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        if resp.status_code == 200:
            return {"accessible": True, "status_code": 200, "latency_ms": duration_ms, "models": resp.json().get("data", [])}
        return {"accessible": False, "status_code": resp.status_code, "latency_ms": duration_ms, "error": resp.text}
    except Exception as e:
        return {"accessible": False, "status_code": 0, "latency_ms": 0.0, "error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="Colibri Runtime Health Probe")
    parser.add_argument("--host", default=os.getenv("COLI_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("COLI_PORT", "8000")))
    parser.add_argument("--api-key", default=os.getenv("COLI_API_KEY"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    health = probe_health_endpoint(args.host, args.port)
    models = probe_models_endpoint(args.host, args.port, args.api_key)

    is_ok = health["healthy"] and models["accessible"]
    combined = {
        "status": "HEALTHY" if is_ok else "UNHEALTHY",
        "health_probe": health,
        "models_probe": models
    }

    if args.json:
        print(json.dumps(combined, indent=2))
    elif console:
        if is_ok:
            console.print(f"[bold green]✓ Runtime is HEALTHY on {args.host}:{args.port} (Latency: {health['latency_ms']}ms)[/bold green]")
        else:
            console.print(f"[bold red]✗ Runtime probe FAILED on {args.host}:{args.port}[/bold red]")
            if not health["healthy"]:
                console.print(f"  - Health Error: {health.get('error')}")
            if not models["accessible"]:
                console.print(f"  - Models Error: {models.get('error')}")

    sys.exit(0 if is_ok else 1)


if __name__ == "__main__":
    main()
