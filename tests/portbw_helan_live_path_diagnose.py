#!/usr/bin/env python3
"""Helan-only, read-only live per-port ingress/egress TCP+UDP rate evidence.

Reads exact per-port shared tc police actions, named nft counters, and the
public CLI's auto status. Never touches kernel rules, systemd, VLESS, WG,
or saved policy. Doesn't expose credentials, VLESS URLs or config records.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import time

EXPECTED="f0ebe551e8c0345c045a558b39a8b13523b2be8195255c67db13eec3eff5dc1a"
INDEX=0x6d000000
HEAD=re.compile(r"^\s*action order \d+:\s+police\s+0x([0-9a-f]+)\b",re.I|re.M)
COUNTS=re.compile(r"\bSent\s+(\d+)\s+bytes\s+(\d+)\s+pkt\s+\(dropped\s+(\d+),\s+overlimits\s+(\d+)",re.I)
RATE=re.compile(r"\brate\s+([0-9.]+)\s*([kKmMgG]?)bit\b")
BURST=re.compile(r"\bburst\s+([0-9.]+[kKmMgG]?)b\b")

def command(argv,timeout=15):
    p=subprocess.run(argv,text=True,capture_output=True,timeout=timeout,
                     env={**os.environ,"LC_ALL":"C"})
    if p.returncode:
        raise RuntimeError(f"{argv[0]} read failure (rc={p.returncode}): "+p.stderr[-240:])
    return p.stdout

def tc(port):
    raw=command(["tc","-s","actions","ls","action","police"])
    heads=list(HEAD.finditer(raw))
    indexes={"up":INDEX+2*port,"down":INDEX+2*port+1}
    found={}
    for i,h in enumerate(heads):
        action=int(h.group(1),16)
        if action not in indexes.values():continue
        body=raw[h.start():heads[i+1].start() if i+1<len(heads) else len(raw)]
        cnt=COUNTS.findall(body)
        if len(cnt)!=1:raise RuntimeError(f"cannot parse action 0x{action:x} counters")
        if action in found:raise RuntimeError(f"duplicate action index 0x{action:x}")
        b,p,d,o=map(int,cnt[0])
        r=RATE.search(body)
        k=BURST.search(body)
        found[action]={"bytes":b,"packets":p,"drops":d,"overlimits":o,
                       "rate":(r.group(1)+r.group(2)+"bit") if r else "unknown",
                       "burst":k.group(1)+"b" if k else "unknown"}
    missing=[d for d,k in indexes.items() if k not in found]
    if missing:raise RuntimeError(f"missing expected port {port} actions: {missing}")
    return {d:found[k] for d,k in indexes.items()}

def nft(port):
    output=json.loads(command(["nft","-j","list","table","inet","pbw_policy"]))
    values={}
    names={"up":f"pbw_cu_{port}","down":f"pbw_cd_{port}"}
    for row in output.get("nftables",[]):
        val=row.get("counter")
        if not isinstance(val,dict):continue
        if val.get("name") in names.values():
            if val["name"] in values:raise RuntimeError("duplicate nft named counter")
            values[val["name"]]=val.get("bytes")
    missing=[d for d,k in names.items() if k not in values]
    if missing:raise RuntimeError(f"missing expected port {port} nft counters: {missing}")
    if any(type(n) is not int or n<0 for n in values.values()):
        raise RuntimeError("unusable nft counter byte value")
    return {d:values[k] for d,k in names.items()}

def status(port):
    s=command(["/usr/local/sbin/portbw","auto","status",str(port)])
    rows=[v for v in s.splitlines() if v.startswith(("端口 ","阈值=","up:","down:"))]
    if len(rows)<4:raise RuntimeError("unexpected auto status output")
    for row in rows:print("STATUS "+row,flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--port",type=int,default=40024)
    p.add_argument("--seconds",type=int,default=35)
    a=p.parse_args()
    if not 1<=a.port<=65535 or not 15<=a.seconds<=90:
        p.error("port=1..65535 and seconds=15..90")
    if os.geteuid()!=0 or socket.gethostname()!="helan":
        p.error("REFUSED: root on HELAN only; never run on production")
    program=Path("/usr/local/lib/portbw/portbw.py")
    if not program.is_file() or program.is_symlink() or hashlib.sha256(program.read_bytes()).hexdigest()!=EXPECTED:
        p.error("REFUSED: installed portbw differs from Helan verified burst-fix SHA")
    print(f"LIVE_PATH_DIAG=20261017 READ_ONLY port={a.port} seconds={a.seconds}",flush=True)
    print("DIRECTION: up=client->VPS:40024; down=VPS:40024->client",flush=True)
    print("TC_SEEN: pre-drop police-action bytes (NOT application speed); nft bytes: post-nft-drop named counter",flush=True)
    print("Start your upload/download speed test NOW and keep it active during capture.",flush=True)
    status(a.port)
    nt,nc=time.monotonic(),nft(a.port)
    t,c=time.monotonic(),tc(a.port)
    print("LIMITS "+" | ".join(f"{d} rate={c[d]['rate']} burst={c[d]['burst']}" for d in ("up","down")),flush=True)
    end=t+a.seconds
    status_at=t+5
    elapsed=0.0
    totals={d:{"bytes":0,"drops":0,"overlimits":0} for d in ("up","down")}
    while time.monotonic()<end:
        time.sleep(min(1,max(0,end-time.monotonic())))
        now,cur=time.monotonic(),tc(a.port)
        dt=now-t
        if dt<=0:continue
        out=[]
        for d in ("up","down"):
            dif={key:cur[d][key]-c[d][key] for key in totals[d]}
            if any(val<0 for val in dif.values()):
                out.append(f"{d}:COUNTER_RESET(skip interval)")
            else:
                for key,val in dif.items():totals[d][key]+=val
                out.append(f"{d}:tc_seen={dif['bytes']*8/dt/1e6:.3f}Mbps dropped+{dif['drops']} overlimits+{dif['overlimits']}")
        elapsed=now-(end-a.seconds)
        print(f"TICK t={elapsed:.1f}s "+" | ".join(out),flush=True)
        c,t=cur,now
        if now>=status_at:
            status(a.port)
            status_at+=5
    nft_end=nft(a.port)
    nft_duration=time.monotonic()-nt
    for d in ("up","down"):
        delta=nft_end[d]-nc[d]
        n_rate=f"{delta*8/nft_duration/1e6:.3f}Mbps" if delta>=0 else "RESET"
        tc_avg=totals[d]["bytes"]*8/max(1,elapsed)/1e6
        print(f"RESULT {d}: tc_seen_avg={tc_avg:.3f}Mbps tc_drop_total={totals[d]['drops']} "
              f"tc_overlimit_total={totals[d]['overlimits']} nft_counted_avg={n_rate}",flush=True)
    print("READ_ONLY_PASS: nft/tc/systemd/VLESS/WG/portbw policies untouched.",flush=True)

if __name__=="__main__":
    main()
