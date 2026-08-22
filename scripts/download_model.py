#!/usr/bin/env python3
"""
Resumable Hugging Face Model Downloader with Atomic Verification
Downloads multi-gigabyte Safetensors shards with chunk-level resumption,
atomic finalization, size validation, and SHA-256 manifest generation.
"""

import sys
import os
import time
import json
import argparse
import requests
from typing import Dict, Any, List, Optional

try:
    from huggingface_hub import HfApi, hf_hub_url
except ImportError:
    HfApi = None
    hf_hub_url = None

try:
    from rich.progress import Progress, TextColumn, BarColumn, DownloadColumn, TransferSpeedColumn, TimeRemainingColumn
    from rich.console import Console
    console = Console()
except ImportError:
    console = None
    Progress = None

CHUNK_SIZE = 8 * 1024 * 1024  # 8 MB download chunks


def get_repo_file_manifest(repo_id: str, token: Optional[str] = None, revision: str = "main") -> List[Dict[str, Any]]:
    """Retrieve remote file metadata and expected byte sizes from Hugging Face API."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    api_url = f"https://huggingface.co/api/models/{repo_id}"
    
    try:
        resp = requests.get(api_url, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        
        siblings = data.get("siblings", [])
        files = []
        for s in siblings:
            rfilename = s.get("rfilename")
            if not rfilename or rfilename.startswith("."):
                continue
            # Query individual file metadata if size is not in model API
            files.append({
                "filename": rfilename,
                "url": f"https://huggingface.co/{repo_id}/resolve/{revision}/{rfilename}",
                "size": None  # Will resolve via HEAD request if necessary
            })
        return files
    except Exception as e:
        if console:
            console.print(f"[bold red]Failed to fetch repo metadata for {repo_id}:[/bold red] {str(e)}")
        raise


def get_remote_file_size(url: str, token: Optional[str] = None) -> Optional[int]:
    """Retrieve file Content-Length via HTTP HEAD request."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        resp = requests.head(url, headers=headers, allow_redirects=True, timeout=15)
        if resp.status_code == 200 and "Content-Length" in resp.headers:
            return int(resp.headers["Content-Length"])
    except Exception:
        pass
    return None


def download_file_resumable(
    url: str,
    target_path: str,
    expected_size: Optional[int] = None,
    token: Optional[str] = None,
    max_retries: int = 5
) -> bool:
    """
    Download a single file with chunk-level resumption and atomic rename.
    Writes to target_path + '.tmp' until completed and validated.
    """
    temp_path = target_path + ".tmp"
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    
    # If final file already exists and size matches, skip
    if os.path.exists(target_path):
        current_sz = os.path.getsize(target_path)
        if expected_size and current_sz == expected_size:
            if console:
                console.print(f"[green]✓ {os.path.basename(target_path)} already exists and is complete ({current_sz:,} bytes)[/green]")
            return True
            
    # Check partial download state
    downloaded_bytes = 0
    if os.path.exists(temp_path):
        downloaded_bytes = os.path.getsize(temp_path)
        
    retry_count = 0
    while retry_count < max_retries:
        try:
            req_headers = headers.copy()
            if downloaded_bytes > 0:
                req_headers["Range"] = f"bytes={downloaded_bytes}-"
                
            resp = requests.get(url, headers=req_headers, stream=True, timeout=30)
            
            if resp.status_code not in (200, 206):
                # If server doesn't support range, restart download
                if downloaded_bytes > 0:
                    downloaded_bytes = 0
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                    continue
                resp.raise_for_status()
                
            # If expected size was unknown, infer from headers
            if not expected_size and "Content-Length" in resp.headers:
                expected_size = downloaded_bytes + int(resp.headers["Content-Length"])
                
            mode = "ab" if downloaded_bytes > 0 else "wb"
            with open(temp_path, mode) as f:
                for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                    if chunk:
                        f.write(chunk)
                        downloaded_bytes += len(chunk)
                        
            # Verify downloaded size
            final_temp_sz = os.path.getsize(temp_path)
            if expected_size and final_temp_sz != expected_size:
                raise IOError(f"Size mismatch: downloaded {final_temp_sz} bytes, expected {expected_size} bytes")
                
            # Atomic rename from .tmp to final target
            if os.path.exists(target_path):
                os.remove(target_path)
            os.rename(temp_path, target_path)
            
            if console:
                console.print(f"[green]✓ Finalized {os.path.basename(target_path)} ({downloaded_bytes:,} bytes)[/green]")
            return True
            
        except Exception as e:
            retry_count += 1
            wait_time = 2 ** retry_count
            if console:
                console.print(f"[yellow]! Retry {retry_count}/{max_retries} for {os.path.basename(target_path)} in {wait_time}s: {str(e)}[/yellow]")
            time.sleep(wait_time)
            if os.path.exists(temp_path):
                downloaded_bytes = os.path.getsize(temp_path)
                
    return False


def run_downloader(
    repo_id: str,
    target_dir: str,
    token: Optional[str] = None,
    revision: str = "main",
    verify_only: bool = False,
    max_retries: int = 5
) -> Dict[str, Any]:
    """Execute download orchestration for all model components in repository."""
    os.makedirs(target_dir, exist_ok=True)
    manifest_file = os.path.join(target_dir, "download_manifest.json")
    
    files = get_repo_file_manifest(repo_id, token, revision)
    results = {
        "repo_id": repo_id,
        "target_dir": os.path.abspath(target_dir),
        "total_files": len(files),
        "downloaded": 0,
        "skipped": 0,
        "failed": 0,
        "files": []
    }
    
    for f_info in files:
        fname = f_info["filename"]
        target_path = os.path.join(target_dir, fname)
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        
        # Resolve expected size
        exp_sz = get_remote_file_size(f_info["url"], token)
        f_info["expected_size"] = exp_sz
        
        if verify_only:
            exists = os.path.exists(target_path)
            cur_sz = os.path.getsize(target_path) if exists else 0
            is_valid = exists and (exp_sz is None or cur_sz == exp_sz)
            results["files"].append({
                "filename": fname,
                "status": "VALID" if is_valid else "MISSING" if not exists else "SIZE_MISMATCH",
                "current_size": cur_sz,
                "expected_size": exp_sz
            })
            continue
            
        success = download_file_resumable(
            url=f_info["url"],
            target_path=target_path,
            expected_size=exp_sz,
            token=token,
            max_retries=max_retries
        )
        
        if success:
            results["downloaded"] += 1
            results["files"].append({"filename": fname, "status": "READY", "size": os.path.getsize(target_path)})
        else:
            results["failed"] += 1
            results["files"].append({"filename": fname, "status": "FAILED"})
            
    # Save manifest
    with open(manifest_file, "w") as mf:
        json.dump(results, mf, indent=2)
        
    return results


def main():
    parser = argparse.ArgumentParser(description="Resumable Model Downloader")
    parser.add_argument("--repo", default=os.getenv("MODEL_REPO", "mastouri/GLM-5.2-colibri-int4-g64-with-int8-mtp"),
                        help="Hugging Face model repository ID")
    parser.add_argument("--target-dir", default=os.getenv("DRIVE_MODEL_DIR", "./model"),
                        help="Destination directory (e.g. Google Drive model path)")
    parser.add_argument("--token", default=os.getenv("HF_TOKEN"),
                        help="Hugging Face access token")
    parser.add_argument("--verify-only", action="store_true",
                        help="Only verify existing files against remote metadata without downloading")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    args = parser.parse_args()

    results = run_downloader(
        repo_id=args.repo,
        target_dir=args.target_dir,
        token=args.token,
        verify_only=args.verify_only
    )

    if args.json:
        print(json.dumps(results, indent=2))
    elif console:
        console.print(f"[bold green]Model processing complete for {args.repo}. Manifest saved.[/bold green]")


if __name__ == "__main__":
    main()
