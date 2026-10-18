#!/usr/bin/env python3
"""Controlled migration from exact zuizhongheji legacy portbw to new managed portbw.
Never flushes a ruleset or root qdisc. No numbered prompts.
check/baseline: read-only. migrate/rollback: destructive for ONLY portbw objects.
Backups stay on host; snapshot VPS before use.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from decimal import Decimal

OLD_SHA="face2509536f182d9fe894b98515d5ad9dfb46c36c5555cca3286228a7984f5b"
NEW_SHA="66a79fd8ff9f4b00c43a62ef3530251cd6934301bfc5412d497b47d94a3f70d1"
REF="078e6cd06e5a406d11bf6523dcebc6de7afe017f"
BASE="https://raw.githubusercontent.com/liucong552-art/jieshu"
PROG=Path("/usr/local/lib/portbw/portbw.py")
CLI=Path("/usr/local/sbin/portbw")
POLICIES=Path("/var/lib/portbw/ports")
CONFIG=Path("/etc/portbw/config.json")
MARK=Path("/var/lib/portbw-resident-release/current.env")
ROOT=Path("/var/backups/portbw-legacy-migration")
UNITS=("portbw-watch.timer","portbw-watch.service","portbw-restore.service")
PATHS=(PROG,CLI,CONFIG,Path("/var/lib/portbw"),
       *(Path("/etc/systemd/system")/u for u in UNITS))

class Refuse(RuntimeError):pass

def run(*cmd,check=True,timeout=180):
    p=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=timeout)
    if check and p.returncode:raise Refuse(f"{' '.join(map(str,cmd))}: {p.stderr[-800:]} {p.stdout[-400:]}")
    return p.stdout.strip()

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None

def load_module():
    spec=importlib.util.spec_from_file_location("legacy_portbw_verified",PROG)
    m=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

def expected_ports(arg):
    m=re.fullmatch(r"([0-9]{1,5}):([0-9]{1,5})",arg)
    if not m:raise Refuse("use --ports FIRST:LAST")
    first,last=map(int,m.groups())
    if not 1<=first<=last<=65535 or last-first>100:raise Refuse("invalid port range")
    return list(range(first,last+1))

def snapshot_policies():
    return {int(p.stem):json.loads(p.read_text()) for p in sorted(POLICIES.glob("*.json"))}

def preflight(a):
    if os.geteuid():raise Refuse("root required")
    hostname=run("hostname")
    if hostname!=a.host:raise Refuse(f"wrong host {hostname}; expected {a.host}")
    if sha(PROG)!=OLD_SHA:raise Refuse(f"legacy binary hash mismatch: {sha(PROG)}")
    if not CLI.is_file() or CLI.is_symlink():raise Refuse("old portbw CLI wrapper not found")
    if MARK.exists() or MARK.is_symlink():raise Refuse("managed marker already exists")
    cfg=json.loads(CONFIG.read_text())
    if cfg.get("tc_enabled") is not True:raise Refuse("only old nft+tc mode supported")
    iface=cfg.get("iface")
    if not isinstance(iface,str) or not re.fullmatch(r"[a-zA-Z0-9_.-]{1,15}",iface):
        raise Refuse("invalid old iface")
    run("ip","link","show","dev",iface)
    actual=snapshot_policies()
    expect=expected_ports(a.ports)
    if sorted(actual)!=expect:raise Refuse(f"port mismatch {sorted(actual)} vs {expect}")
    old=load_module()
    if cfg!=old.cfg():raise Refuse("config discrepancy")
    if not all(old.validate_record(p,actual[p]) is None for p in expect):
        raise Refuse("record validation failed")
    for p in expect:
        rec=actual[p]
        if rec.get("pending") or rec.get("deleting") or "auto" not in rec:
            raise Refuse(f"port {p}: not a settled auto policy")
        opts=rec["auto"]
        if set(opts)!=set(("version","base","limited","trigger_bp","after","hold","cooldown")):
            raise Refuse(f"port {p}: unrecognized auto options")
    if any((Path("/etc/systemd/system")/unit).read_text()!=body
           for unit,body in old.units().items()):
        raise Refuse("legacy unit content differs from SHA-verified source")
    if run("systemctl","is-active","portbw-watch.timer",check=False)!="active":
        raise Refuse("legacy timer is not active")
    if run("systemctl","show","portbw-watch.service","-p","Type","--value")!="oneshot":
        raise Refuse("legacy unit is not oneshot")
    old.validate_base(old.nft_snapshot())
    run(CLI,"audit")
    print(f"PRECHECK_PASS host={hostname} iface={iface} ports={len(expect)} old_sha={OLD_SHA}")
    for p in expect:
        opt=actual[p]["auto"]
        print(f"POLICY {p}: base={opt['base']} limited={opt['limited']} trigger_bp={opt['trigger_bp']} after={opt['after']} hold={opt['hold']} cooldown={opt['cooldown']}")
    return cfg,actual

def take_backup(cfg,policies):
    ROOT.mkdir(parents=True,exist_ok=True,mode=0o700)
    os.chmod(ROOT,0o700)
    directory=Path(tempfile.mkdtemp(prefix="backup-",dir=ROOT))
    os.chmod(directory,0o700)
    mirror=directory/"mirror"
    for orig in PATHS:
        if not orig.exists() and not orig.is_symlink():raise Refuse(f"missing expected file: {orig}")
        dest=mirror/orig.relative_to("/")
        dest.parent.mkdir(parents=True,exist_ok=True)
        if orig.is_dir() and not orig.is_symlink():
            shutil.copytree(orig,dest,symlinks=True)
        elif orig.is_symlink():
            dest.symlink_to(os.readlink(orig))
        else:shutil.copy2(orig,dest)
    data={"old_sha":OLD_SHA,"new_sha":NEW_SHA,"iface":cfg["iface"],
          "ports":sorted(policies),"hostname":run("hostname")}
    (directory/"manifest.json").write_text(json.dumps(data,indent=2))
    (directory/"legacy-rules.nft").write_text(run("nft","-a","list","table","inet","pbw_policy")+"\n")
    for direction in ("ingress","egress"):
        (directory/f"tc-{direction}.txt").write_text(run("tc","-s","filter","show","dev",cfg["iface"],direction)+"\n")
    os.sync()
    print(f"BACKUP_DIR={directory}",flush=True)
    return directory

def remove_empty_owned_nft():
    data=json.loads(run("nft","-j","list","table","inet","pbw_policy"))
    entries=data["nftables"]
    other=[x for x in entries if not set(x).issubset({"metainfo","table","chain"})]
    names=[x["chain"].get("name") for x in entries if "chain" in x]
    if other or sorted(names)!=["inbound","outbound"]:
        raise Refuse("owned nft table still has objects/rules or unexpected chains; REFUSE table deletion")
    if any(x["table"].get("family")!="inet" or x["table"].get("name")!="pbw_policy"
           for x in entries if "table" in x):
        raise Refuse("nft table identity mismatch")
    run("nft","delete","table","inet","pbw_policy")

def remove_unit_files():
    for u in UNITS:
        p=Path("/etc/systemd/system")/u
        if p.is_symlink() or p.is_file():p.unlink()
    for p in (PROG,CLI,CONFIG):
        if p.is_symlink() or p.is_file():p.unlink()
    run("systemctl","daemon-reload")

def fetch_package(work):
    files={}
    for name in ("portbw.py","portbw-install.sh"):
        dest=work/name
        run("curl","-fsSL","--retry","3",f"{BASE}/{REF}/{name}","-o",dest)
        files[name]=dest
    if sha(files["portbw.py"])!=NEW_SHA:raise Refuse("new source SHA mismatch")
    if f"EXPECTED_SHA='{NEW_SHA}'" not in files["portbw-install.sh"].read_text():
        raise Refuse("installer SHA pin mismatch")
    run("bash","-n",files["portbw-install.sh"])
    return files

def reapply(policies):
    for port,rec in sorted(policies.items()):
        opt=rec["auto"]
        def mbps(n):return format((Decimal(n)/Decimal(125000)).normalize(),"f")
        def trigger(n):return format((Decimal(n)/100).normalize(),"f")
        cmd=[str(CLI),"auto","set",str(port),
             "--up",mbps(opt["base"]["up"]),"--down",mbps(opt["base"]["down"]),
             "--trigger",trigger(opt["trigger_bp"]),"--after",f'{opt["after"]}s',
             "--auto-up",mbps(opt["limited"]["up"]),
             "--auto-down",mbps(opt["limited"]["down"]),
             "--hold",f'{opt["hold"]}s',"--cooldown",f'{opt["cooldown"]}s']
        print(run(*cmd),flush=True)
    after=snapshot_policies()
    if set(after)!=set(policies):raise Refuse("port count mismatch after reinstall")
    for port,rec in policies.items():
        if after[port].get("auto")!=rec["auto"]:
            raise Refuse(f"port {port}: policy options were not preserved")
        if after[port].get("pending"):raise Refuse(f"port {port}: pending after replay")
    run(CLI,"audit")
    print(f"POLICIES_RESTORED={len(after)}",flush=True)

def remove_current_rules_if_new():
    if sha(PROG)==NEW_SHA:
        run("systemctl","stop","portbw-watch.service",check=False)
        for port in sorted(snapshot_policies()):
            run(CLI,"del",str(port))
        if run("nft","list","table","inet","pbw_policy",check=False):
            remove_empty_owned_nft()
    elif sha(PROG)==OLD_SHA:
        # Old portbw could already have deleted some of its original ports.
        # Restoring backed-up records + old install will recreate those rules.
        return
    elif not PROG.exists():
        if run("nft","list","table","inet","pbw_policy",check=False):
            remove_empty_owned_nft()
    else:raise Refuse("installed program is neither known old nor known new")

def rollback(directory,*,automatic=False):
    directory=directory.resolve()
    if directory.parent!=ROOT or not directory.name.startswith("backup-"):
        raise Refuse("rollback requires exact backup directory under "+str(ROOT))
    meta=json.loads((directory/"manifest.json").read_text())
    if meta["old_sha"]!=OLD_SHA or meta["new_sha"]!=NEW_SHA or meta["hostname"]!=run("hostname"):
        raise Refuse("backup identity mismatch")
    original=directory/"mirror"/PROG.relative_to("/")
    if sha(original)!=OLD_SHA:raise Refuse("backup original source hash mismatch")
    for u in ("portbw-watch.timer","portbw-watch.service","portbw-restore.service"):
        run("systemctl","stop",u,check=False)
    run("systemctl","disable","portbw-watch.timer","portbw-restore.service",check=False)
    remove_current_rules_if_new()
    # Restore saved legacy program, wrapper, configuration, policy state and units.
    for original_path in PATHS:
        dest=original_path
        saved=directory/"mirror"/original_path.relative_to("/")
        if dest.is_symlink() or dest.is_file():dest.unlink()
        elif dest.is_dir():shutil.rmtree(dest)
        dest.parent.mkdir(parents=True,exist_ok=True)
        if saved.is_dir() and not saved.is_symlink():
            shutil.copytree(saved,dest,symlinks=True)
        elif saved.is_symlink():
            dest.symlink_to(os.readlink(saved))
        else:shutil.copy2(saved,dest)
    if MARK.exists():MARK.unlink()
    run("systemctl","daemon-reload")
    run(CLI,"install","--iface",meta["iface"])
    run(CLI,"audit")
    if sorted(snapshot_policies())!=meta["ports"]:raise Refuse("rollback port count mismatch")
    if run("systemctl","is-active","portbw-watch.timer",check=False)!="active":
        raise Refuse("legacy timer not active after rollback")
    print(f"ROLLBACK_PASS ports={len(meta['ports'])} source={OLD_SHA}",flush=True)

def migrate(a):
    cfg,policies=preflight(a)
    work=Path(tempfile.mkdtemp(prefix="portbw-migrate-package-"))
    package=fetch_package(work)
    backup=take_backup(cfg,policies)
    try:
        run("systemctl","stop","portbw-watch.timer")
        run("systemctl","stop","portbw-watch.service")
        run("systemctl","disable","portbw-watch.timer","portbw-restore.service")
        for port in sorted(policies):
            print(run(CLI,"del",str(port)),flush=True)
        if list(POLICIES.glob("*.json")):raise Refuse("legacy port records remain")
        remove_empty_owned_nft()
        remove_unit_files()
        print(run("bash",package["portbw-install.sh"],"check","--iface",cfg["iface"]),flush=True)
        print(run("bash",package["portbw-install.sh"],"install","--iface",cfg["iface"],timeout=240),flush=True)
        reapply(policies)
        print(run("bash",package["portbw-install.sh"],"verify",timeout=120),flush=True)
        print(f"MIGRATION_PASS backup={backup} ports={len(policies)} new_sha={NEW_SHA}",flush=True)
    except BaseException as e:
        print(f"MIGRATION_FAILED: {e}; attempting owned-only rollback",file=sys.stderr,flush=True)
        try:rollback(backup,automatic=True)
        except BaseException as rollback_exc:
            print(f"ROLLBACK_INCOMPLETE: {rollback_exc}; preserve backup {backup}; do not flush rulesets",file=sys.stderr,flush=True)
        raise

def baseline(seconds):
    if not 10<=seconds<=120:raise Refuse("sample must be 10..120 seconds")
    observed={}
    started=time.monotonic()
    while time.monotonic()-started<seconds:
        raw=run("systemctl","show","portbw-watch.service",
                "-p","ExecMainStartTimestampMonotonic","-p","CPUUsageNSec",
                "-p","ActiveState",check=False,timeout=10)
        fields=dict(row.split("=",1) for row in raw.splitlines() if "=" in row)
        stamp=fields.get("ExecMainStartTimestampMonotonic","0")
        cpu=fields.get("CPUUsageNSec","")
        if (fields.get("ActiveState")=="inactive" and stamp.isdigit()
            and int(stamp)>0 and cpu.isdigit() and int(cpu)>0):
            observed[int(stamp)]=int(cpu)
        time.sleep(.2)
    cpu_s=sum(observed.values())/1e9
    print(f"LEGACY_TIMER_CPU_LOWER_BOUND={100*cpu_s/seconds:.3f}% single-core-normalized")
    print(f"observed_completed_runs={len(observed)} duration={seconds}s (missed timer executions make this a lower bound)")

def main():
    ap=argparse.ArgumentParser(description="Verified legacy portbw migration; no numeric menus")
    sub=ap.add_subparsers(dest="action",required=True)
    for name in ("check","migrate"):
        p=sub.add_parser(name);p.add_argument("--host",required=True);p.add_argument("--ports",required=True)
    p=sub.add_parser("rollback");p.add_argument("backup_dir")
    p=sub.add_parser("baseline");p.add_argument("--seconds",type=int,default=60)
    a=ap.parse_args()
    try:
        if a.action=="check":preflight(a)
        elif a.action=="migrate":migrate(a)
        elif a.action=="rollback":rollback(Path(a.backup_dir))
        else:baseline(a.seconds)
    except (Refuse,OSError,ValueError,KeyError,subprocess.TimeoutExpired) as e:
        print("STOP:",e,file=sys.stderr);sys.exit(1)

if __name__=="__main__":main()
