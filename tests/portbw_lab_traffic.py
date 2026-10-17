#!/usr/bin/env python3
"""Bounded TCP/UDP IPv4/IPv6 echo tests for isolated portbw veth namespaces.

Run the server on 198.18.0.1 / 2001:db8:4300::1 in the outer lab netns,
client on .2 / ::2 in a nested lab netns. No host listener is ever created.
"""
import argparse
import json
import select
import socket
import time

V4 = ("198.18.0.1", "198.18.0.2")
V6 = ("2001:db8:4300::1", "2001:db8:4300::2")
PAYLOAD = bytes(1200)


def emit(result):
    print(json.dumps(result, sort_keys=True), flush=True)


def run_udp(role, port, seconds, mbit, family, addresses):
    sock = socket.socket(family, socket.SOCK_DGRAM)
    count = total = sent = failures = received = 0
    if role == "server":
        sock.bind((addresses[0], port))
        sock.settimeout(.15)
        end = time.monotonic() + seconds
        try:
            while time.monotonic() < end:
                try:
                    payload, addr = sock.recvfrom(65536)
                except socket.timeout:
                    continue
                count += 1
                total += len(payload)
                try:
                    sent += sock.sendto(payload, addr)
                except OSError:
                    failures += 1
        finally:
            emit({"role": "server", "proto": "udp", "rx_packets": count,
                  "rx_bytes": total, "tx_bytes": sent,
                  "send_errors": failures})
            sock.close()
        return

    sock.bind((addresses[1], 0))
    sock.setblocking(False)
    destination = (addresses[0], port)
    interval = len(PAYLOAD) * 8 / (mbit * 1000000)
    started = time.monotonic()
    end = started + seconds
    next_send = started
    try:
        while time.monotonic() < end:
            now = time.monotonic()
            if now >= next_send:
                try:
                    sock.sendto(PAYLOAD, destination)
                    count += 1
                except (BlockingIOError, OSError):
                    failures += 1
                next_send += interval
                if next_send < now - interval * 3:
                    next_send = now
            try:
                while True:
                    result, _ = sock.recvfrom(65536)
                    received += len(result)
            except BlockingIOError:
                pass
            time.sleep(.001)
    finally:
        sock.close()
        emit({"role": "client", "proto": "udp", "tx_packets": count,
              "tx_bytes": count * len(PAYLOAD), "send_errors": failures,
              "rx_bytes": received, "seconds": seconds})


def run_tcp(role, port, seconds, mbit, family, addresses):
    if role == "server":
        listener = socket.socket(family, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((addresses[0], port))
        listener.listen(1)
        listener.settimeout(min(12, seconds))
        accepted = 0
        received = sent = 0
        connection = None
        started = time.monotonic()
        try:
            connection, _ = listener.accept()
            accepted = 1
            connection.settimeout(.4)
            end = started + seconds
            while time.monotonic() < end:
                try:
                    data = connection.recv(65536)
                    if not data:
                        break
                    received += len(data)
                    connection.sendall(data)
                    sent += len(data)
                except socket.timeout:
                    continue
                except (ConnectionResetError, BrokenPipeError):
                    break
        finally:
            if connection:
                connection.close()
            listener.close()
            emit({"role": "server", "proto": "tcp", "accepted": accepted,
                  "rx_bytes": received, "tx_bytes": sent})
        return

    sock = socket.socket(family, socket.SOCK_STREAM)
    sock.settimeout(12)
    sock.connect((addresses[0], port))
    sock.setblocking(False)
    started = time.monotonic()
    end = started + seconds
    next_send = started
    interval = len(PAYLOAD) * 8 / (mbit * 1000000)
    sent = received = errors = 0
    try:
        while time.monotonic() < end:
            now = time.monotonic()
            writable = now >= next_send
            readable, can_write, _ = select.select(
                [sock], [sock] if writable else [], [], .02)
            if can_write:
                try:
                    n = sock.send(PAYLOAD)
                    if n:
                        sent += n
                    next_send += interval
                    if next_send < now - interval * 3:
                        next_send = now
                except BlockingIOError:
                    pass
                except (ConnectionResetError, BrokenPipeError):
                    errors += 1
                    break
            if readable:
                try:
                    data = sock.recv(65536)
                    if not data:
                        break
                    received += len(data)
                except BlockingIOError:
                    pass
    finally:
        sock.close()
        emit({"role": "client", "proto": "tcp", "tx_bytes": sent,
              "rx_bytes": received, "send_errors": errors, "seconds": seconds})


def main():
    p = argparse.ArgumentParser()
    p.add_argument("role", choices=["client", "server"])
    p.add_argument("--proto", choices=["udp", "tcp"], default="udp")
    p.add_argument("--family", choices=["ipv4", "ipv6"], default="ipv4")
    p.add_argument("--port", type=int, default=43000)
    p.add_argument("--seconds", type=float, required=True)
    p.add_argument("--mbit", type=float, default=3)
    args = p.parse_args()
    if not (43000 <= args.port <= 43100 and 0 < args.seconds <= 10000
            and .1 <= args.mbit <= 20):
        p.error("invalid isolation-test bounds")
    family = socket.AF_INET6 if args.family == "ipv6" else socket.AF_INET
    addresses = V6 if args.family == "ipv6" else V4
    if args.proto == "udp":
        run_udp(args.role, args.port, args.seconds, args.mbit, family, addresses)
    else:
        run_tcp(args.role, args.port, args.seconds, args.mbit, family, addresses)


if __name__ == "__main__":
    main()
