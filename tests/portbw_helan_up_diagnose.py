#!/usr/bin/env python3
"""Read-only Helan per-port tc police and portbw auto-trigger diagnostic.

No nft/tc/systemd/config mutation; no VLESS URLs, credentials, or raw policy
JSON are printed. Read-only commands: tc -s actions ls action police,
portbw auto status <port>. The 'Sent' counter is the action-SEEN byte volume,
including attempted bytes later dropped, not TCP goodput.
"""
import argparse
import hashlib
import os
import re
import socket
import subprocess
import time
from pathlib import Path

EXPECTED_SHA="52eaa233f831236973dff6b43d8f320659b29226939ee5ba132d2b9cf31eebfb"
BASE_INDEX=0x6d000000
HEADER=re.compile(r"^\s*action order [0-9]+:\s+police\s+0x([0-9a-f]+)\b",re.I|re.M)
COUNTER=re.compile(r"\bSent\s+([0-9]+)\s+bytes\s+([0-9]+)\s+pkt\s+\(dropped\s+([0-9]+),\s+overlimits\s+([0-9]+)",re.I)

def extract(text,port):
    heads=list(HEADER.finditer(text))
    targets={"up":BASE_INDEX+port*2,"down":BASE_INDEX+port*2+1}
    blocks={}
    for i,m in enumerate(heads):
        idx=int(m.group(1),16)
        if idx not in targets.values():continue
        body=text[m.start():heads[i+1].start() if i+1<len(heads) else len(text)]
        count=COUNTER.findall(body)
        if len(count)!=1:raise ValueError(f"unable to parse police counter index 0x{idx:x}")
        if idx in blocks:raise ValueError(f"duplicate police index 0x{idx:x}")
        blocks[idx]=dict(zip(("bytes","packets","drops","overlimits"),map(int,count[0])))
    if set(blocks)!=set(targets.values()):
        absent=[d for d,i in targets.items() if i not in blocks]
        raise ValueError(f"missing managed tc police action(s) for {absent}")
    return {d:blocks[idx] for d,idx in targets.items()}

def read_action(port):
    p=subprocess.run(["tc","-s","actions","ls","action","police"],
                     text=True,capture_output=True,timeout=12,
                     env=dict(os.environ,LC_ALL="C"))
    if p.returncode:raise RuntimeError("tc action read failed: "+p.stderr[-600:])
    t=time.monotonic()
    return t,extract(p.stdout,port)

def show_status(port):
    p=subprocess.run(["/usr/local/sbin/portbw","auto","status",str(port)],
                     text=True,capture_output=True,timeout=15)
    if p.returncode:raise RuntimeError("portbw status failed: "+p.stderr[-600:])
    # Display only diagnostic lines, not arbitrary free-form saved metadata.
    for line in p.stdout.splitlines():
        if line.startswith(("up:","down:","阈值=","端口 ")):
            print("STATUS "+line,flush=True)

def main():
    p=argparse.ArgumentParser(description="Read-only upload/down trigger diagnostics for Helan")
    p.add_argument("--port",type=int,required=True)
    p.add_argument("--seconds",type=int,default=25)
    args=p.parse_args()
    if not 1<=args.port<=65535 or not 10<=args.seconds<=60:
        p.error("port must be 1..65535; seconds must be 10..60")
    if os.geteuid()!=0 or socket.gethostname()!="helan":
        p.error("Helan root-only, refuses production hosts")
    target=Path("/usr/local/lib/portbw/portbw.py")
    if not target.is_file() or target.is_symlink():
        p.error("managed portbw not installed as a regular file")
    if hashlib.sha256(target.read_bytes()).hexdigest()!=EXPECTED_SHA:
        p.error("installed version differs from verified optimized portbw candidate")
    print(f"DIAGNOSTIC_VERSION=20261017-UP-READONLY PORT={args.port} SECONDS={args.seconds}",flush=True)
    print("DIRECTION up=client->VPS inbound; down=VPS->client outbound",flush=True)
    print("COUNTER_SENT=police-action-seen bytes; not necessarily delivered TCP payload",flush=True)
    print("Start a client UPLOAD test on this port during these samples.",flush=True)
    show_status(args.port)
    before_t,before=read_action(args.port)
    totals={d:{"overlimits":0,"drops":0,"bytes":0} for d in before}
    deadline=before_t+args.seconds
    next_status=before_t+5
    while time.monotonic()<deadline:
        time.sleep(max(0,min(1,deadline-time.monotonic())))
        now,snapshot=read_action(args.port)
        dt=now-before_t
        if dt<=0:continue
        out=[]
        for d in ("up","down"):
            deltas={key:snapshot[d][key]-before[d][key] for key in ("bytes","drops","overlimits")}
            if any(n<0 for n in deltas.values()):
                print(f"RESET direction={d} (action replaced/counters reset; interval discarded)",flush=True)
                continue
            for k,val in deltas.items():totals[d][k]+=val
            mbps=deltas["bytes"]*8/dt/1e6
            out.append(f"{d}={mbps:.3f}Mbps seen,"
                       f"drops+{deltas['drops']},overlimits+{deltas['overlimits']}")
        print(f"SAMPLE elapsed={args.seconds-max(0,deadline-now):.1f}s "+" | ".join(out),flush=True)
        before_t,before=now,snapshot
        if now>=next_status:
            show_status(args.port)
            next_status+=5
    print("TOTALS "+str(totals),flush=True)
    print("No kernel rules, configs, or service state were modified.",flush=True)

if __name__=="__main__":
    main()
