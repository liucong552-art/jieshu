#!/usr/bin/env python3
"""No side effects: AST validation of the PINNED Helan semantic harness.

Rejects obsolete 2-arg TCP shared-cap gates before any netns/rule setup.
"""
from __future__ import annotations
import ast
from pathlib import Path
import sys


def validate_harness(source: str):
    tree = ast.parse(source, filename="portbw_lab_semantics.py")
    functions = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    required = ("check_shared_cap", "police_stats", "police_delta", "aggregate")
    missing = [n for n in required if n not in functions]
    if missing:
        raise ValueError(f"missing required limit-verification functions: {missing}")

    signature = [a.arg for a in functions["check_shared_cap"].args.args]
    if signature != ["scenario", "sample", "pressure"]:
        raise ValueError(f"obsolete shared cap signature: {signature}")

    checker = functions["check_shared_cap"]
    checker_names = {n.id for n in ast.walk(checker) if isinstance(n, ast.Name)}
    if "pressure" not in checker_names:
        raise ValueError("shared cap gate does not use real kernel pressure")

    # Check that the aggregate path actually computes and passes pressure.
    calls = [n for n in ast.walk(functions["aggregate"])
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
    for name in ("flow_batch", "police_stats", "police_delta", "check_shared_cap"):
        if not any(n.func.id == name for n in calls):
            raise ValueError(f"aggregate did not call {name}")
    gate_calls = [n for n in calls if n.func.id == "check_shared_cap"]
    if len(gate_calls) != 1 or len(gate_calls[0].args) != 3:
        raise ValueError("aggregate must pass kernel pressure to shared-cap gate")

    # A stale v2 generator's generic UDP threshold erroneously rejects TCP
    # congestion-control/backpressure, even when both transports participate.
    aggregate_source = ast.get_source_segment(source, functions["aggregate"]) or ""
    if 'if src["offered_mbps"]<2.3:' in aggregate_source:
        raise ValueError("obsolete UDP offered-load check applies to TCP")


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: verify_portbw_semantic_harness.py <semantics.py>")
    source = Path(sys.argv[1]).read_text(encoding="utf-8")
    try:
        validate_harness(source)
    except (SyntaxError, ValueError) as error:
        raise SystemExit(f"REFUSED: semantic harness mismatch: {error}") from error
    print("HARNESS_GATE=CORRECTED_TCP_BACKPRESSURE")
    print("HARNESS_GATE=ACTUAL_TC_POLICE_COUNTERS")
    print("HARNESS_GATE=AST_VERSION_VERIFIED")


if __name__ == "__main__":
    main()
