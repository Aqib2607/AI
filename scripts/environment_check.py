#!/usr/bin/env python3
"""
Environment Diagnostic & Hardware Capability Probe
Detects CPU vector capabilities, RAM residency budget, GPU presence, disk space,
and build toolchain availability for the Colibrì GLM-5.2 runtime.
"""

import sys
import os
import platform
import shutil
import subprocess
import json
import argparse
from typing import Dict, Any

try:
    import psutil  # type: ignore
except ImportError:
    psutil = None

try:
    from rich.console import Console  # type: ignore
    from rich.table import Table      # type: ignore
    console = Console()
except ImportError:
    console = None


def check_command(cmd: str) -> Dict[str, Any]:
    """Check whether a binary is available on PATH and return its version."""
    path = shutil.which(cmd)
    if not path:
        return {"available": False, "path": None, "version": None}
    
    version = None
    try:
        if cmd in ("gcc", "g++", "clang", "make", "git"):
            res = subprocess.run([cmd, "--version"], capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                version = res.stdout.splitlines()[0].strip()
        elif cmd == "python" or cmd == "python3":
            version = platform.python_version()
    except Exception as e:
        version = f"Error: {str(e)}"
    
    return {"available": True, "path": path, "version": version}


def check_cpu_features() -> Dict[str, Any]:
    """Detect CPU architectural details and OpenMP / vector capability."""
    cpu_info = {
        "processor": platform.processor(),
        "machine": platform.machine(),
        "physical_cores": psutil.cpu_count(logical=False) if psutil else "Unknown",
        "logical_cores": psutil.cpu_count(logical=True) if psutil else os.cpu_count(),
        "avx2_supported": False,
        "avx512_supported": False,
    }
    
    # On Linux / Colab, inspect /proc/cpuinfo
    if sys.platform.startswith("linux") and os.path.exists("/proc/cpuinfo"):
        try:
            with open("/proc/cpuinfo", "r") as f:
                flags_text = f.read().lower()
                cpu_info["avx2_supported"] = "avx2" in flags_text
                cpu_info["avx512_supported"] = "avx512" in flags_text or "avx512f" in flags_text
        except Exception:
            pass
    elif sys.platform.startswith("win"):
        # On Windows, modern x86_64 CPUs typically support AVX2
        cpu_info["avx2_supported"] = True
    
    return cpu_info


def check_memory() -> Dict[str, Any]:
    """Inspect system RAM and calculate Colibri dense-weight residency feasibility."""
    if not psutil:
        return {"error": "psutil not installed"}
    
    mem = psutil.virtual_memory()
    total_gb = mem.total / (1024 ** 3)
    available_gb = mem.available / (1024 ** 3)
    required_dense_gb = 9.9
    
    return {
        "total_ram_gb": round(total_gb, 2),
        "available_ram_gb": round(available_gb, 2),
        "used_ram_gb": round((mem.total - mem.available) / (1024 ** 3), 2),
        "percent_used": mem.percent,
        "required_dense_ram_gb": required_dense_gb,
        "can_host_dense_core": available_gb >= required_dense_gb,
        "recommendation": (
            "High-RAM runtime recommended" if total_gb < 16.0 else "RAM capacity sufficient for dense weights"
        )
    }


def check_disk(target_path: str = ".") -> Dict[str, Any]:
    """Inspect disk space for target workspace."""
    try:
        total, used, free = shutil.disk_usage(target_path)
        return {
            "path": os.path.abspath(target_path),
            "total_gb": round(total / (1024 ** 3), 2),
            "used_gb": round(used / (1024 ** 3), 2),
            "free_gb": round(free / (1024 ** 3), 2),
            "can_host_full_model_locally": (free / (1024 ** 3)) >= 380.0,
            "can_host_partial_mirror": (free / (1024 ** 3)) >= 150.0
        }
    except Exception as e:
        return {"error": str(e)}


def check_gpu() -> Dict[str, Any]:
    """Detect NVIDIA CUDA acceleration availability without hard requirement."""
    gpu_info = {"has_nvidia_gpu": False, "device_name": None, "vram_gb": 0.0}
    nvidia_smi = shutil.which("nvidia-smi")
    if nvidia_smi:
        try:
            res = subprocess.run([nvidia_smi, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                                 capture_output=True, text=True, timeout=5)
            if res.returncode == 0 and res.stdout.strip():
                lines = res.stdout.strip().splitlines()
                gpu_info["has_nvidia_gpu"] = True
                gpu_info["device_name"] = lines[0].split(",")[0].strip()
                try:
                    gpu_info["vram_gb"] = round(float(lines[0].split(",")[1].strip()) / 1024, 2)
                except Exception:
                    pass
        except Exception:
            pass
    return gpu_info


def run_full_diagnostic(target_path: str = ".") -> Dict[str, Any]:
    """Compile all system checks into a single structured report."""
    return {
        "platform": {
            "os": platform.system(),
            "os_release": platform.release(),
            "os_version": platform.version(),
            "architecture": platform.machine(),
            "python_version": platform.python_version()
        },
        "cpu": check_cpu_features(),
        "memory": check_memory(),
        "disk": check_disk(target_path),
        "gpu": check_gpu(),
        "toolchain": {
            "gcc": check_command("gcc"),
            "g++": check_command("g++"),
            "clang": check_command("clang"),
            "make": check_command("make"),
            "git": check_command("git"),
        }
    }


def print_table_report(report: Dict[str, Any]):
    """Render human-readable rich CLI summary table."""
    if not console:
        print(json.dumps(report, indent=2))
        return

    table = Table(title="Colibrì GLM-5.2 Environment Diagnostic Report", show_lines=True)
    table.add_column("Subsystem", style="cyan", no_wrap=True)
    table.add_column("Property", style="magenta")
    table.add_column("Value / Status", style="green")

    # Platform
    table.add_row("Platform", "OS", f"{report['platform']['os']} {report['platform']['os_release']}")
    table.add_row("Platform", "Python", report['platform']['python_version'])

    # CPU & RAM
    table.add_row("CPU", "Logical Cores", str(report['cpu']['logical_cores']))
    table.add_row("CPU", "AVX2 Vector Support", "[green]Yes[/green]" if report['cpu']['avx2_supported'] else "[yellow]No[/yellow]")
    table.add_row("RAM", "Available RAM", f"{report['memory'].get('available_ram_gb', 'N/A')} GB / {report['memory'].get('total_ram_gb', 'N/A')} GB")
    dense_ok = report['memory'].get('can_host_dense_core', False)
    table.add_row("RAM", "9.9 GB Dense Core Residency", "[green]PASS[/green]" if dense_ok else "[red]FAIL (Low RAM)[/red]")

    # Disk
    table.add_row("Disk", "Free Storage", f"{report['disk'].get('free_gb', 'N/A')} GB")
    table.add_row("Disk", "380 GB Full Staging", "[green]Ready[/green]" if report['disk'].get('can_host_full_model_locally') else "[yellow]Use Dual-Drive / Cloud Staging[/yellow]")

    # GPU
    gpu = report['gpu']
    table.add_row("GPU", "NVIDIA CUDA Acceleration", f"{gpu['device_name']} ({gpu['vram_gb']} GB)" if gpu['has_nvidia_gpu'] else "[blue]CPU Inference Mode (No CUDA)[/blue]")

    # Toolchain
    for tool, data in report['toolchain'].items():
        status = f"[green]Found[/green] ({data['version']})" if data['available'] else "[red]Missing[/red]"
        table.add_row("Toolchain", tool, status)

    console.print(table)


def main():
    parser = argparse.ArgumentParser(description="Colibri GLM-5.2 Environment Diagnostic")
    parser.add_argument("--json", action="store_true", help="Output raw JSON format")
    parser.add_argument("--local", action="store_true", help="Run local workstation check")
    parser.add_argument("--path", default=".", help="Target disk path to inspect")
    args = parser.parse_args()

    report = run_full_diagnostic(args.path)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_table_report(report)


if __name__ == "__main__":
    main()
