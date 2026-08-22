#!/usr/bin/env python3
"""
Colibrì End-to-End Reusable Runtime Launcher
Performs automated pre-flight validation (environment, storage, model, engine)
and starts the Colibrì inference engine and REST API gateway.
"""

import sys
import os
import time
import json
import argparse
import subprocess
from typing import Dict, Any, List, Tuple, Optional

from environment_check import run_full_diagnostic
from drive_check import check_drive_storage
from model_verify import verify_model_directory


def execute_preflight_checks(
    model_dir: str,
    drive_dir: str,
    skip_drive: bool = False
) -> Tuple[bool, List[str]]:
    """Run all mandatory validation checks before runtime process launch."""
    failures = []
    
    print("[1/4] Running Environment & Toolchain Diagnostics...")
    env_rep = run_full_diagnostic()
    if not env_rep["memory"].get("can_host_dense_core", True):
        print("  ! Warning: Available RAM is below 9.9 GB. Colibri may experience memory pressure.")
        
    if not skip_drive:
        print(f"[2/4] Validating Persistent Storage in {drive_dir}...")
        drive_rep = check_drive_storage(drive_dir, required_free_gb=10.0)
        if not drive_rep["exists"]:
            failures.append(f"Drive directory {drive_dir} does not exist")
        elif not drive_rep["is_writable"]:
            failures.append(f"Drive directory {drive_dir} is not writable")
    else:
        print("[2/4] Skipping Drive validation (--skip-drive specified)")
        
    print(f"[3/4] Validating Model Integrity in {model_dir}...")
    model_rep = verify_model_directory(model_dir, min_expected_shards=1 if "mock" in model_dir else 38)
    if model_rep["status"] not in ("READY", "COMPLETE"):
        failures.append(f"Model validation failed with status {model_rep['status']}: {model_rep.get('missing_files')}")
        
    return len(failures) == 0, failures


def launch_runtime_server(
    host: str = "127.0.0.1",
    port: int = 8000,
    model_dir: str = "/content/model",
    api_key: Optional[str] = None
):
    """Start the FastAPI OpenAI-compatible server."""
    print(f"[4/4] Starting OpenAI-Compatible API Gateway on http://{host}:{port}...")
    os.environ["COLI_HOST"] = host
    os.environ["COLI_PORT"] = str(port)
    os.environ["MODEL_DIR"] = model_dir
    if api_key:
        os.environ["COLI_API_KEY"] = api_key
        
    api_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "api", "app.py")
    subprocess.run([sys.executable, api_script])


def main():
    parser = argparse.ArgumentParser(description="Colibri Runtime Launcher")
    parser.add_argument("--model-dir", default=os.getenv("MODEL_DIR", "./model"))
    parser.add_argument("--drive-dir", default=os.getenv("DRIVE_MODEL_DIR", "./mock_drive"))
    parser.add_argument("--host", default=os.getenv("COLI_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("COLI_PORT", "8000")))
    parser.add_argument("--api-key", default=os.getenv("COLI_API_KEY"))
    parser.add_argument("--skip-drive", action="store_true", help="Skip Google Drive storage check")
    parser.add_argument("--preflight-only", action="store_true", help="Run validation without launching server")
    args = parser.parse_args()

    success, errors = execute_preflight_checks(
        model_dir=args.model_dir,
        drive_dir=args.drive_dir,
        skip_drive=args.skip_drive
    )

    if not success:
        print("\n[bold red]Pre-Flight Validation Failed:[/bold red]")
        for err in errors:
            print(f"  [FAIL] {err}")
        sys.exit(1)

    print("\n[OK] All pre-flight checks passed successfully.")
    if args.preflight_only:
        sys.exit(0)

    launch_runtime_server(
        host=args.host,
        port=args.port,
        model_dir=args.model_dir,
        api_key=args.api_key
    )


if __name__ == "__main__":
    main()
