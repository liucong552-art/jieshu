#!/usr/bin/env python3
"""20/40 Mbps TCP GOODPUT comparison, not just policing compliance.

For Helan disposable netns only. bench mode MUST run under unshare --net.
The sender runs in a second nested netns. No host interface touched.
No changes to the pinned algorithm or any installed portbw service.
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
CONTROL=43080
SENDER_ADDR="198.18.0.2"
SERVER_ADDR="198.18.0.1"
A_SHA="69058c8069e78d902c4814e1300c5aa38e2b91340f936cdb9cdc09a14936f359"
B_SHA="52eaa233f831236973dff6b43d8f320659b29226939ee5ba132d2b9cf31eebfb"
CHUNK=b"t"*16384


def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def receiver(args):
    sock=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
    sock.bind((SERVER_ADDR,args.port))
    sock.listen(1)
    sock.settimeout(8)
    conn=None
    total=steady=0
    start=end=None
    try:
        conn,_=sock.accept()
        conn.settimeout(2)
        start=time.monotonic()
        deadline=start+args.seconds+4
        while time.monotonic()<deadline:
            try:
                data=conn.recv(65536)
            except socket.timeout:
                continue
            if not data:break
            now=time.monotonic()
            total+=len(data)
            if now-start>=args.warmup:steady+=len(data)
        end=time.monotonic()
    finally:
        if conn:conn.close()
        sock.close()
    actual=max(.001,(end-start) if start is not None else 0)
    steady_window=max(.001,actual-args.warmup)
    print("GOODPUT_RECEIVER="+json.dumps({
        "total_bytes":total,"steady_bytes":steady,
        "elapsed":round(actual,3),
        "avg_mbps":round(total*8/actual/1e6,3),
        "steady_mbps":round(steady*8/steady_window/1e6,3)
    },sort_keys=True),flush=True)


def sender(args):
    sock=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    sock.settimeout(10)
    total=0
    try:
        sock.connect((SERVER_ADDR,args.port))
        started=time.monotonic()
        end=started+args.seconds
        while time.monotonic()<end:
            try:
                n=sock.send(CHUNK)
                if n<=0:break
                total+=n
            except socket.timeout:
                break
            except (BrokenPipeError,ConnectionResetError):
                break
        duration=time.monotonic()-started
    finally:
        sock.close()
    print("GOODPUT_SENDER="+json.dumps({
        "socket_accepted_bytes":total,"seconds":round(duration,3)
    },sort_keys=True),flush=True)


def police(mod):
    body=mod.tc_action_block(mod.tc_police_index(PORT,"up"))
    if not body:raise RuntimeError("shared up police action missing")
    hits=re.findall(r"\bSent\s+([0-9]+)\s+bytes\s+([0-9]+)\s+pkt\s+\(dropped\s+([0-9]+),\s+overlimits\s+([0-9]+)",body)
    if len(hits)!=1:raise RuntimeError("unparseable police statistics")
    return dict(zip(("bytes","packets","drops","overlimits"),map(int,hits[0])))


def run_once(args,child,mod,root,tag,port):
    results=root/"results"/"tcp_goodput"
    results.mkdir(parents=True,exist_ok=True)
    rpath=results/f"{args.version}_{tag}_receiver.log"
    spath=results/f"{args.version}_{tag}_sender.log"
    before=police(mod)
    env={**os.environ,"PORTBW_LAB_ACK":"isolated-netns-only"}
    receiver_cmd=[sys.executable,"-B",str(Path(__file__).resolve()),"receiver",
                  "--port",str(port),"--seconds",str(args.seconds),
                  "--warmup",str(args.warmup)]
    sender_cmd=["nsenter","-t",str(child.pid),"-n",sys.executable,"-B",
                str(Path(__file__).resolve()),"sender",
                "--port",str(port),"--seconds",str(args.seconds),
                "--warmup",str(args.warmup)]
    p=q=None
    try:
        with rpath.open("w") as rf,spath.open("w") as sf:
            p=subprocess.Popen(receiver_cmd,stdout=rf,stderr=subprocess.STDOUT,env=env)
            time.sleep(.4)
            q=subprocess.Popen(sender_cmd,stdout=sf,stderr=subprocess.STDOUT,env=env)
            try:
                q.wait(timeout=args.seconds+16)
                p.wait(timeout=args.seconds+16)
            except subprocess.TimeoutExpired:
                raise RuntimeError("TCP test sender/receiver timed out")
        if p.returncode or q.returncode:
            raise RuntimeError(f"TCP test failed {tag}: {rpath.read_text()[-800:]} {spath.read_text()[-800:]}")
        text=rpath.read_text().splitlines()
        obj=json.loads(next(x.split("GOODPUT_RECEIVER=",1)[1] for x in text if x.startswith("GOODPUT_RECEIVER=")))
        after=police(mod)
        delta={k:after[k]-before[k] for k in before}
        if any(x<0 for x in delta.values()):
            raise RuntimeError("tc police counters reset during TCP test")
        result={
            "version":args.version,"scenario":tag,
            "port":port,"configured_up_mbps":None if port==CONTROL else int(tag),
            "receive":obj,"up_police_delta":delta
        }
        print("TCP_GOODPUT="+json.dumps(result,sort_keys=True),flush=True)
        return result
    finally:
        for proc in (p,q):
            if proc and proc.poll() is None:
                proc.kill();proc.wait(timeout=3)


def bench(args):
    root=Path(args.root).resolve()
    if root.parent!=Path("/tmp") or not root.name.startswith("portbw-cpu-"):
        raise SystemExit("REFUSED: private lab root required")
    runner=load(root/"tools"/"portbw_ab_lab_runner.py","tcp_goodput_runner")
    runner.isolated()
    src=root/args.version/"portbw.py"
    expected={"A":A_SHA,"B":B_SHA}[args.version]
    if hashlib.sha256(src.read_bytes()).hexdigest()!=expected:
        raise RuntimeError("pinned source checksum mismatch")
    child=None
    try:
        child,_=runner.set_up_link()
        base=str(root)
        os.environ.update(PORTBW_STATE=base+"/state",
                          PORTBW_CONF=base+"/config",
                          PORTBW_LOCK=base+"/locks/manager.lock",
                          PORTBW_RUN=base+"/run",PORTBW_UNITS=base+"/units")
        mod=runner.module(src)
        cfg={"iface":runner.IFACE,"tc_enabled":True,"version":2}
        mod.write_json(mod.CONF/"config.json",cfg)
        mod.tc_prepare(runner.IFACE)
        runner.prepare_ports(mod,cfg,1,False)
        runner.audit_records(mod,cfg,[PORT])
        if args.delay_ms:
            # Child netns ONLY. Never host root qdisc. ACKs remain unmodified
            # while client-to-server upload experiences configurable RTT.
            cmd=["nsenter","-t",str(child.pid),"-n","tc","qdisc","replace",
                 "dev",runner.PEER,"root","netem",
                 "delay",str(args.delay_ms)+"ms"]
            subprocess.run(cmd,check=True,text=True,capture_output=True)
        experiments=[("control",CONTROL),("40",PORT),("20",PORT)]
        results=[]
        for tag,port in experiments:
            if port==PORT:
                mbps=int(tag)
                mod.commit(PORT,125000*mbps,125000*40,cfg)
                runner.audit_records(mod,cfg,[PORT])
            results.append(run_once(args,child,mod,root,tag,port))
        summary={r["scenario"]:r["receive"]["steady_mbps"] for r in results}
        print("TCP_GOODPUT_SUMMARY="+json.dumps({"version":args.version,
             "delay_ms":args.delay_ms,"steady_mbps":summary},sort_keys=True),flush=True)
        path=root/"results"/f"goodput_{args.version}.json"
        path.write_text(json.dumps(results,indent=2)+"\n",encoding="utf-8")
        runner.audit_records(mod,cfg,[PORT])
    finally:
        if child:
            child.terminate()
            try:child.wait(timeout=3)
            except subprocess.TimeoutExpired:child.kill();child.wait()


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("role",choices=("bench","sender","receiver"))
    ap.add_argument("--root")
    ap.add_argument("--version",choices=("A","B"),default="B")
    ap.add_argument("--port",type=int,choices=(PORT,CONTROL),default=PORT)
    ap.add_argument("--seconds",type=int,default=24)
    ap.add_argument("--warmup",type=int,default=4)
    ap.add_argument("--delay-ms",type=int,default=0)
    args=ap.parse_args()
    if not 12<=args.seconds<=90 or not 1<=args.warmup<=args.seconds//3 or not 0<=args.delay_ms<=75:
        ap.error("invalid bounded test duration, warmup or RTT")
    if args.role=="bench":
        if not args.root:ap.error("--root required")
        bench(args)
    else:
        if os.environ.get("PORTBW_LAB_ACK")!="isolated-netns-only":
            raise SystemExit("REFUSED: lab marker missing")
        if os.stat("/proc/self/ns/net").st_ino==os.stat("/proc/1/ns/net").st_ino:
            raise SystemExit("REFUSED: host namespace")
        if args.role=="receiver":receiver(args)
        else:sender(args)


if __name__=="__main__":
    main()
