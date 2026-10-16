#!/usr/bin/env python3
"""Read-only reboot recovery probe for a disposable VLESS node.

Exit 0 only when the managed service is active AND the configured local
listening socket is accepting connections. A timeout exits nonzero and prints
diagnostics, without restarting units or changing nftables/quotas.
"""
import argparse
import pathlib
import re
import socket
import subprocess
import time

def command(*args):
    result = subprocess.run(args, text=True, capture_output=True, timeout=15)
    return result.returncode, (result.stdout + result.stderr).strip()

def probe(port, source="127.0.0.2"):
    with socket.socket() as sock:
        sock.settimeout(1.5)
        sock.bind((source, 0))
        try:
            sock.connect(("127.0.0.1", port))
            return True
        except OSError:
            return False

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--node", required=True, help="disposable name, e.g. svpersist")
    ap.add_argument("--timeout", type=int, default=150)
    args = ap.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,35}", args.node):
        ap.error("invalid disposable node name")
    if not 10 <= args.timeout <= 300:
        ap.error("timeout must be 10..300 seconds")
    tag = "vless-temp-" + args.node
    meta = pathlib.Path("/var/lib/vless-reality/temp") / (tag + ".env")
    if not meta.is_file():
        print(f"FAIL: missing {meta}")
        return 2
    fields = dict(line.split("=", 1) for line in meta.read_text().splitlines()
                  if "=" in line and not line.startswith("#"))
    port = int(fields["PORT"])
    if not 1 <= port <= 65535:
        print("FAIL: invalid port")
        return 2

    deadline = time.monotonic() + args.timeout
    last_state = ""
    while time.monotonic() < deadline:
        _, state = command("systemctl", "is-active", tag + ".service")
        if state != last_state:
            print(f"node={tag} service={state} elapsed={args.timeout - (deadline-time.monotonic()):.1f}s", flush=True)
            last_state = state
        if state == "active" and probe(port):
            print(f"PASS: {tag} active and TCP port {port} listening")
            return 0
        time.sleep(3)
    print(f"FAIL: {tag} did not restore within {args.timeout} seconds")
    for label, cmd in [
        ("UNIT", ("systemctl", "status", tag + ".service", "--no-pager", "-l")),
        ("RESTORE", ("systemctl", "status", "vless-managed-restore.service", "--no-pager", "-l")),
        ("UNIT-JOURNAL", ("journalctl", "-b", "-u", tag + ".service", "--no-pager", "-n", "60")),
        ("RESTORE-JOURNAL", ("journalctl", "-b", "-u", "vless-managed-restore.service", "--no-pager", "-n", "60")),
        ("LISTEN", ("ss", "-ltn")),
    ]:
        try:
            _, output = command(*cmd)
            print(f"=== {label} ===\n{output[-5000:]}", flush=True)
        except Exception as exc:
            print(f"=== {label}: diagnostic failed ({exc}) ===")
    return 1

if __name__ == "__main__":
    raise SystemExit(main())
