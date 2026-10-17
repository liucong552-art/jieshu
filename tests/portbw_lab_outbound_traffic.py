#!/usr/bin/env python3
"""True one-way UDP traffic across disposable portbw veth pair.

Unlike an echo server, this sends packets exclusively OUT of the portbw-side
interface with source port 43000. This isolates the tc egress ('down') policer.
Only use inside the lab network namespaces created by portbw semantic runner.
"""
import argparse
import json
import socket
import time


ADDRESS={"ipv4":("198.18.0.1","198.18.0.2"),
         "ipv6":("2001:db8:4300::1","2001:db8:4300::2")}
PAYLOAD=bytes(1200)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("role",choices=("source","sink"))
    p.add_argument("--family",choices=("ipv4","ipv6"),required=True)
    p.add_argument("--source-port",type=int,default=43000)
    p.add_argument("--destination-port",type=int,default=43080)
    p.add_argument("--seconds",type=float,required=True)
    p.add_argument("--mbit",type=float,default=3.0)
    args=p.parse_args()
    if not (43000<=args.source_port<=43100 and 43000<=args.destination_port<=43100
            and 0<args.seconds<=240 and 0.1<=args.mbit<=20):
        p.error("out-of-bounds lab traffic parameters")
    addresses=ADDRESS[args.family]
    family=socket.AF_INET6 if args.family=="ipv6" else socket.AF_INET
    sock=socket.socket(family,socket.SOCK_DGRAM)
    total=packets=errors=0
    start=time.monotonic()
    deadline=start+args.seconds
    try:
        if args.role=="source":
            sock.bind((addresses[0],args.source_port))
            sock.setblocking(False)
            step=len(PAYLOAD)*8/(args.mbit*1_000_000)
            next_send=start
            destination=(addresses[1],args.destination_port)
            while time.monotonic()<deadline:
                now=time.monotonic()
                if now>=next_send:
                    try:
                        n=sock.sendto(PAYLOAD,destination)
                        if n!=len(PAYLOAD):
                            raise RuntimeError("short UDP send in lab")
                        total+=n;packets+=1
                    except BlockingIOError:
                        errors+=1
                    next_send+=step
                    if next_send<now-3*step:
                        next_send=now
                time.sleep(.0005)
        else:
            sock.bind((addresses[1],args.destination_port))
            sock.settimeout(.2)
            while time.monotonic()<deadline:
                try:
                    data,_=sock.recvfrom(65536)
                    total+=len(data);packets+=1
                except socket.timeout:
                    continue
    finally:
        sock.close()
        print("OUTBOUND_TRAFFIC="+json.dumps({
            "role":args.role,"family":args.family,
            "source_port":args.source_port,
            "destination_port":args.destination_port,
            "bytes":total,"packets":packets,"errors":errors,
            "seconds":args.seconds
        },sort_keys=True),flush=True)


if __name__=="__main__":
    main()
