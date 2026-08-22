#!/usr/bin/env python3
"""
Non-Destructive Model Integrity & Safetensors Header Validator
Inspects Safetensors headers, metadata consistency, and shard completeness
without loading multi-gigabyte tensors into system RAM.
"""

import sys
import os
import glob
import json
import struct
import argparse
from typing import Dict, Any, List, Tuple, Optional

try:
    from rich.console import Console  # type: ignore
    from rich.table import Table      # type: ignore
    console = Console()
except ImportError:
    console = None

REQUIRED_METADATA_FILES = [
    "config.json",
    "generation_config.json",
    "model.safetensors.index.json"
]

REQUIRED_TOKENIZER_FILES = [
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json"
]


def read_safetensors_header(file_path: str) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
    """
    Non-destructively parse the Safetensors JSON header from the file prefix.
    Safetensors specification:
    - First 8 bytes: unsigned 64-bit integer (little-endian) representing header length N.
    - Next N bytes: UTF-8 encoded JSON string of tensor metadata.
    """
    if not os.path.exists(file_path):
        return False, None, "File does not exist"
        
    file_size = os.path.getsize(file_path)
    if file_size < 8:
        return False, None, "File is truncated (smaller than 8-byte header prefix)"
        
    try:
        with open(file_path, "rb") as f:
            header_len_bytes = f.read(8)
            header_len = struct.unpack("<Q", header_len_bytes)[0]
            
            if header_len > file_size - 8 or header_len > 100 * 1024 * 1024:  # Header sanity limit 100MB
                return False, None, f"Corrupted header length ({header_len} bytes) exceeds file boundaries"
                
            header_json_bytes = f.read(header_len)
            header_json = json.loads(header_json_bytes.decode("utf-8"))
            return True, header_json, None
    except Exception as e:
        return False, None, f"Header parse failure: {str(e)}"


def verify_model_directory(model_dir: str, min_expected_shards: int = 38) -> Dict[str, Any]:
    """Perform full non-destructive validation on target model directory."""
    abs_dir = os.path.abspath(model_dir)
    report = {
        "model_dir": abs_dir,
        "status": "UNKNOWN",
        "metadata_valid": False,
        "tokenizer_valid": False,
        "shards_valid": False,
        "total_shards_found": 0,
        "expected_shards": min_expected_shards,
        "corrupted_shards": [],
        "missing_files": [],
        "total_bytes": 0,
        "total_gb": 0.0,
        "details": []
    }
    
    if not os.path.exists(abs_dir):
        report["status"] = "MISSING"
        report["missing_files"].append("Entire directory is missing")
        return report
        
    # 1. Verify Metadata Files
    missing_meta = []
    for meta_name in REQUIRED_METADATA_FILES:
        meta_path = os.path.join(abs_dir, meta_name)
        if not os.path.exists(meta_path):
            missing_meta.append(meta_name)
        else:
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    json.load(f)
            except Exception:
                missing_meta.append(f"{meta_name} (corrupt JSON)")
                
    report["metadata_valid"] = len(missing_meta) == 0
    if missing_meta:
        report["missing_files"].extend(missing_meta)
        
    # 2. Verify Tokenizer Files
    missing_tok = []
    for tok_name in REQUIRED_TOKENIZER_FILES:
        tok_path = os.path.join(abs_dir, tok_name)
        if not os.path.exists(tok_path):
            missing_tok.append(tok_name)
        else:
            try:
                with open(tok_path, "r", encoding="utf-8") as f:
                    json.load(f)
            except Exception:
                missing_tok.append(f"{tok_name} (corrupt JSON)")
                
    report["tokenizer_valid"] = len(missing_tok) == 0
    if missing_tok:
        report["missing_files"].extend(missing_tok)
        
    # 3. Verify Safetensors Shards
    shard_paths = sorted(glob.glob(os.path.join(abs_dir, "*.safetensors")))
    report["total_shards_found"] = len(shard_paths)
    
    total_bytes = 0
    corrupted = []
    for sp in shard_paths:
        sz = os.path.getsize(sp)
        total_bytes += sz
        ok, header, err = read_safetensors_header(sp)
        if not ok:
            corrupted.append({"file": os.path.basename(sp), "error": err})
            
    report["total_bytes"] = total_bytes
    report["total_gb"] = round(total_bytes / (1024 ** 3), 2)
    report["corrupted_shards"] = corrupted
    
    if len(corrupted) > 0:
        report["status"] = "CORRUPTED"
    elif report["total_shards_found"] < min_expected_shards:
        report["status"] = "INCOMPLETE"
    elif report["metadata_valid"] and report["tokenizer_valid"] and report["total_shards_found"] >= min_expected_shards:
        report["status"] = "READY"
        report["shards_valid"] = True
    else:
        report["status"] = "INCOMPLETE"
        
    return report


def print_verification_report(report: Dict[str, Any]):
    """Render rich verification summary."""
    if not console:
        print(json.dumps(report, indent=2))
        return
        
    color_map = {
        "READY": "green",
        "INCOMPLETE": "yellow",
        "CORRUPTED": "red",
        "MISSING": "red",
        "UNKNOWN": "white"
    }
    status_color = color_map.get(report["status"], "white")
    
    table = Table(title=f"Safetensors Model Integrity Report: {report['model_dir']}", show_lines=True)
    table.add_column("Verification Step", style="cyan")
    table.add_column("Expected", style="magenta")
    table.add_column("Observed", style="bold")
    table.add_column("Result", style=status_color)
    
    table.add_row("Overall Status", "READY", f"[{status_color}]{report['status']}[/{status_color}]", "PASS" if report['status'] == "READY" else "FAIL")
    table.add_row("Metadata Files", f"{len(REQUIRED_METADATA_FILES)} valid JSONs", f"{len(REQUIRED_METADATA_FILES) - len([m for m in report['missing_files'] if m in REQUIRED_METADATA_FILES])} found", "PASS" if report['metadata_valid'] else "FAIL")
    table.add_row("Tokenizer Files", f"{len(REQUIRED_TOKENIZER_FILES)} valid JSONs", f"{len(REQUIRED_TOKENIZER_FILES) - len([t for t in report['missing_files'] if t in REQUIRED_TOKENIZER_FILES])} found", "PASS" if report['tokenizer_valid'] else "FAIL")
    table.add_row("Safetensors Shards", f">={report['expected_shards']} valid shards", f"{report['total_shards_found']} shards ({report['total_gb']} GB)", "PASS" if report['shards_valid'] else "FAIL")
    
    console.print(table)
    
    if report["corrupted_shards"]:
        console.print(f"[bold red]Corrupted Shards Detected ({len(report['corrupted_shards'])}):[/bold red]")
        for c in report["corrupted_shards"]:
            console.print(f"  - {c['file']}: {c['error']}")
            
    if report["missing_files"]:
        console.print(f"[bold yellow]Missing / Incomplete Artifacts ({len(report['missing_files'])}):[/bold yellow]")
        for m in report["missing_files"]:
            console.print(f"  - {m}")


def main():
    parser = argparse.ArgumentParser(description="Non-Destructive Model Header Validator")
    parser.add_argument("--model-dir", default=os.getenv("MODEL_DIR", "./model"),
                        help="Target directory containing model shards and metadata")
    parser.add_argument("--expected-shards", type=int, default=38,
                        help="Expected number of Safetensors shard files")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    args = parser.parse_args()

    report = verify_model_directory(args.model_dir, args.expected_shards)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_verification_report(report)

    sys.exit(0 if report["status"] == "READY" else 1)


if __name__ == "__main__":
    main()
