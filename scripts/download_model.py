#!/usr/bin/env python3
"""
Resumable Hugging Face Model Downloader with Atomic Verification
Downloads multi-gigabyte Safetensors shards with prioritized sequencing,
chunk-level resumption, atomic finalization, size validation, and manifest generation.

Priority Ordering:
1. config.json
2. generation_config.json
3. tokenizer_config.json
4. tokenizer.json
5. out-mtp-00000.safetensors (MTP Speculative Head)
6. out-00000.safetensors (Dense Embedding & Layer 0)
7. Remaining MoE expert shards in numerical order (out-00001 ... out-00140)
"""

import sys
import os
import time
import json
import shutil
import argparse
import requests
from typing import Dict, Any, List, Optional, Tuple

try:
    from huggingface_hub import HfApi, hf_hub_url  # type: ignore
except ImportError:
    HfApi = None
    hf_hub_url = None

try:
    from rich.progress import (  # type: ignore
        Progress,
        TextColumn,
        BarColumn,
        DownloadColumn,
        TransferSpeedColumn,
        TimeRemainingColumn,
        TaskID
    )
    from rich.console import Console  # type: ignore
    console = Console()
except ImportError:
    console = None
    Progress = None

CHUNK_SIZE = 8 * 1024 * 1024  # 8 MB streaming chunks


def get_file_priority_key(filename: str) -> Tuple[int, str]:
    """Determine prioritized download sequence for GLM-5.2 artifacts."""
    base = os.path.basename(filename)
    if base == "config.json":
        return (0, base)
    elif base == "generation_config.json":
        return (1, base)
    elif base == "tokenizer_config.json":
        return (2, base)
    elif base == "tokenizer.json":
        return (3, base)
    elif base == "out-mtp-00000.safetensors":
        return (4, base)
    elif base == "out-00000.safetensors":
        return (5, base)
    elif base.startswith("out-") and base.endswith(".safetensors"):
        return (6, base)
    else:
        return (7, base)


def get_repo_file_manifest(repo_id: str, token: Optional[str] = None, revision: str = "main") -> List[Dict[str, Any]]:
    """Retrieve complete file tree metadata and exact byte sizes from Hugging Face API."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    tree_url = f"https://huggingface.co/api/models/{repo_id}/tree/{revision}"
    
    try:
        resp = requests.get(tree_url, headers=headers, timeout=30)
        if resp.status_code == 200:
            tree_data = resp.json()
            files = []
            for item in tree_data:
                path = item.get("path")
                if not path or path.startswith(".") or item.get("type") != "file":
                    continue
                files.append({
                    "filename": path,
                    "url": f"https://huggingface.co/{repo_id}/resolve/{revision}/{path}",
                    "size": item.get("size")
                })
            # Sort according to priority download order
            files.sort(key=lambda x: get_file_priority_key(x["filename"]))
            return files
    except Exception:
        pass

    # Fallback to model info API
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
            files.append({
                "filename": rfilename,
                "url": f"https://huggingface.co/{repo_id}/resolve/{revision}/{rfilename}",
                "size": None
            })
        files.sort(key=lambda x: get_file_priority_key(x["filename"]))
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
    max_retries: int = 5,
    progress: Optional[Any] = None,
    task_id: Optional[Any] = None
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
            if console and not progress:
                console.print(f"[green][OK] {os.path.basename(target_path)} already exists and is complete ({current_sz:,} bytes)[/green]")
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
                        if progress and task_id is not None:
                            progress.update(task_id, advance=len(chunk))
                        
            # Verify downloaded size
            final_temp_sz = os.path.getsize(temp_path)
            if expected_size and final_temp_sz != expected_size:
                raise IOError(f"Size mismatch: downloaded {final_temp_sz} bytes, expected {expected_size} bytes")
                
            # Atomic rename from .tmp to final target
            if os.path.exists(target_path):
                os.remove(target_path)
            os.rename(temp_path, target_path)
            
            if console and not progress:
                console.print(f"[green][OK] Finalized {os.path.basename(target_path)} ({downloaded_bytes:,} bytes)[/green]")
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
    max_retries: int = 5,
    min_free_gib: float = 400.0
) -> Dict[str, Any]:
    """Execute prioritized download orchestration for all model components in repository."""
    os.makedirs(target_dir, exist_ok=True)
    manifest_file = os.path.join(target_dir, "download_manifest.json")
    
    files = get_repo_file_manifest(repo_id, token, revision)
    
    # Pre-download storage capacity check
    if not verify_only:
        try:
            _, _, free_bytes = shutil.disk_usage(target_dir)
            free_gib = free_bytes / (1024 ** 3)
            if free_gib < min_free_gib and console:
                console.print(f"[bold red]! Capacity Gate Alert: Free space ({free_gib:.2f} GiB) is below required ({min_free_gib:.2f} GiB)[/bold red]")
        except Exception:
            pass

    total_bytes = sum(f.get("size") or 0 for f in files)
    
    results = {
        "repo_id": repo_id,
        "target_dir": os.path.abspath(target_dir),
        "total_files": len(files),
        "total_bytes": total_bytes,
        "total_gib": round(total_bytes / (1024 ** 3), 2),
        "downloaded": 0,
        "skipped": 0,
        "failed": 0,
        "start_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "files": []
    }
    
    if console:
        console.print(f"\n[bold cyan]Starting prioritized download for {repo_id} ({len(files)} files, {results['total_gib']} GiB)[/bold cyan]")
        console.print(f"Target Directory: [yellow]{target_dir}[/yellow]\n")

    for idx, f_info in enumerate(files, 1):
        fname = f_info["filename"]
        target_path = os.path.join(target_dir, fname)
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        
        # Resolve expected size if not pre-populated
        exp_sz = f_info.get("size")
        if exp_sz is None:
            exp_sz = get_remote_file_size(f_info["url"], token)
            f_info["size"] = exp_sz
            
        exists = os.path.exists(target_path)
        cur_sz = os.path.getsize(target_path) if exists else 0
        is_valid = exists and (exp_sz is None or cur_sz == exp_sz)

        if is_valid:
            results["skipped"] += 1
            results["files"].append({
                "filename": fname,
                "status": "READY",
                "size": cur_sz,
                "verified": True
            })
            if console:
                console.print(f"[{idx}/{len(files)}] [green][OK] (Skipped existing) {fname} ({cur_sz:,} B)[/green]")
            continue

        if verify_only:
            results["files"].append({
                "filename": fname,
                "status": "MISSING" if not exists else "SIZE_MISMATCH",
                "current_size": cur_sz,
                "expected_size": exp_sz
            })
            if console:
                console.print(f"[{idx}/{len(files)}] [red][MISSING] {fname}[/red]")
            continue
            
        if console:
            console.print(f"[{idx}/{len(files)}] [bold yellow]Downloading {fname}...[/bold yellow] (Expected: {exp_sz:,} B)")

        start_t = time.perf_counter()
        success = download_file_resumable(
            url=f_info["url"],
            target_path=target_path,
            expected_size=exp_sz,
            token=token,
            max_retries=max_retries
        )
        elapsed = time.perf_counter() - start_t
        
        if success:
            final_sz = os.path.getsize(target_path)
            speed_mb = (final_sz / (1024 * 1024)) / max(elapsed, 0.001)
            results["downloaded"] += 1
            results["files"].append({"filename": fname, "status": "READY", "size": final_sz})
            if console:
                console.print(f"[{idx}/{len(files)}] [bold green][OK] Completed {fname} ({final_sz:,} B in {elapsed:.1f}s @ {speed_mb:.1f} MB/s)[/bold green]")
        else:
            results["failed"] += 1
            results["files"].append({"filename": fname, "status": "FAILED"})
            if console:
                console.print(f"[{idx}/{len(files)}] [bold red][FAIL] Failed to download {fname}[/bold red]")
            
    results["end_time"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    results["all_files_ready"] = (results["failed"] == 0 and (results["downloaded"] + results["skipped"]) == len(files))

    # Save manifest
    with open(manifest_file, "w") as mf:
        json.dump(results, mf, indent=2)
        
    return results


def main():
    parser = argparse.ArgumentParser(description="Prioritized Resumable Model Downloader")
    parser.add_argument("--repo", default=os.getenv("MODEL_REPO", "mastouri/GLM-5.2-colibri-int4-g64-with-int8-mtp"),
                        help="Hugging Face model repository ID")
    parser.add_argument("--target-dir", default=os.getenv("DRIVE_MODEL_DIR", "/content/drive/MyDrive/AI - Google Drive/GLM-5.2/model"),
                        help="Destination directory (e.g. Google Drive model path)")
    parser.add_argument("--token", default=os.getenv("HF_TOKEN"),
                        help="Hugging Face access token")
    parser.add_argument("--verify-only", action="store_true",
                        help="Only verify existing files against remote metadata without downloading")
    parser.add_argument("--min-free-gb", type=float, default=400.0,
                        help="Minimum required free storage in GB before downloading")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    args = parser.parse_args()

    results = run_downloader(
        repo_id=args.repo,
        target_dir=args.target_dir,
        token=args.token,
        verify_only=args.verify_only,
        min_free_gib=args.min_free_gb
    )

    if args.json:
        print(json.dumps(results, indent=2))
    elif console:
        status_color = "green" if results.get("all_files_ready") else "yellow"
        console.print(f"\n[{status_color}]Model processing finished for {args.repo}. Manifest saved at {os.path.join(args.target_dir, 'download_manifest.json')}[/{status_color}]")

    sys.exit(0 if results.get("all_files_ready") else 1)


if __name__ == "__main__":
    main()
