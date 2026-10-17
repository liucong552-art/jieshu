#!/usr/bin/env python3
"""Kernel semantics: concurrent shared police, recovery and fail-closed.

Launched ONLY from portbw_ab_lab_runner.py inside its disposable netns.
This is NOT a CPU benchmark (client/server packet-processing CPU is included).
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time


PORT = 43000
CONTROL = 43080
INTERFACE = "pbwl0"
TRAFFIC = Path(__file__).with_name("portbw_lab_traffic.py")


def run(*cmd, **kwargs):
    return subprocess.run(cmd, check=True, text=True, **kwargs)


def guard():
    if os.environ.get("PORTBW_LAB_ACK") != "isolated-netns-only":
        raise SystemExit("REFUSED: missing explicit test acknowledgement")
    if os.geteuid() or os.stat("/proc/self/ns/net").st_ino == os.stat("/proc/1/ns/net").st_ino:
        raise SystemExit("REFUSED: not in disposable root netns")
    links=json.loads(run("ip","-j","link",stdout=subprocess.PIPE).stdout)
    names={x.get("ifname") for x in links}
    if INTERFACE not in names or "eth0" in names or "wg-nat" in names:
        raise SystemExit("REFUSED: lab interface absent or production interface visible")
    if not os.environ.get("PORTBW_STATE","").startswith("/tmp/portbw-cpu-"):
        raise SystemExit("REFUSED: portbw state must be in private /tmp lab")


def load(path):
    spec=importlib.util.spec_from_file_location("portbw_semantics_target",path)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def parse_log(path,kind):
    body=path.read_text(encoding="utf-8") if path.exists() else ""
    try:
        return json.loads(body.strip().splitlines()[-1])
    except (IndexError,ValueError) as exc:
        raise RuntimeError(f"{kind} failed: {body[-2000:]!r}") from exc


def flow_batch(pid,root,label,flows,port,seconds):
    """Measure the sum of bytes delivered to a single destination port."""
    logs=root / "results" / "semantics"
    logs.mkdir(parents=True,exist_ok=True)
    workers=[]
    results=[]
    try:
        for i,(proto,family) in enumerate(flows):
            name=f"{label}_{i}_{proto}_{family}"
            serverpath=logs / (name+"_server.log")
            fp=serverpath.open("w")
            p=subprocess.Popen([sys.executable,str(TRAFFIC),"server",
                                "--proto",proto,"--family",family,
                                "--port",str(port),"--seconds",str(seconds+4)],
                               stdout=fp,stderr=subprocess.STDOUT)
            workers.append((p,fp,serverpath,"server"))
        time.sleep(.6)
        for i,(proto,family) in enumerate(flows):
            name=f"{label}_{i}_{proto}_{family}"
            path=logs / (name+"_client.log")
            fp=path.open("w")
            p=subprocess.Popen(["nsenter","-t",str(pid),"-n",sys.executable,str(TRAFFIC),
                                "client","--proto",proto,"--family",family,
                                "--port",str(port),"--seconds",str(seconds),
                                "--mbit","3"],stdout=fp,stderr=subprocess.STDOUT)
            workers.append((p,fp,path,"client"))
        for p,fp,path,role in workers:
            try:
                p.wait(timeout=seconds+14)
            except subprocess.TimeoutExpired:
                p.kill();p.wait()
                raise RuntimeError(f"{label} {role} timed out: {path}")
            fp.flush()
            if p.returncode:
                raise RuntimeError(f"{label} {role} exited {p.returncode}: {path.read_text()[-2000:]}")
        sent=received=0
        flow_report=[]
        for i,(proto,family) in enumerate(flows):
            name=f"{label}_{i}_{proto}_{family}"
            server=parse_log(logs/(name+"_server.log"),"server")
            client=parse_log(logs/(name+"_client.log"),"client")
            if client.get("tx_bytes",0)<=0 or server.get("rx_bytes",0)<=0:
                raise RuntimeError(f"{label}: zero delivered data in {proto}/{family}: {server}, {client}")
            sent+=client["tx_bytes"]
            received+=server["rx_bytes"]
            flow_report.append({"proto":proto,"family":family,
                                "offered_mbps":round(client["tx_bytes"]*8/seconds/1e6,3),
                                "delivered_mbps":round(server["rx_bytes"]*8/seconds/1e6,3)})
        data={"label":label,"port":port,"seconds":seconds,
              "offered_mbps":round(sent*8/seconds/1e6,3),
              "delivered_mbps":round(received*8/seconds/1e6,3),
              "flows":flow_report}
        print("SEMANTIC_FLOW="+json.dumps(data,sort_keys=True),flush=True)
        return data
    finally:
        for p,fp,_,_ in workers:
            if p.poll() is None:
                p.terminate()
                try:p.wait(timeout=2)
                except subprocess.TimeoutExpired:p.kill();p.wait()
            fp.close()


def aggregate(mod,config,pid,root,label,seconds):
    for scenario,flows in (
        ("udp-ipv4-ipv6",[("udp","ipv4"),("udp","ipv6")]),
        ("tcp-udp-ipv4",[("tcp","ipv4"),("udp","ipv4")]),
        ("tcp-udp-ipv6",[("tcp","ipv6"),("udp","ipv6")]),
    ):
        # Assert the two protocols/families do not get TWO independent 1 Mbps
        # policers. Per-flow receive cannot be extrapolated to aggregation.
        mod.reconcile(config,monitor=False)
        src=flow_batch(pid,root,f"{label}_{scenario}",flows,PORT,seconds)
        if src["offered_mbps"]<2.3:
            raise RuntimeError(f"{label}/{scenario}: inadequate combined offered load: {src}")
        if not .05 < src["delivered_mbps"] < 1.35:
            raise RuntimeError(f"{label}/{scenario}: NOT a shared 1 Mbps cap: {src}")
        for flow in src["flows"]:
            if flow["delivered_mbps"]<=0:
                raise RuntimeError(f"{label}/{scenario}: lost a required protocol/family: {src}")
    # Without any rules on control port, prove that the test generator and
    # veth link can deliver substantially more than the configured 1 Mbps.
    control=flow_batch(pid,root,f"{label}_unpoliced_control",
                       [("udp","ipv4"),("udp","ipv6")],CONTROL,seconds)
    if control["delivered_mbps"]<2.3:
        raise RuntimeError(f"{label}: unpoliced control too slow, no proof of kernel policing: {control}")


def audit(mod,config):
    p=mod.read_json(mod.port_file(PORT))
    mod.validate_record(PORT,p)
    nft=mod.nft_snapshot()
    mod.validate_base(nft)
    tc=mod.tc_snapshot(config["iface"])
    value,*_=mod.audit_one(PORT,p,config,nft,tc)
    if value!="OK":raise RuntimeError(f"rule audit failed: {value}")


def faults(mod,config,label):
    audit(mod,config)
    snapshot=mod.nft_snapshot()
    rule=next(x["rule"] for x in snapshot if x.get("rule",{}).get("comment")==mod.comment("up",PORT,"count"))
    run("nft","delete","rule","inet",mod.TABLE,"inbound","handle",str(rule["handle"]))
    if mod.nft_ok(PORT,mod.read_json(mod.port_file(PORT))):
        raise RuntimeError(f"{label}: missing count rule incorrectly audited healthy")
    mod.reconcile(config,monitor=False)
    audit(mod,config)
    print(f"SEMANTIC_FAULT={label}: missing managed rule repaired",flush=True)

    injected="portbw-foreign-test-guard"
    run("nft","add","rule","inet",mod.TABLE,"inbound","counter","comment",injected)
    try:
        before=mod.nft_snapshot()
        handles=[x["rule"]["handle"] for x in before
                 if x.get("rule",{}).get("comment")==injected]
        if len(handles)!=1:raise RuntimeError("foreign injection not observable")
        blocked=False
        try:mod.reconcile(config,monitor=False)
        except mod.Error:blocked=True
        if not blocked:raise RuntimeError(f"{label}: foreign rule did not block reconcile")
        after=mod.nft_snapshot()
        surviving=[x["rule"]["handle"] for x in after
                   if x.get("rule",{}).get("comment")==injected]
        if surviving!=handles:
            raise RuntimeError(f"{label}: foreign rule changed/deleted")
        print(f"SEMANTIC_FAULT={label}: foreign rule preserved and fail-closed",flush=True)
    finally:
        # Only delete the EXACT lab-injected foreign rule; never flush.
        allrules=mod.nft_snapshot()
        for x in allrules:
            if x.get("rule",{}).get("comment")==injected:
                run("nft","delete","rule","inet",mod.TABLE,"inbound",
                    "handle",str(x["rule"]["handle"]))
    mod.reconcile(config,monitor=False)
    audit(mod,config)

    corrupt=mod.port_file(PORT+1)
    if corrupt.exists():raise RuntimeError("refuse to overwrite a sibling policy")
    corrupt.parent.mkdir(parents=True,exist_ok=True)
    corrupt.write_text("{ invalid test record",encoding="utf-8")
    try:
        try:mod.reconcile(config,monitor=False)
        except mod.Error:pass
        else:raise RuntimeError(f"{label}: damaged sibling should report failure")
        if not corrupt.is_file():
            raise RuntimeError("damaged sibling was unexpectedly removed")
        audit(mod,config)
    finally:
        corrupt.unlink(missing_ok=True)
    print(f"SEMANTIC_FAULT={label}: corrupt sibling isolated",flush=True)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source",required=True)
    p.add_argument("--root",required=True)
    p.add_argument("--child-pid",required=True,type=int)
    p.add_argument("--label",required=True)
    p.add_argument("--suite",choices=["aggregate","faults"],required=True)
    p.add_argument("--seconds",type=int,default=18)
    args=p.parse_args()
    guard()
    root=Path(args.root).resolve()
    if root.parent!=Path("/tmp") or not root.name.startswith("portbw-cpu-"):
        p.error("root must be private /tmp/portbw-cpu-*")
    if args.suite=="aggregate" and not 12<=args.seconds<=120:
        p.error("aggregate duration must be 12..120")
    mod=load(args.source)
    config=mod.cfg()
    audit(mod,config)
    if args.suite=="aggregate":
        aggregate(mod,config,args.child_pid,root,args.label,args.seconds)
    else:
        faults(mod,config,args.label)
    audit(mod,config)
    print("SEMANTIC_PASS="+json.dumps({"version":args.label,"suite":args.suite}),flush=True)


if __name__=="__main__":
    main()
