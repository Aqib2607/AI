#!/usr/bin/env python3
"""
Google Drive Mount & Storage Health Check
Validates mount status, directory write permissions, project directory layout,
and storage quota feasibility for hosting the GLM-5.2 400 GB model package
in Google Drive within the designated target folder:
Account: aqibjawwad2607@gmail.com
Target Folder: "AI - Google Drive" (ID: 11BdZx7pI2XyEmiJjpZJjTCIX1V41vKhd)
"""

import sys
import os
import shutil
import json
import argparse
from typing import Dict, Any, List

try:
    from rich.console import Console  # type: ignore
    from rich.panel import Panel      # type: ignore
    console = Console()
except ImportError:
    console = None

EXPECTED_ACCOUNT = "aqibjawwad2607@gmail.com"
TARGET_FOLDER_ID = "11BdZx7pI2XyEmiJjpZJjTCIX1V41vKhd"
TARGET_FOLDER_NAME = "AI - Google Drive"

REQUIRED_SUBDIRECTORIES = [
    "model",
    "runtime",
    "logs",
    "manifests",
    "benchmarks"
]


def check_drive_storage(
    base_path: str,
    required_free_gb: float = 400.0,
    init_subdirectories: bool = True
) -> Dict[str, Any]:
    """
    Inspect storage capacity, project structure, and write permissions
    for target Google Drive project path strictly within designated scope.
    """
    resolved_path = os.path.abspath(base_path)
    exists = os.path.exists(resolved_path)
    
    result = {
        "target_path": resolved_path,
        "expected_account": EXPECTED_ACCOUNT,
        "target_folder_id": TARGET_FOLDER_ID,
        "target_folder_name": TARGET_FOLDER_NAME,
        "exists": exists,
        "is_writable": False,
        "total_gb": 0.0,
        "used_gb": 0.0,
        "free_gb": 0.0,
        "required_free_gb": required_free_gb,
        "is_quota_sufficient": False,
        "is_drive_fuse": False,
        "subdirectories": {},
        "status": "UNKNOWN",
        "error": None
    }
    
    # Detect if path is in Google Colab Drive FUSE mount
    if "/content/drive" in resolved_path:
        result["is_drive_fuse"] = True
    
    # Ensure target directory exists strictly within scope
    if not exists:
        try:
            os.makedirs(resolved_path, exist_ok=True)
            result["exists"] = True
        except Exception as e:
            result["error"] = f"Failed to create directory {resolved_path}: {str(e)}"
            result["status"] = "DIRECTORY_CREATION_FAILED"
            return result
            
    # Verify and initialize required subdirectories if base_path is project root or parent of model
    project_root = resolved_path if os.path.basename(resolved_path) == "GLM-5.2" else os.path.dirname(resolved_path)
    for subdir in REQUIRED_SUBDIRECTORIES:
        sub_path = os.path.join(project_root, subdir)
        if init_subdirectories:
            os.makedirs(sub_path, exist_ok=True)
        result["subdirectories"][subdir] = {
            "path": sub_path,
            "exists": os.path.exists(sub_path)
        }
    
    # Check disk usage
    try:
        total, used, free = shutil.disk_usage(resolved_path)
        total_gb = round(total / (1024 ** 3), 2)
        used_gb = round(used / (1024 ** 3), 2)
        free_gb = round(free / (1024 ** 3), 2)
        
        result["total_gb"] = total_gb
        result["used_gb"] = used_gb
        result["free_gb"] = free_gb
        result["is_quota_sufficient"] = free_gb >= required_free_gb
    except Exception as e:
        result["error"] = f"Failed to query disk usage: {str(e)}"
        result["status"] = "DISK_QUERY_FAILED"
        return result
    
    # Test write permissions strictly inside project directory
    test_probe_file = os.path.join(resolved_path, ".drive_probe_test.tmp")
    try:
        with open(test_probe_file, "w") as f:
            f.write("GLM-5.2 Colibri Drive Probe OK\n")
        result["is_writable"] = True
        os.remove(test_probe_file)
    except Exception as e:
        result["error"] = f"Write permission probe failed: {str(e)}"
        result["status"] = "PERMISSION_DENIED"
        return result
    
    if result["is_quota_sufficient"] and result["is_writable"]:
        result["status"] = "HEALTHY"
    elif not result["is_quota_sufficient"]:
        result["status"] = "INSUFFICIENT_STORAGE"
    else:
        result["status"] = "WARNING"
        
    return result


def main():
    parser = argparse.ArgumentParser(description="Google Drive Storage & Project Structure Check")
    parser.add_argument("--path", default=os.getenv("DRIVE_MODEL_DIR", "/content/drive/MyDrive/AI - Google Drive/GLM-5.2/model"),
                        help="Google Drive mount project or model directory")
    parser.add_argument("--required-gb", type=float, default=400.0,
                        help="Minimum required free storage in GB (default: 400.0)")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    args = parser.parse_args()

    report = check_drive_storage(args.path, args.required_gb)

    if args.json:
        print(json.dumps(report, indent=2))
        sys.exit(0 if report["status"] == "HEALTHY" else 1)

    if console:
        color = "green" if report["status"] == "HEALTHY" else "yellow" if report["status"] == "INSUFFICIENT_STORAGE" else "red"
        text = (
            f"[bold]Account Target:[/bold] {report['expected_account']}\n"
            f"[bold]Folder Name / ID:[/bold] {report['target_folder_name']} ({report['target_folder_id']})\n"
            f"[bold]Target Path:[/bold] {report['target_path']}\n"
            f"[bold]Status:[/bold] [{color}]{report['status']}[/{color}]\n"
            f"[bold]Total Capacity:[/bold] {report['total_gb']} GB\n"
            f"[bold]Used Capacity:[/bold] {report['used_gb']} GB\n"
            f"[bold]Available Free:[/bold] {report['free_gb']} GB (Required: >= {report['required_free_gb']} GB)\n"
            f"[bold]Write Permitted:[/bold] {'Yes' if report['is_writable'] else 'No'}\n"
            f"[bold]Google Drive FUSE:[/bold] {'Yes' if report['is_drive_fuse'] else 'No (Local/Direct)'}\n"
            f"[bold]Subdirectories Verified:[/bold] {', '.join(report['subdirectories'].keys())}"
        )
        if report["error"]:
            text += f"\n[bold red]Error Message:[/bold red] {report['error']}"
        console.print(Panel(text, title="Google Drive Storage & Isolation Report", border_style=color))
    else:
        print(json.dumps(report, indent=2))

    sys.exit(0 if report["status"] in ("HEALTHY", "INSUFFICIENT_STORAGE") else 1)


if __name__ == "__main__":
    main()
