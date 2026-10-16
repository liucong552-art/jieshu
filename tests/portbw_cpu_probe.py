#!/usr/bin/env python3
"""Measure baseline/candidate portbw in a disposable Linux network namespace.

This script calls reconcile(), which can repair rules; it REFUSES to execute in
the host network namespace. Never use it against a production portbw state.
It neither creates namespaces nor sets up traffic.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import importlib.util
import json
import os
from pathlib import Path
import resource
import statistics
import subprocess
import sys
import time


def check_isolation():
    if os.getenv("PORTBW_LAB_ACK") != "isolated-netns-only":
        raise SystemExit("REFUSED: lab not explicitly enabled")
    host = os.stat("/proc/1/ns/net").st_ino
    ours = os.stat("/proc/self/ns/net").st_ino
    if ours == host:
        raise SystemExit("REFUSED: host network namespace; no kernel reads/writes attempted")
    required = ("PORTBW_STATE", "PORTBW_CONF", "PORTBW_LOCK", "PORTBW_RUN")
    for key in required:
        value = os.environ.get(key, "")
        if not value.startswith("/tmp/portbw-cpu-"):
            raise SystemExit(f"REFUSED: {key} must be an explicit /tmp/portbw-cpu-* test path")
    if os.environ.get("PORTBW_UNITS", "") == "/etc/systemd/system":
        raise SystemExit("REFUSED: host systemd unit path")


def proc_stat():
    with open("/proc/stat", encoding="ascii") as f:
        values = list(map(int, f.readline().split()[1:]))
    return sum(values[:8]), values[3] + values[4]


def children_cpu():
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    return usage.ru_utime + usage.ru_stime


def percentile(data, q):
    if not data:
        return None
    data = sorted(data)
    i = (len(data) - 1) * q
    low = int(i)
    return data[low] * (1 - (i - low)) + data[min(low + 1, len(data) - 1)] * (i - low)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("source", help="Original main/portbw.py or candidate portbw.py")
    p.add_argument("--rounds", type=int, default=180)
    p.add_argument("--warmup", type=int, default=3)
    p.add_argument("--interval", type=float, default=1.0)
    p.add_argument("--label", default="unlabeled")
    p.add_argument("--profile", default="", help="Optional profiler output; use in SEPARATE diagnostic run")
    args = p.parse_args()
    check_isolation()
    if args.rounds < 1 or not 0 <= args.warmup <= 20 or not 0.5 <= args.interval <= 10:
        p.error("invalid sampling parameters")
    if args.profile and not args.profile.startswith("/tmp/portbw-cpu-"):
        p.error("--profile must be a /tmp/portbw-cpu-* path")
    src = Path(args.source).resolve()
    if src.name != "portbw.py" or not src.is_file():
        p.error("source must point to a portbw.py file")

    spec = importlib.util.spec_from_file_location("portbw_probe_target", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    config = mod.cfg()
    if not config.get("tc_enabled"):
        raise SystemExit("REFUSED: benchmark must include nft+tc, not nft-only")

    old_run = subprocess.run
    all_calls = []
    active = False

    def timed_run(*a, **kw):
        nonlocal active
        if not active:
            return old_run(*a, **kw)
        command = a[0] if a else kw.get("args", [])
        name = os.path.basename(str(command[0])) if command else "unknown"
        parts = [str(v) for v in command[1:]]
        if name == "nft":
            detail = "nft list table" if "list" in parts and "table" in parts else "nft other"
        elif name == "tc":
            if "qdisc" in parts:
                detail = "tc qdisc"
            elif "filter" in parts:
                detail = "tc filter stats" if "-s" in parts else "tc filter json"
            elif "actions" in parts:
                detail = "tc actions"
            else:
                detail = "tc other"
        else:
            detail = name
        before = time.perf_counter()
        before_cpu = children_cpu()
        try:
            return old_run(*a, **kw)
        finally:
            all_calls.append({"command": detail,
                              "wall": time.perf_counter() - before,
                              "child_cpu": children_cpu() - before_cpu})

    # Counts BOTH portbw.run(...) and nft_snapshot()'s direct subprocess.run(...).
    subprocess.run = timed_run
    profile = None
    if args.profile:
        import cProfile
        profile = cProfile.Profile()

    laps, pycpu, childcpu = [], [], []
    errors = []
    try:
        # Warm up; measured rounds must not include initial rule repair.
        for _ in range(args.warmup):
            mod.reconcile(config, monitor=True)
        starting_stats = proc_stat()
        start_wall = time.perf_counter()
        active = True
        if profile:
            profile.enable()
        for i in range(args.rounds):
            t = time.perf_counter()
            py_start, child_start = time.process_time(), children_cpu()
            try:
                mod.reconcile(config, monitor=True)
            except Exception as exc:
                errors.append(f"round={i}: {type(exc).__name__}: {str(exc)[:300]}")
                break
            duration = time.perf_counter() - t
            laps.append(duration)
            pycpu.append(time.process_time() - py_start)
            childcpu.append(children_cpu() - child_start)
            time.sleep(max(0.0, args.interval - duration))
        if profile:
            profile.disable()
        elapsed = time.perf_counter() - start_wall
        ending_stats = proc_stat()
    finally:
        active = False
        subprocess.run = old_run
        if profile:
            profile.dump_stats(args.profile)
            import io
            import pstats
            text = io.StringIO()
            stats = pstats.Stats(profile, stream=text)
            stats.strip_dirs().sort_stats("cumtime").print_stats(35)
            stats.sort_stats("tottime").print_stats(35)
            Path(args.profile + ".txt").write_text(text.getvalue(), encoding="utf-8")

    totals = Counter(x["command"] for x in all_calls)
    per_command_wall = defaultdict(float)
    per_command_childcpu = defaultdict(float)
    for item in all_calls:
        per_command_wall[item["command"]] += item["wall"]
        per_command_childcpu[item["command"]] += item["child_cpu"]
    dt = ending_stats[0] - starting_stats[0]
    idle = ending_stats[1] - starting_stats[1]
    machine_busy = (100 * (dt - idle) / dt) if dt > 0 else None
    result = {
        "label": args.label,
        "source": str(src),
        "source_sha256": __import__("hashlib").sha256(src.read_bytes()).hexdigest(),
        "completed_rounds": len(laps),
        "requested_rounds": args.rounds,
        "errors": errors,
        "wall_seconds": round(elapsed, 4),
        "process_cpu_seconds": round(sum(pycpu), 6),
        "child_cpu_seconds": round(sum(childcpu), 6),
        "process_one_core_pct": round(100 * sum(pycpu) / elapsed, 3) if elapsed else None,
        "process_plus_children_one_core_pct": round(100 * (sum(pycpu) + sum(childcpu)) / elapsed, 3) if elapsed else None,
        "machine_busy_pct": round(machine_busy, 3) if machine_busy is not None else None,
        "cpu_count_for_equivalent": len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else os.cpu_count(),
        "machine_one_core_equivalent_pct": round(machine_busy * (len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else os.cpu_count()), 3) if machine_busy is not None else None,
        "round_wall_ms": {
            "mean": round(1000 * statistics.mean(laps), 3) if laps else None,
            "max": round(1000 * max(laps), 3) if laps else None,
            "p95": round(1000 * percentile(laps, .95), 3) if laps else None,
            "p99": round(1000 * percentile(laps, .99), 3) if laps else None,
        },
        "child_commands": dict(totals),
        "command_wall_seconds": {k: round(v, 4) for k, v in per_command_wall.items()},
        "command_child_cpu_seconds": {k: round(v, 4) for k, v in per_command_childcpu.items()},
        "profile_path": args.profile or None,
        "profile_report_path": args.profile + ".txt" if args.profile else None,
        "measurement_includes_profiler_overhead": bool(args.profile),
    }
    # Single parseable marker even when portbw auto transitions print status.
    print("PORTBW_PROBE_RESULT="+json.dumps(result,ensure_ascii=False,sort_keys=True))
    if errors or len(laps) != args.rounds:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
