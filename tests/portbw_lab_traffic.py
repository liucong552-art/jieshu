#!/usr/bin/env python3
"""UDP echo load for the disposable portbw network namespace test."""
import argparse
import json
import socket
import sys
import time


def serve(port, seconds):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("198.18.0.1", port))
    sock.settimeout(.2)
    count = total = sent = 0
    end = time.monotonic() + seconds
    try:
        while time.monotonic() < end:
            try:
                payload, addr = sock.recvfrom(2048)
            except socket.timeout:
                continue
            count += 1
            total += len(payload)
            try:
                sent += sock.sendto(payload, addr)
            except OSError:
                pass
    finally:
        print(json.dumps({"role": "server", "rx_packets": count,
                          "rx_bytes": total, "tx_bytes": sent}), flush=True)
        sock.close()


def client(port, seconds, mbit):
    payload = bytes(1200)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("198.18.0.2", 0))
    sock.setblocking(False)
    destination = ("198.18.0.1", port)
    interval = len(payload) * 8 / (mbit * 1000000)
    start = time.monotonic()
    end = start + seconds
    next_send = start
    sent = failures = received = 0
    while time.monotonic() < end:
        now = time.monotonic()
        if now >= next_send:
            try:
                sock.sendto(payload, destination)
                sent += 1
            except (BlockingIOError, OSError):
                failures += 1
            next_send += interval
            if next_send < now - interval * 3:
                next_send = now
        try:
            while True:
                b, _ = sock.recvfrom(2048)
                received += len(b)
        except BlockingIOError:
            pass
        time.sleep(.001)
    sock.close()
    print(json.dumps({"role": "client", "tx_packets": sent,
                      "tx_bytes": sent * len(payload), "send_errors": failures,
                      "rx_bytes": received, "seconds": seconds}), flush=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("role", choices=["client", "server"])
    p.add_argument("--port", type=int, default=43000)
    p.add_argument("--seconds", type=float, required=True)
    p.add_argument("--mbit", type=float, default=3)
    args = p.parse_args()
    if not (43000 <= args.port <= 43100 and 0 < args.seconds <= 10000
            and .1 <= args.mbit <= 20):
        p.error("invalid isolation-test bounds")
    if args.role == "server":
        serve(args.port, args.seconds)
    else:
        client(args.port, args.seconds, args.mbit)


if __name__ == "__main__":
    main()
