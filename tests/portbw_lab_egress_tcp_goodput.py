#!/usr/bin/env python3
"""Helan-only isolated real TCP EGRESS (server-to-client) GOODPUT test.

No host interfaces, systemd units, live VLESS/WG, or real policy records changed.
The server TCP socket is bound to port 43000 in the outer disposable namespace;
receiver is in a second disposable namespace. Compare original egress burst with
bounded experimental egress bursts, keeping nft+tc BOTH active throughout.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time

PORT=43000
CONTROL_PORT=43080
DEST_PORT=43100
SHA="f0ebe551e8c0345c045a558b39a8b13523b2be8195255c67db13eec3eff5dc1a"
SERVER="198.18.0.1"
CLIENT="198.18.0.2"
PAYLOAD=b"e"*16384
COUNT=re.compile(r"\bSent\s+(\d+)\s+bytes\s+(\d+)\s+pkt\s+\(dropped\s+(\d+),\s+overlimits\s+(\d+)",re.I)

def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

def receiver(a):
    s=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
    s.bind((CLIENT,DEST_PORT));s.listen(1);s.settimeout(10)
    conn=None
    total=steady=0
    start=end=None
    try:
        conn,_=s.accept();conn.settimeout(2)
        start=time.monotonic()
        while time.monotonic()<start+a.seconds+4:
            try:data=conn.recv(65536)
            except socket.timeout:continue
            if not data:break
            total+=len(data)
            if time.monotonic()-start>=a.warmup:steady+=len(data)
        end=time.monotonic()
    finally:
        if conn:conn.close()
        s.close()
    dt=max(.001,end-start)
    print("EGRESS_RECEIVER="+json.dumps({
        "total_bytes":total,"elapsed":round(dt,3),
        "steady_mbps":round(steady*8/max(.001,dt-a.warmup)/1e6,3)
    },sort_keys=True),flush=True)

def sender(a):
    s=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
    s.settimeout(10)
    total=0
    try:
        s.bind((SERVER,a.source_port));s.connect((CLIENT,DEST_PORT))
        end=time.monotonic()+a.seconds
        while time.monotonic()<end:
            try:
                n=s.send(PAYLOAD)
                if n<=0:break
                total+=n
            except (socket.timeout,BrokenPipeError,ConnectionResetError):break
    finally:s.close()
    print("EGRESS_SENDER="+json.dumps({"socket_accepted_bytes":total}),flush=True)

def action(mod):
    body=mod.tc_action_block(mod.tc_police_index(PORT,"down"))
    if not body:raise RuntimeError("shared egress tc police missing")
    x=COUNT.findall(body)
    if len(x)!=1:raise RuntimeError("unparseable egress police counters")
    return dict(zip(("bytes","packets","drops","overlimits"),map(int,x[0])))

def transfer(a,root,child,mod,tag,port):
    dst=root/"results"/"egress_tcp"
    dst.mkdir(parents=True,exist_ok=True)
    rp=dst/f"{a.mode}_{tag}_receiver.log"
    sp=dst/f"{a.mode}_{tag}_sender.log"
    before=action(mod)
    recv=[ "nsenter","-t",str(child.pid),"-n",sys.executable,"-B",
           str(Path(__file__).resolve()),"receiver","--seconds",str(a.seconds),
           "--warmup",str(a.warmup)]
    send=[sys.executable,"-B",str(Path(__file__).resolve()),"sender",
          "--source-port",str(port),"--seconds",str(a.seconds),
          "--warmup",str(a.warmup)]
    ps=[]
    try:
        with rp.open("w") as rf,sp.open("w") as sf:
            ps.append(subprocess.Popen(recv,stdout=rf,stderr=subprocess.STDOUT))
            time.sleep(.3)
            ps.append(subprocess.Popen(send,stdout=sf,stderr=subprocess.STDOUT))
            for p in reversed(ps):p.wait(timeout=a.seconds+18)
        if any(p.returncode for p in ps):
            raise RuntimeError("traffic failed: "+rp.read_text()[-600:]+sp.read_text()[-600:])
        rr=next(x.split("EGRESS_RECEIVER=",1)[1] for x in rp.read_text().splitlines() if x.startswith("EGRESS_RECEIVER="))
        value=json.loads(rr)
        after=action(mod)
        diff={k:after[k]-before[k] for k in before}
        if any(n<0 for n in diff.values()):raise RuntimeError("egress police was recreated within trial")
        out={"mode":a.mode,"scenario":tag,"receiver":value,"egress_police_delta":diff}
        print("EGRESS_TCP="+json.dumps(out,sort_keys=True),flush=True)
        return out
    finally:
        for p in ps:
            if p.poll() is None:
                p.kill();p.wait(timeout=3)

def bench(a):
    root=Path(a.root).resolve()
    if root.parent!=Path("/tmp") or not root.name.startswith("portbw-cpu-"):
        raise RuntimeError("private test root required")
    runner=load(root/"tools"/"portbw_ab_lab_runner.py","egress_runner")
    runner.isolated()
    source=root/"B"/"portbw.py"
    if hashlib.sha256(source.read_bytes()).hexdigest()!=SHA:raise RuntimeError("pinned portbw SHA mismatch")
    child=None
    try:
        child,_=runner.set_up_link()
        os.environ.update(
            PORTBW_STATE=str(root/"state_"+a.mode),
            PORTBW_CONF=str(root/"config_"+a.mode),
            PORTBW_LOCK=str(root/"lock_"+a.mode/"manager.lock"),
            PORTBW_RUN=str(root/"run_"+a.mode),
            PORTBW_UNITS=str(root/"units_"+a.mode))
        mod=runner.module(source)
        # Only adjust egress/down in this imported disposable module.
        orig=mod.tc_burst_kb
        if a.mode!="original":
            def experimental(rate,direction="down"):
                if direction=="down":
                    if a.mode=="half_second":
                        return max(64,min(1024,(rate+2047)//2048))
                    if a.mode=="one_meg":
                        return 1024
                return orig(rate,direction)
            mod.tc_burst_kb=experimental
        cfg={"iface":runner.IFACE,"tc_enabled":True,"version":2}
        mod.write_json(mod.CONF/"config.json",cfg)
        mod.tc_prepare(runner.IFACE)
        runner.prepare_ports(mod,cfg,1,False)
        runner.audit_records(mod,cfg,[PORT])
        results=[transfer(a,root,child,mod,"control",CONTROL_PORT)]
        for n in (40,20,5):
            # Upload is zero; ONLY this port's source/egress traffic is limited.
            mod.commit(PORT,0,n*125000,cfg)
            runner.audit_records(mod,cfg,[PORT])
            results.append(transfer(a,root,child,mod,str(n),PORT))
        print("EGRESS_TCP_SUMMARY="+json.dumps({
            "mode":a.mode,"steady_mbps":{x["scenario"]:x["receiver"]["steady_mbps"] for x in results},
            "seconds":a.seconds,"source_sha256":SHA
        },sort_keys=True),flush=True)
        runner.audit_records(mod,cfg,[PORT])
        outfile=root/"results"/f"egress_goodput_{a.mode}.json"
        outfile.write_text(json.dumps(results,indent=2)+"\n",encoding="utf-8")
    finally:
        if child:
            child.terminate()
            try:child.wait(timeout=3)
            except subprocess.TimeoutExpired:child.kill();child.wait()

def main():
    p=argparse.ArgumentParser()
    p.add_argument("role",choices=["bench","sender","receiver"])
    p.add_argument("--root")
    p.add_argument("--mode",choices=["original","half_second","one_meg"],default="original")
    p.add_argument("--source-port",type=int,choices=[PORT,CONTROL_PORT],default=PORT)
    p.add_argument("--seconds",type=int,default=20)
    p.add_argument("--warmup",type=int,default=4)
    a=p.parse_args()
    if not 15<=a.seconds<=75 or not 1<=a.warmup<=a.seconds//3:
        p.error("duration outside bounded test")
    if a.role=="bench":
        if not a.root:p.error("private root required")
        if os.geteuid()!=0 or socket.gethostname()!="helan":
            p.error("REFUSED: Helan-only outer netns experiment")
        bench(a)
    else:
        if os.environ.get("PORTBW_LAB_ACK")!="isolated-netns-only":
            p.error("REFUSED: lab acknowledgement missing")
        if os.stat("/proc/self/ns/net").st_ino==os.stat("/proc/1/ns/net").st_ino:
            p.error("REFUSED: host netns")
        if a.role=="receiver":receiver(a)
        else:sender(a)

if __name__=="__main__":main()
