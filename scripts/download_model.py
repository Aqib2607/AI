#!/usr/bin/env python3
"""
Resumable Hugging Face Model Downloader with Atomic Verification
Downloads multi-gigabyte Safetensors shards with prioritized sequencing,
chunk-level resumption, atomic finalization, size validation, and manifest generation.

Capacity Semantics:
  - Persistent storage gate: authoritative Google Drive API v3 storageQuota.
    The FUSE mount at /content/drive is NOT the account quota.
  - Local disk gate: only checked for temporary chunk buffer (~3 GiB max per shard).
    The full 399.79 GiB model must NEVER be required on local Colab NVMe.
  - Target path: /content/drive/MyDrive/AI - Google Drive/GLM-5.2/model
    (backed by Google Drive, not local NVMe)

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

# Paths that indicate the target is a Google Drive FUSE mount, not local NVMe
DRIVE_MOUNT_PREFIXES = (
    "/content/drive/",
    "/gdrive/",
    "/mnt/drive/",
)


def is_drive_path(path: str) -> bool:
    """Return True if the path is a Google Drive FUSE mount path, not local NVMe.
    Uses raw string prefix matching to avoid platform-specific os.path.abspath
    mangling of Unix paths when running on Windows.
    """
    # Normalise to forward slashes; do NOT call abspath (breaks /content/* on Windows)
    normalized = path.replace("\\", "/")
    return any(normalized.startswith(p) for p in DRIVE_MOUNT_PREFIXES)


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
    Preserves existing completed files and resumes partial .tmp downloads.
    """
    temp_path = target_path + ".tmp"
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    
    # If final file already exists and size matches, skip (preserve valid files)
    if os.path.exists(target_path):
        current_sz = os.path.getsize(target_path)
        if expected_size and current_sz == expected_size:
            if console and not progress:
                console.print(f"[green][OK] {os.path.basename(target_path)} already exists and is complete ({current_sz:,} bytes)[/green]")
            return True
            
    # Check partial download state — resume from existing .tmp byte offset
    downloaded_bytes = 0
    if os.path.exists(temp_path):
        downloaded_bytes = os.path.getsize(temp_path)
        if console and not progress:
            console.print(f"[cyan]  Resuming {os.path.basename(target_path)} from byte {downloaded_bytes:,}[/cyan]")
        
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


def get_capacity_report(
    target_dir: str,
    drive_service=None,
    mock_about: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Build a structured capacity report with three independent sections:
      1. Google Drive API account quota (authoritative persistent storage).
      2. Colab local ephemeral NVMe capacity (temporary chunks only).
      3. FUSE mount diagnostic (informational only — never used as account quota).

    Returns a dict with all values and an overall gate_decision key.
    """
    # 1. Authoritative Google Drive API quota
    drive_quota = {
        "available": False,
        "free_gb": None,
        "limit_gb": None,
        "usage_gb": None,
        "is_unlimited": False,
        "email": None,
        "error": None
    }
    try:
        if mock_about is not None:
            about_data = mock_about
        elif drive_service is not None:
            about_data = drive_service.about().get(fields="storageQuota,user").execute()
        else:
            about_data = None

        if about_data:
            sq = about_data.get("storageQuota", {})
            user = about_data.get("user", {})
            raw_limit = sq.get("limit")
            raw_usage = sq.get("usage", "0")
            usage_bytes = int(raw_usage or 0)
            drive_quota["email"] = user.get("emailAddress")
            drive_quota["available"] = True
            if raw_limit is None:
                drive_quota["is_unlimited"] = True
                drive_quota["usage_gb"] = round(usage_bytes / 1e9, 2)
            else:
                limit_bytes = int(raw_limit)
                free_bytes = max(0, limit_bytes - usage_bytes)
                drive_quota["limit_gb"] = round(limit_bytes / 1e9, 2)
                drive_quota["usage_gb"] = round(usage_bytes / 1e9, 2)
                drive_quota["free_gb"] = round(free_bytes / 1e9, 2)
    except Exception as e:
        drive_quota["error"] = str(e)

    # 2. Colab local ephemeral NVMe (always /content, not the Drive FUSE mount)
    local_capacity = {"free_gib": None, "total_gib": None, "error": None}
    try:
        _, _, local_free = shutil.disk_usage("/content")
        _, local_total, _ = shutil.disk_usage("/content")
        local_capacity["free_gib"] = round(local_free / (1024 ** 3), 2)
        local_capacity["total_gib"] = round(local_total / (1024 ** 3), 2)
    except Exception:
        try:
            _, _, local_free = shutil.disk_usage(".")
            local_capacity["free_gib"] = round(local_free / (1024 ** 3), 2)
        except Exception as e:
            local_capacity["error"] = str(e)

    # 3. FUSE mount diagnostic (target_dir — informational only)
    fuse_diag = {"free_gib": None, "total_gib": None, "path": target_dir, "error": None}
    fuse_probe_path = target_dir
    while fuse_probe_path and not os.path.exists(fuse_probe_path):
        fuse_probe_path = os.path.dirname(fuse_probe_path)
    if fuse_probe_path and os.path.exists(fuse_probe_path):
        try:
            _, fuse_total, fuse_free = shutil.disk_usage(fuse_probe_path)
            fuse_diag["free_gib"] = round(fuse_free / (1024 ** 3), 2)
            fuse_diag["total_gib"] = round(fuse_total / (1024 ** 3), 2)
        except Exception as e:
            fuse_diag["error"] = str(e)

    return {
        "drive_api_quota": drive_quota,
        "local_colab_disk": local_capacity,
        "fuse_diagnostic": fuse_diag,
        "target_is_drive_path": is_drive_path(target_dir)
    }


def evaluate_download_gate(
    capacity: Dict[str, Any],
    required_gb: float = 400.0,
    recommended_gb: float = 450.0,
    local_temp_gib: float = 3.0
) -> Tuple[str, str]:
    """
    Evaluate download feasibility.

    Gate 1 (authoritative): Google Drive API free_gb >= required_gb.
    Gate 2 (local temp):     Only if target is NOT a Drive path —
                             local NVMe must have at least local_temp_gib for chunk buffer.
    FUSE capacity is NEVER used as a gate.

    Returns (status, reason).
    """
    dq = capacity.get("drive_api_quota", {})
    target_is_drive = capacity.get("target_is_drive_path", True)

    # Gate 1: Drive API quota
    if dq.get("is_unlimited"):
        drive_gate = "PASS"
        drive_reason = "Google Drive account has unlimited/unmetered quota."
    elif dq.get("free_gb") is not None:
        free_gb = dq["free_gb"]
        if free_gb >= recommended_gb:
            drive_gate = "PASS"
            drive_reason = f"Google Drive API: {free_gb:,.2f} GB free >= recommended {recommended_gb:.2f} GB threshold."
        elif free_gb >= required_gb:
            drive_gate = "PASS_LOW_MARGIN"
            drive_reason = f"Google Drive API: {free_gb:,.2f} GB free >= required {required_gb:.2f} GB (below recommended {recommended_gb:.2f} GB)."
        else:
            drive_gate = "FAIL"
            drive_reason = f"Google Drive API: {free_gb:,.2f} GB free is BELOW required {required_gb:.2f} GB. Download blocked."
    else:
        drive_gate = "UNKNOWN"
        drive_reason = "Google Drive API quota could not be determined. Authentication may be required."

    if drive_gate == "FAIL":
        return ("NO-GO", drive_reason)

    # Gate 2: Local temp buffer — only relevant when downloading to local disk
    if not target_is_drive:
        local = capacity.get("local_colab_disk", {})
        local_free = local.get("free_gib", 0.0) or 0.0
        if local_free < local_temp_gib:
            return ("NO-GO", f"Local Colab NVMe has only {local_free:.2f} GiB free (need {local_temp_gib:.2f} GiB temp buffer for non-Drive target).")

    # All gates passed
    if drive_gate == "PASS_LOW_MARGIN":
        return ("GO_WITH_LOW_MARGIN", drive_reason)
    return ("GO", drive_reason)


def run_downloader(
    repo_id: str,
    target_dir: str,
    token: Optional[str] = None,
    revision: str = "main",
    verify_only: bool = False,
    max_retries: int = 5,
    required_gb: float = 400.0,
    recommended_gb: float = 450.0,
    local_temp_gib: float = 3.0,
    drive_service=None,
    mock_capacity: Optional[Dict[str, Any]] = None,
    # Legacy parameter alias kept for backward compatibility
    min_free_gib: Optional[float] = None
) -> Dict[str, Any]:
    """
    Execute prioritized download orchestration for all model components.

    Capacity checks:
      - Authoritative gate: Google Drive API account quota (not FUSE).
      - Local temp gate: only applied when target is NOT a Drive mount path.
      - FUSE diagnostic: reported separately, never used as a gate.
    """
    os.makedirs(target_dir, exist_ok=True)
    manifest_file = os.path.join(target_dir, "download_manifest.json")

    files = get_repo_file_manifest(repo_id, token, revision)
    total_bytes = sum(f.get("size") or 0 for f in files)

    # Capacity report (three independent sections)
    if mock_capacity is not None:
        capacity = mock_capacity
    else:
        capacity = get_capacity_report(target_dir, drive_service=drive_service)

    gate_status, gate_reason = evaluate_download_gate(
        capacity,
        required_gb=required_gb,
        recommended_gb=recommended_gb,
        local_temp_gib=local_temp_gib
    )

    dq = capacity.get("drive_api_quota", {})
    local = capacity.get("local_colab_disk", {})
    fuse = capacity.get("fuse_diagnostic", {})
    target_is_drive = capacity.get("target_is_drive_path", True)

    if console:
        # Report three sections clearly
        console.print("\n[bold cyan]=== Storage Capacity Report ===[/bold cyan]")
        console.print(f"[bold]Target Directory:[/bold]         {target_dir}")
        console.print(f"[bold]Target Is Drive Mount:[/bold]    {target_is_drive}")
        console.print()
        console.print("[bold cyan]Google Drive Account Quota (Authoritative):[/bold cyan]")
        if dq.get("is_unlimited"):
            console.print("  Quota: Unlimited / Unmetered")
        elif dq.get("free_gb") is not None:
            console.print(f"  Total Plan:        {dq.get('limit_gb', 'N/A'):,} GB")
            console.print(f"  Used:              {dq.get('usage_gb', 'N/A'):,} GB")
            console.print(f"  [bold]Available Free:    {dq['free_gb']:,.2f} GB[/bold]")
        else:
            console.print(f"  Status: Unavailable ({dq.get('error', 'unknown')})")
        console.print(f"  Required:          >= {required_gb:.2f} GB")
        console.print(f"  Drive Gate:        [{'green' if 'GO' in gate_status else 'red'}]{gate_status}[/{'green' if 'GO' in gate_status else 'red'}]")
        console.print()
        console.print("[bold yellow]Colab Local Ephemeral NVMe (Temp Chunks Only):[/bold yellow]")
        console.print(f"  Local Free:        {local.get('free_gib', 'N/A')} GiB")
        console.print(f"  Local Total:       {local.get('total_gib', 'N/A')} GiB")
        console.print(f"  Required Temp:     {local_temp_gib:.2f} GiB (per-chunk buffer only)")
        console.print(f"  Full model staged locally: NO (model downloads directly to Drive)")
        console.print()
        console.print("[bold yellow]FUSE Mount Diagnostic (Informational Only — NOT account quota):[/bold yellow]")
        if fuse.get("free_gib") is not None:
            console.print(f"  FUSE Free:         {fuse['free_gib']:.2f} GiB  [Note: Colab FUSE virtual overlay, not Drive quota]")
            console.print(f"  FUSE Total:        {fuse['total_gib']:.2f} GiB")
        else:
            console.print("  FUSE: Not accessible")
        console.print()

    is_go = gate_status in ("GO", "GO_WITH_LOW_MARGIN")

    if not verify_only and not is_go:
        if console:
            console.print(f"[bold red]! Download Blocked: {gate_reason}[/bold red]")

    results = {
        "repo_id": repo_id,
        "target_dir": os.path.abspath(target_dir),
        "target_is_drive_path": target_is_drive,
        "total_files": len(files),
        "total_bytes": total_bytes,
        "total_gib": round(total_bytes / (1024 ** 3), 2),
        "capacity_gate_status": gate_status,
        "capacity_gate_reason": gate_reason,
        "drive_api_quota": dq,
        "local_colab_disk": local,
        "fuse_diagnostic_note": "FUSE values reflect Colab virtual container overlay, NOT Google Drive account quota.",
        "downloaded": 0,
        "skipped": 0,
        "failed": 0,
        "start_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "files": []
    }

    if not verify_only and not is_go:
        results["all_files_ready"] = False
        return results

    if console:
        console.print(f"[bold cyan]Starting prioritized download for {repo_id} ({len(files)} files, {results['total_gib']} GiB)[/bold cyan]")
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
            console.print(f"[{idx}/{len(files)}] [bold yellow]Downloading {fname}...[/bold yellow] (Expected: {exp_sz:,} B)" if exp_sz else f"[{idx}/{len(files)}] [bold yellow]Downloading {fname}...[/bold yellow]")

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
    parser.add_argument("--required-gb", type=float, default=400.0,
                        help="Minimum required Google Drive account quota in GB (default: 400.0)")
    parser.add_argument("--recommended-gb", type=float, default=450.0,
                        help="Recommended Google Drive account quota in GB (default: 450.0)")
    parser.add_argument("--local-temp-gib", type=float, default=3.0,
                        help="Minimum local NVMe temp buffer per chunk in GiB (default: 3.0, only applies to non-Drive targets)")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    # Legacy alias kept for backward compatibility
    parser.add_argument("--min-free-gb", type=float, default=None,
                        help="[Deprecated] Use --required-gb instead")
    args = parser.parse_args()

    # Honor legacy --min-free-gb if provided
    required_gb = args.required_gb
    if args.min_free_gb is not None:
        required_gb = args.min_free_gb

    results = run_downloader(
        repo_id=args.repo,
        target_dir=args.target_dir,
        token=args.token,
        verify_only=args.verify_only,
        required_gb=required_gb,
        recommended_gb=args.recommended_gb,
        local_temp_gib=args.local_temp_gib
    )

    if args.json:
        print(json.dumps(results, indent=2))
    elif console:
        status_color = "green" if results.get("all_files_ready") else "yellow"
        console.print(f"\n[{status_color}]Model processing finished for {args.repo}. Gate: {results.get('capacity_gate_status')}[/{status_color}]")

    sys.exit(0 if results.get("all_files_ready") else 1)


if __name__ == "__main__":
    main()
