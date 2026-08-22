#!/usr/bin/env python3
"""
Model Shard Discovery & Inventory Scanner
Discovers, enumerates, and catalogs all Safetensors weight shards, metadata,
and tokenizer artifacts in a target model directory.
"""

import sys
import os
import glob
import json
import argparse
from typing import Dict, Any, List

try:
    from rich.console import Console  # type: ignore
    from rich.table import Table      # type: ignore
    console = Console()
except ImportError:
    console = None

REQUIRED_METADATA_FILES = [
    "config.json",
    "generation_config.json"
]

REQUIRED_TOKENIZER_FILES = [
    "tokenizer.json",
    "tokenizer_config.json"
]

OPTIONAL_FILES = [
    "model.safetensors.index.json",
    "special_tokens_map.json",
    "out-mtp-00000.safetensors"
]


def scan_model_directory(model_dir: str) -> Dict[str, Any]:
    """Scan and catalog all model files in the target directory."""
    abs_dir = os.path.abspath(model_dir)
    
    if not os.path.exists(abs_dir):
        return {
            "model_dir": abs_dir,
            "exists": False,
            "status": "MISSING",
            "metadata_files": {},
            "tokenizer_files": {},
            "shards": [],
            "total_shards": 0,
            "total_bytes": 0,
            "total_gb": 0.0,
            "missing_metadata": REQUIRED_METADATA_FILES,
            "missing_tokenizer": REQUIRED_TOKENIZER_FILES
        }
    
    # Check metadata files
    metadata_found = {}
    missing_metadata = []
    for meta in REQUIRED_METADATA_FILES:
        meta_path = os.path.join(abs_dir, meta)
        if os.path.exists(meta_path):
            metadata_found[meta] = {
                "size_bytes": os.path.getsize(meta_path),
                "path": meta_path
            }
        else:
            missing_metadata.append(meta)
            
    # Check tokenizer files
    tokenizer_found = {}
    missing_tokenizer = []
    for tok in REQUIRED_TOKENIZER_FILES:
        tok_path = os.path.join(abs_dir, tok)
        if os.path.exists(tok_path):
            tokenizer_found[tok] = {
                "size_bytes": os.path.getsize(tok_path),
                "path": tok_path
            }
        else:
            missing_tokenizer.append(tok)
            
    # Discover Safetensors shards
    shard_paths = sorted(glob.glob(os.path.join(abs_dir, "*.safetensors")))
    shards_info = []
    total_bytes = 0
    
    for sp in shard_paths:
        sz = os.path.getsize(sp)
        total_bytes += sz
        shards_info.append({
            "filename": os.path.basename(sp),
            "size_bytes": sz,
            "size_gb": round(sz / (1024 ** 3), 3),
            "path": sp
        })
        
    total_gb = round(total_bytes / (1024 ** 3), 2)
    
    # Determine status
    if len(shards_info) >= 38 and not missing_metadata and not missing_tokenizer:
        status = "COMPLETE"
    elif len(shards_info) > 0:
        status = "PARTIAL"
    else:
        status = "EMPTY"
        
    return {
        "model_dir": abs_dir,
        "exists": True,
        "status": status,
        "metadata_files": metadata_found,
        "tokenizer_files": tokenizer_found,
        "shards": shards_info,
        "total_shards": len(shards_info),
        "total_bytes": total_bytes,
        "total_gb": total_gb,
        "missing_metadata": missing_metadata,
        "missing_tokenizer": missing_tokenizer
    }


def print_inventory_table(inventory: Dict[str, Any]):
    """Render human-readable table of model inventory."""
    if not console:
        print(json.dumps(inventory, indent=2))
        return

    table = Table(title=f"Model Inventory: {inventory['model_dir']}", show_lines=True)
    table.add_column("Category", style="cyan")
    table.add_column("Component", style="magenta")
    table.add_column("Details / Status", style="green")

    # Status & Totals
    table.add_row("Overview", "Status", inventory["status"])
    table.add_row("Overview", "Total Shards", str(inventory["total_shards"]))
    table.add_row("Overview", "Total Size", f"{inventory['total_gb']} GB ({inventory['total_bytes']:,} bytes)")

    # Metadata
    for meta in REQUIRED_METADATA_FILES:
        if meta in inventory["metadata_files"]:
            table.add_row("Metadata", meta, f"Present ({inventory['metadata_files'][meta]['size_bytes']:,} B)")
        else:
            table.add_row("Metadata", meta, "[red]MISSING[/red]")

    # Tokenizer
    for tok in REQUIRED_TOKENIZER_FILES:
        if tok in inventory["tokenizer_files"]:
            table.add_row("Tokenizer", tok, f"Present ({inventory['tokenizer_files'][tok]['size_bytes']:,} B)")
        else:
            table.add_row("Tokenizer", tok, "[red]MISSING[/red]")

    console.print(table)


def main():
    parser = argparse.ArgumentParser(description="Model Shard Discovery & Inventory Scanner")
    parser.add_argument("--model-dir", default=os.getenv("MODEL_DIR", "./model"),
                        help="Target model directory to inspect")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    parser.add_argument("--output", help="Optional file path to save inventory JSON")
    args = parser.parse_args()

    inventory = scan_model_directory(args.model_dir)

    if args.output:
        os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
        with open(args.output, "w") as f:
            json.dump(inventory, f, indent=2)

    if args.json:
        print(json.dumps(inventory, indent=2))
    else:
        print_inventory_table(inventory)


if __name__ == "__main__":
    main()
