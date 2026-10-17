#!/usr/bin/env python3
"""One-version real-kernel semantic suite in fresh disposable netns."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import hashlib


def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",required=True)
    p.add_argument("--version",choices=["A","B"],required=True)
    p.add_argument("--suite",choices=["aggregate","faults","lifecycle","outbound"],required=True)
    p.add_argument("--seconds",type=int,default=18)
    args=p.parse_args()
    if not 12<=args.seconds<=120:
        p.error("seconds must be 12..120")
    root=Path(args.root).resolve()
    if root.parent!=Path("/tmp") or not root.name.startswith("portbw-cpu-"):
        p.error("private /tmp root required")
    runner=load(root/"tools/portbw_ab_lab_runner.py","lab_runner")
    runner.isolated()
    src=root/args.version/"portbw.py"
    expected={"A":"69058c8069e78d902c4814e1300c5aa38e2b91340f936cdb9cdc09a14936f359",
              "B":"f0ebe551e8c0345c045a558b39a8b13523b2be8195255c67db13eec3eff5dc1a"}
    if args.version=="B" and os.environ.get("PORTBW_LAB_B_SHA"):
        expected["B"]=os.environ["PORTBW_LAB_B_SHA"]
    if hashlib.sha256(src.read_bytes()).hexdigest()!=expected[args.version]:
        raise RuntimeError("source hash mismatch")
    for d in ("config","state","run","locks"):
        path=root/d
        if path.is_symlink():raise RuntimeError("unexpected test state symlink")
        if path.is_dir():shutil.rmtree(path)
        elif path.exists():raise RuntimeError("unexpected non-directory test state")
    child=None
    try:
        child,ipv6=runner.set_up_link()
        if args.suite=="aggregate" and not ipv6:
            raise RuntimeError("IPv6 test interface unavailable")
        base=str(root)
        os.environ.update(PORTBW_STATE=base+"/state",
                          PORTBW_CONF=base+"/config",
                          PORTBW_LOCK=base+"/locks/manager.lock",
                          PORTBW_RUN=base+"/run",PORTBW_UNITS=base+"/units")
        sem=load(root/"tools/portbw_lab_semantics.py","lab_semantics")
        sem.guard()
        mod=runner.module(src)
        cfg={"iface":runner.IFACE,"tc_enabled":True,"version":2}
        mod.write_json(mod.CONF/"config.json",cfg)
        mod.tc_prepare(runner.IFACE)
        runner.prepare_ports(mod,cfg,1,False)
        sem.audit(mod,cfg)
        if args.suite=="aggregate":
            sem.aggregate(mod,cfg,child.pid,root,args.version,args.seconds)
        elif args.suite=="faults":
            sem.faults(mod,cfg,args.version)
        elif args.suite=="outbound":
            sem.outbound(mod,cfg,child.pid,root,args.version,args.seconds)
        else:
            sem.lifecycle(mod,cfg,child.pid,root,args.version)
        sem.audit(mod,cfg)
        result={"version":args.version,"suite":args.suite,"passed":True,
                "source_sha256":expected[args.version]}
        output=root/"results"/f"semantics_{args.suite}_{args.version}.json"
        output.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
        print("SEMANTIC_PASS="+json.dumps(result),flush=True)
    finally:
        if child:
            child.terminate()
            try:child.wait(timeout=3)
            except Exception:child.kill()


if __name__=="__main__":
    main()
