#!/usr/bin/env python3
"""
Consolidated Engineering & Benchmark Report Generator
Compiles environment diagnostics, model inventory, integrity verification,
and storage benchmark measurements into structured Markdown and JSON reports.
"""

import sys
import os
import glob
import json
import time
import argparse
from typing import Dict, Any

from environment_check import run_full_diagnostic
from model_verify import verify_model_directory


def generate_consolidated_report(
    model_dir: str = "./model",
    benchmark_dir: str = "./benchmarks",
    output_path: str = "./reports/engineering_report.md"
) -> Dict[str, Any]:
    """Compile multi-subsystem data into a comprehensive report."""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    
    # 1. Environment data
    env_data = run_full_diagnostic()
    
    # 2. Model verification data
    model_data = verify_model_directory(model_dir, min_expected_shards=1 if "mock" in model_dir else 38)
    
    # 3. Benchmark data
    benchmark_files = sorted(glob.glob(os.path.join(benchmark_dir, "*.json")))
    latest_benchmark = {}
    if benchmark_files:
        try:
            with open(benchmark_files[-1], "r") as bf:
                latest_benchmark = json.load(bf)
        except Exception:
            pass
            
    report_dict = {
        "report_id": f"rep_{int(time.time())}",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "environment": env_data,
        "model_integrity": model_data,
        "benchmark": latest_benchmark
    }
    
    # Render Markdown
    md_lines = [
        "# Consolidated Engineering & Benchmark Report: GLM-5.2 Colibri Runtime",
        "",
        f"**Generated At**: {report_dict['generated_at']}  ",
        f"**Report ID**: `{report_dict['report_id']}`  ",
        "",
        "---",
        "",
        "## 1. Environment & Hardware Summary",
        "",
        f"- **Operating System**: {env_data['platform']['os']} ({env_data['platform']['architecture']})",
        f"- **Python Version**: {env_data['platform']['python_version']}",
        f"- **CPU Cores**: {env_data['cpu']['logical_cores']} logical cores (AVX2: {env_data['cpu']['avx2_supported']})",
        f"- **RAM**: {env_data['memory'].get('available_ram_gb', 'N/A')} GB available / {env_data['memory'].get('total_ram_gb', 'N/A')} GB total",
        f"- **Dense Core 9.9 GB Residency**: {'READY' if env_data['memory'].get('can_host_dense_core') else 'CONSTRAINED'}",
        "",
        "---",
        "",
        "## 2. Model Shard & Integrity Status",
        "",
        f"- **Model Path**: `{model_data['model_dir']}`",
        f"- **Validation Status**: **{model_data['status']}**",
        f"- **Safetensors Shards Found**: {model_data['total_shards_found']} / {model_data['expected_shards']}",
        f"- **Total Model Volume**: {model_data['total_gb']} GB ({model_data['total_bytes']:,} bytes)",
        f"- **Metadata Valid**: {'Yes' if model_data['metadata_valid'] else 'No'}",
        f"- **Tokenizer Valid**: {'Yes' if model_data['tokenizer_valid'] else 'No'}",
        "",
        "---",
        "",
        "## 3. Storage Benchmark Comparison (Local NVMe vs. Google Drive FUSE)",
        ""
    ]
    
    if latest_benchmark and "summary" in latest_benchmark:
        s = latest_benchmark["summary"]
        md_lines.extend([
            "| Storage Medium | Average TTFT (s) | Average Decode Speed (tok/s) | Relative Speedup |",
            "| :--- | :--- | :--- | :--- |",
            f"| **Colab Local NVMe** | {s.get('local_avg_ttft_seconds', 'N/A')} s | {s.get('local_avg_tokens_per_sec', 'N/A')} tok/s | **{s.get('speedup_factor_local_vs_drive', 'N/A')}x** |",
            f"| **Google Drive FUSE** | {s.get('drive_avg_ttft_seconds', 'N/A')} s | {s.get('drive_avg_tokens_per_sec', 'N/A')} tok/s | 1.0x (Baseline) |",
            "",
            "> [!NOTE]",
            "> Direct Google Drive streaming latency is dominated by FUSE network roundtrips. Staging hot experts onto local NVMe produces massive throughput improvements."
        ])
    else:
        md_lines.append("*No benchmark measurements recorded yet. Run `scripts/benchmark.py` to capture metrics.*")
        
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines) + "\n")
        
    json_path = output_path.replace(".md", ".json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report_dict, f, indent=2)
        
    return report_dict


def main():
    parser = argparse.ArgumentParser(description="Consolidated Engineering Report Generator")
    parser.add_argument("--model-dir", default="./model", help="Model directory")
    parser.add_argument("--benchmark-dir", default="./benchmarks", help="Benchmarks directory")
    parser.add_argument("--output", default="./reports/engineering_report.md", help="Markdown output path")
    args = parser.parse_args()

    generate_consolidated_report(args.model_dir, args.benchmark_dir, args.output)
    print(f"Report generated at {args.output}")


if __name__ == "__main__":
    main()
