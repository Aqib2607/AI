#!/usr/bin/env python3
"""
Google Drive API Quota & Storage Preflight Check
Authoritatively validates Google Drive storage quota using Google Drive API v3 (drive.about.get),
validates target folder ID & permissions, initializes GLM-5.2 subdirectories, and reports
virtual FUSE capacity purely as a secondary diagnostic metric.

Account: aqibjawwad2607@gmail.com
Target Folder: "AI - Google Drive" (ID: 11BdZx7pI2XyEmiJjpZJjTCIX1V41vKhd)
"""

import sys
import os
import shutil
import json
import argparse
from typing import Dict, Any, List, Optional, Tuple

try:
    from rich.console import Console  # type: ignore
    from rich.panel import Panel      # type: ignore
    from rich.table import Table      # type: ignore
    console = Console()
except ImportError:
    console = None

# Defaults and Pinned Identifiers
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


def get_google_drive_credentials():
    """
    Obtain authenticated Google credentials in Google Colab or local environment.
    Uses google.colab.auth in Colab, or standard google.auth credentials.
    """
    try:
        # Check if in Google Colab environment
        import importlib
        colab_auth = importlib.import_module("google" + ".colab.auth")
        colab_auth.authenticate_user()
    except Exception:
        pass

    try:
        import importlib
        gauth = importlib.import_module("google.auth")
        credentials, _ = gauth.default(scopes=["https://www.googleapis.com/auth/drive.readonly"])
        return credentials
    except Exception:
        return None


def get_drive_service(credentials=None):
    """Build and return a Google Drive API v3 resource client."""
    if credentials is None:
        credentials = get_google_drive_credentials()
    try:
        from googleapiclient.discovery import build  # type: ignore
        return build("drive", "v3", credentials=credentials)
    except Exception as e:
        return None


def get_drive_storage_quota(service=None, mock_response: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Retrieve authoritative Google Drive account storage quota via drive.about.get.
    Extracts limit, usage, usageInDrive, usageInDriveTrash, and computes free storage.
    Supports unlimited/null quota handling.
    """
    about_data = mock_response
    if about_data is None and service is not None:
        try:
            about_data = service.about().get(fields="storageQuota,user").execute()
        except Exception as e:
            return {
                "success": False,
                "error": f"Drive API query failed: {str(e)}",
                "email": None,
                "limit_bytes": None,
                "usage_bytes": None,
                "free_bytes": None,
                "limit_gb": None,
                "usage_gb": None,
                "free_gb": None,
                "limit_gib": None,
                "usage_gib": None,
                "free_gib": None,
                "is_unlimited": False
            }

    if about_data is None:
        return {
            "success": False,
            "error": "Google Drive API service or authentication not available",
            "email": None,
            "limit_bytes": None,
            "usage_bytes": None,
            "free_bytes": None,
            "limit_gb": None,
            "usage_gb": None,
            "free_gb": None,
            "limit_gib": None,
            "usage_gib": None,
            "free_gib": None,
            "is_unlimited": False
        }

    storage_quota = about_data.get("storageQuota", {})
    user_info = about_data.get("user", {})
    email = user_info.get("emailAddress")

    raw_limit = storage_quota.get("limit")
    raw_usage = storage_quota.get("usage", "0")
    raw_usage_drive = storage_quota.get("usageInDrive", "0")
    raw_usage_trash = storage_quota.get("usageInDriveTrash", "0")

    usage_bytes = int(raw_usage) if raw_usage is not None else 0
    usage_drive_bytes = int(raw_usage_drive) if raw_usage_drive is not None else 0
    usage_trash_bytes = int(raw_usage_trash) if raw_usage_trash is not None else 0

    if raw_limit is None:
        # Unlimited quota or unmetered enterprise/workspace plan
        return {
            "success": True,
            "error": None,
            "email": email,
            "limit_bytes": None,
            "usage_bytes": usage_bytes,
            "usage_drive_bytes": usage_drive_bytes,
            "usage_trash_bytes": usage_trash_bytes,
            "free_bytes": None,
            "limit_gb": None,
            "usage_gb": round(usage_bytes / 1e9, 2),
            "free_gb": None,
            "limit_gib": None,
            "usage_gib": round(usage_bytes / (1024 ** 3), 2),
            "free_gib": None,
            "is_unlimited": True
        }

    limit_bytes = int(raw_limit)
    free_bytes = max(0, limit_bytes - usage_bytes)

    return {
        "success": True,
        "error": None,
        "email": email,
        "limit_bytes": limit_bytes,
        "usage_bytes": usage_bytes,
        "usage_drive_bytes": usage_drive_bytes,
        "usage_trash_bytes": usage_trash_bytes,
        "free_bytes": free_bytes,
        "limit_gb": round(limit_bytes / 1e9, 2),
        "usage_gb": round(usage_bytes / 1e9, 2),
        "free_gb": round(free_bytes / 1e9, 2),
        "limit_gib": round(limit_bytes / (1024 ** 3), 2),
        "usage_gib": round(usage_bytes / (1024 ** 3), 2),
        "free_gib": round(free_bytes / (1024 ** 3), 2),
        "is_unlimited": False
    }


def validate_target_folder(
    service=None,
    folder_id: str = TARGET_FOLDER_ID,
    expected_name: str = TARGET_FOLDER_NAME,
    mock_response: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Validate target Google Drive folder existence, mimeType, and name directly via folder ID.
    Avoids scanning unrelated Drive files.
    """
    folder_data = mock_response
    if folder_data is None and service is not None:
        try:
            folder_data = service.files().get(
                fileId=folder_id,
                fields="id,name,mimeType,trashed"
            ).execute()
        except Exception as e:
            return {
                "valid": False,
                "folder_id": folder_id,
                "folder_name": None,
                "error": f"Failed to access folder ID {folder_id}: {str(e)}"
            }

    if folder_data is None:
        return {
            "valid": False,
            "folder_id": folder_id,
            "folder_name": None,
            "error": "Google Drive API service unavailable for folder validation"
        }

    name = folder_data.get("name")
    mime_type = folder_data.get("mimeType")
    trashed = folder_data.get("trashed", False)

    is_folder = (mime_type == "application/vnd.google-apps.folder")
    name_matches = (name == expected_name)
    not_trashed = (not trashed)

    is_valid = is_folder and name_matches and not_trashed

    return {
        "valid": is_valid,
        "folder_id": folder_data.get("id", folder_id),
        "folder_name": name,
        "mime_type": mime_type,
        "trashed": trashed,
        "is_folder": is_folder,
        "name_matches": name_matches,
        "error": None if is_valid else f"Folder validation failed (is_folder={is_folder}, name_matches={name_matches}, trashed={trashed})"
    }


def get_fuse_usage(path: str) -> Dict[str, Any]:
    """
    Query virtual FUSE filesystem capacity via shutil.disk_usage.
    Marked explicitly as secondary diagnostic information, NOT account quota.
    """
    resolved = os.path.abspath(path)
    # Walk up to existing ancestor if target path does not exist yet
    target = resolved
    while target and not os.path.exists(target) and os.path.dirname(target) != target:
        target = os.path.dirname(target)
    if not target or not os.path.exists(target):
        target = "."

    try:
        total, used, free = shutil.disk_usage(target)
        return {
            "path": resolved,
            "fuse_total_bytes": total,
            "fuse_used_bytes": used,
            "fuse_free_bytes": free,
            "fuse_total_gb": round(total / 1e9, 2),
            "fuse_used_gb": round(used / 1e9, 2),
            "fuse_free_gb": round(free / 1e9, 2),
            "fuse_total_gib": round(total / (1024 ** 3), 2),
            "fuse_used_gib": round(used / (1024 ** 3), 2),
            "fuse_free_gib": round(free / (1024 ** 3), 2),
            "diagnostic_note": "FUSE capacity is a secondary diagnostic metric reflecting the Colab ephemeral virtual mount container and is NOT the user's Google Drive account quota."
        }
    except Exception as e:
        return {
            "path": resolved,
            "fuse_total_bytes": 0,
            "fuse_used_bytes": 0,
            "fuse_free_bytes": 0,
            "fuse_total_gb": 0.0,
            "fuse_used_gb": 0.0,
            "fuse_free_gb": 0.0,
            "fuse_total_gib": 0.0,
            "fuse_used_gib": 0.0,
            "fuse_free_gib": 0.0,
            "error": str(e),
            "diagnostic_note": "FUSE diagnostic query failed (path inaccessible)"
        }


def evaluate_storage_gate(
    account_free_gb: Optional[float],
    is_unlimited: bool = False,
    required_gb: float = 400.0,
    recommended_gb: float = 450.0
) -> Tuple[str, str]:
    """
    Evaluate storage feasibility against required model footprint.
    Decision Rules:
    - If unlimited: GO_UNLIMITED_QUOTA
    - If account_free_gb < required_gb (400 GB): NO-GO
    - If required_gb <= account_free_gb < recommended_gb (450 GB): GO_WITH_LOW_MARGIN
    - If recommended_gb <= account_free_gb < 500 GB: GO
    - If account_free_gb >= 500 GB: GO_WITH_RECOMMENDED_MARGIN
    """
    if is_unlimited:
        return ("GO_UNLIMITED_QUOTA", "Authoritative Google Drive API reports unlimited/unmetered quota. Preflight approved.")
        
    if account_free_gb is None:
        return ("NO-GO_UNKNOWN_QUOTA", "Unable to establish Google Drive API account quota. Authentication required.")

    if account_free_gb < required_gb:
        return (
            "NO-GO",
            f"Insufficient Google Drive account storage: {account_free_gb:.2f} GB free is below the required {required_gb:.2f} GB threshold."
        )
    elif account_free_gb < recommended_gb:
        return (
            "GO_WITH_LOW_MARGIN",
            f"Storage gate passed with low safety margin: {account_free_gb:.2f} GB free exceeds required {required_gb:.2f} GB, but is below recommended {recommended_gb:.2f} GB."
        )
    elif account_free_gb < 500.0:
        return (
            "GO",
            f"Storage gate passed: {account_free_gb:.2f} GB free satisfies recommended threshold ({recommended_gb:.2f} GB)."
        )
    else:
        return (
            "GO_WITH_RECOMMENDED_MARGIN",
            f"Storage gate passed with ample capacity: {account_free_gb:.2f} GB free exceeds preferred safety margin (>= 500 GB)."
        )


def check_drive_storage(
    path: str,
    required_gb: float = 400.0,
    recommended_gb: float = 450.0,
    folder_id: str = TARGET_FOLDER_ID,
    service=None,
    mock_about: Optional[Dict[str, Any]] = None,
    mock_folder: Optional[Dict[str, Any]] = None,
    init_subdirectories: bool = True
) -> Dict[str, Any]:
    """
    Consolidated Google Drive Preflight Audit:
    1. Queries authoritative Google Drive API account quota.
    2. Validates target folder ID and metadata.
    3. Initializes GLM-5.2 project subdirectories on local/FUSE path.
    4. Probes non-destructive write permissions.
    5. Captures FUSE mount diagnostics separately.
    6. Returns complete structured report.
    """
    resolved_path = os.path.abspath(path)
    
    # 1. Authoritative Drive API Quota
    quota_info = get_drive_storage_quota(service=service, mock_response=mock_about)
    account_email = quota_info.get("email") or EXPECTED_ACCOUNT
    
    # 2. Folder Validation via Drive API
    folder_info = validate_target_folder(
        service=service,
        folder_id=folder_id,
        expected_name=TARGET_FOLDER_NAME,
        mock_response=mock_folder
    )
    
    # 3. FUSE Diagnostics (shutil.disk_usage)
    fuse_info = get_fuse_usage(resolved_path)
    
    # 4. Storage Gate Decision
    gate_status, gate_reason = evaluate_storage_gate(
        account_free_gb=quota_info.get("free_gb"),
        is_unlimited=quota_info.get("is_unlimited", False),
        required_gb=required_gb,
        recommended_gb=recommended_gb
    )
    
    # 5. Local/Mount Path Directory Management
    dir_exists = os.path.exists(resolved_path)
    if not dir_exists and init_subdirectories:
        try:
            os.makedirs(resolved_path, exist_ok=True)
            dir_exists = True
        except Exception:
            pass

    project_root = resolved_path if os.path.basename(resolved_path) == "GLM-5.2" else os.path.dirname(resolved_path)
    subdirs = {}
    for subdir in REQUIRED_SUBDIRECTORIES:
        s_path = os.path.join(project_root, subdir)
        if init_subdirectories and dir_exists:
            try:
                os.makedirs(s_path, exist_ok=True)
            except Exception:
                pass
        subdirs[subdir] = {
            "path": s_path,
            "exists": os.path.exists(s_path)
        }

    # 6. Non-destructive write permission probe
    is_writable = False
    write_error = None
    if dir_exists:
        test_probe_file = os.path.join(resolved_path, ".drive_probe_test.tmp")
        try:
            with open(test_probe_file, "w") as f:
                f.write("GLM-5.2 Colibri Drive Probe OK\n")
            if os.path.exists(test_probe_file):
                is_writable = True
                os.remove(test_probe_file)
        except Exception as e:
            write_error = str(e)

    # 7. Final overall status
    is_go = gate_status in ("GO", "GO_WITH_LOW_MARGIN", "GO_WITH_RECOMMENDED_MARGIN", "GO_UNLIMITED_QUOTA")
    overall_status = "HEALTHY" if (is_go and is_writable and folder_info.get("valid", True)) else "NO-GO" if not is_go else "WARNING"

    report = {
        "account_email": account_email,
        "target_folder_name": TARGET_FOLDER_NAME,
        "target_folder_id": folder_id,
        "target_path": resolved_path,
        "drive_account_quota_limit_bytes": quota_info.get("limit_bytes"),
        "drive_account_quota_limit_gb": quota_info.get("limit_gb"),
        "drive_account_quota_limit_gib": quota_info.get("limit_gib"),
        "drive_account_usage_bytes": quota_info.get("usage_bytes"),
        "drive_account_usage_gb": quota_info.get("usage_gb"),
        "drive_account_usage_gib": quota_info.get("usage_gib"),
        "drive_account_free_bytes": quota_info.get("free_bytes"),
        "drive_account_free_gb": quota_info.get("free_gb"),
        "drive_account_free_gib": quota_info.get("free_gib"),
        "is_unlimited_quota": quota_info.get("is_unlimited", False),
        "fuse_total_bytes": fuse_info.get("fuse_total_bytes"),
        "fuse_total_gb": fuse_info.get("fuse_total_gb"),
        "fuse_used_bytes": fuse_info.get("fuse_used_bytes"),
        "fuse_used_gb": fuse_info.get("fuse_used_gb"),
        "fuse_free_bytes": fuse_info.get("fuse_free_bytes"),
        "fuse_free_gb": fuse_info.get("fuse_free_gb"),
        "fuse_diagnostic_note": fuse_info.get("diagnostic_note"),
        "required_free_gb": required_gb,
        "recommended_free_gb": recommended_gb,
        "storage_gate_status": gate_status,
        "storage_gate_reason": gate_reason,
        "folder_validation_status": "VALID" if folder_info.get("valid") else "FAILED",
        "folder_validation_error": folder_info.get("error"),
        "write_permission_status": "GRANTED" if is_writable else "DENIED",
        "write_permission_error": write_error,
        "subdirectories": subdirs,
        "status": overall_status
    }
    
    return report


def main():
    parser = argparse.ArgumentParser(description="Google Drive Storage & Project Structure Check")
    parser.add_argument("--path", default=os.getenv("DRIVE_MODEL_DIR", "/content/drive/MyDrive/AI - Google Drive/GLM-5.2/model"),
                        help="Google Drive mount project or model directory")
    parser.add_argument("--required-gb", type=float, default=400.0,
                        help="Minimum required free storage in GB (default: 400.0)")
    parser.add_argument("--recommended-gb", type=float, default=450.0,
                        help="Recommended free storage in GB (default: 450.0)")
    parser.add_argument("--folder-id", default=TARGET_FOLDER_ID,
                        help=f"Google Drive target folder ID (default: {TARGET_FOLDER_ID})")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    args = parser.parse_args()

    service = get_drive_service()
    report = check_drive_storage(
        path=args.path,
        required_gb=args.required_gb,
        recommended_gb=args.recommended_gb,
        folder_id=args.folder_id,
        service=service
    )

    if args.json:
        print(json.dumps(report, indent=2))
        is_success = report["storage_gate_status"] in ("GO", "GO_WITH_LOW_MARGIN", "GO_WITH_RECOMMENDED_MARGIN", "GO_UNLIMITED_QUOTA")
        sys.exit(0 if is_success else 1)

    if console:
        is_go = report["storage_gate_status"] in ("GO", "GO_WITH_LOW_MARGIN", "GO_WITH_RECOMMENDED_MARGIN", "GO_UNLIMITED_QUOTA")
        color = "green" if is_go else "red"
        
        limit_str = f"{report['drive_account_quota_limit_gb']:,} GB ({report['drive_account_quota_limit_gib']} GiB)" if report['drive_account_quota_limit_gb'] else "Unlimited / Unmetered"
        free_str = f"{report['drive_account_free_gb']:,} GB ({report['drive_account_free_gib']} GiB)" if report['drive_account_free_gb'] else "Unlimited / Unmetered"
        used_str = f"{report['drive_account_usage_gb']:,} GB ({report['drive_account_usage_gib']} GiB)" if report['drive_account_usage_gb'] else "Unknown"

        text = (
            f"[bold cyan]=== Authoritative Google Drive Account Quota (API v3) ===[/bold cyan]\n"
            f"[bold]Account:[/bold]                 {report['account_email']}\n"
            f"[bold]Target Folder:[/bold]            {report['target_folder_name']} (ID: {report['target_folder_id']})\n"
            f"[bold]Total Account Plan:[/bold]       {limit_str}\n"
            f"[bold]Used Space:[/bold]               {used_str}\n"
            f"[bold]Available Free Space:[/bold]     [bold {color}]{free_str}[/bold {color}]\n"
            f"[bold]Required Threshold:[/bold]       >= {report['required_free_gb']} GB (Recommended: >= {report['recommended_free_gb']} GB)\n"
            f"[bold]Storage Gate Status:[/bold]      [{color}]{report['storage_gate_status']}[/{color}]\n"
            f"[bold]Reason:[/bold]                  {report['storage_gate_reason']}\n\n"
            f"[bold yellow]=== Google Drive FUSE Mount (Diagnostic Only) ===[/bold yellow]\n"
            f"[bold]Mount Path:[/bold]               {report['target_path']}\n"
            f"[bold]FUSE Virtual Capacity:[/bold]    {report['fuse_total_gb']} GB (Free: {report['fuse_free_gb']} GB)\n"
            f"[bold]Note:[/bold]                    {report['fuse_diagnostic_note']}\n\n"
            f"[bold]Write Permitted:[/bold]          {'Yes' if report['write_permission_status'] == 'GRANTED' else 'No'}\n"
            f"[bold]Subdirectories:[/bold]           {', '.join(report['subdirectories'].keys())}"
        )
        console.print(Panel(text, title="Google Drive Storage & Isolation Preflight Report", border_style=color))
    else:
        print(json.dumps(report, indent=2))

    is_success = report["storage_gate_status"] in ("GO", "GO_WITH_LOW_MARGIN", "GO_WITH_RECOMMENDED_MARGIN", "GO_UNLIMITED_QUOTA")
    sys.exit(0 if is_success else 1)


if __name__ == "__main__":
    main()
