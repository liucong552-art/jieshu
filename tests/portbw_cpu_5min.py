#!/usr/bin/env python3
"""Read-only 5-minute portbw CPU comparison (timer oneshot OR resident daemon).

No service start/stop, rules changes, sysctl, installation or package changes.
Old oneshot CPU is a measured LOWER BOUND unless 100% journal coverage confirms
all completed service invocations were observed. The measured total-system CPU
includes this observer, Xray, WG, and everything else.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

SVC="portbw-watch.service"
PROG=Path("/usr/local/lib/portbw/portbw.py")
POLICIES=Path("/var/lib/portbw/ports")

def run(*cmd,timeout=8):
    try:
        p=subprocess.run(cmd,text=True,capture_output=True,timeout=timeout)
    except (OSError,subprocess.TimeoutExpired) as e:
        raise RuntimeError(f"cannot sample {' '.join(cmd)}: {e}") from e
    if p.returncode:
        raise RuntimeError(f"{' '.join(cmd)} failed: {p.stderr[-400:]}")
    return p.stdout

def properties():
    keys=("Type","ActiveState","MainPID","ExecMainStartTimestampMonotonic",
          "CPUUsageNSec","CPUAccounting")
    rows=run("systemctl","show",SVC,*sum((["-p",key] for key in keys),[]),
             "--no-pager").splitlines()
    obj=dict(v.split("=",1) for v in rows if "=" in v)
    return obj

def num(s):
    try:return int(s)
    except (ValueError,TypeError):return None

def stat_cpu():
    words=Path("/proc/stat").read_text().splitlines()[0].split()
    values=list(map(int,words[1:]))
    if len(values)<8:raise RuntimeError("/proc/stat missing cpu fields")
    idle=values[3]+values[4]
    total=sum(values[:8])
    return total,idle

def port_summary():
    if not POLICIES.is_dir():return {"count":0,"ports":[]}
    paths=sorted(POLICIES.glob("*.json"))
    out=[]
    for path in paths:
        try:
            d=json.loads(path.read_text())
            out.append({"port":d.get("port"),"base":d.get("auto",{}).get("base"),
                        "limited":d.get("auto",{}).get("limited"),
                        "trigger_bp":d.get("auto",{}).get("trigger_bp"),
                        "after":d.get("auto",{}).get("after")})
        except (OSError,ValueError,TypeError):
            raise RuntimeError(f"invalid port state: {path.name}") from None
    return {"count":len(out),"ports":out}

def journal_completions(start_unix,end_unix):
    try:
        raw=run("journalctl","-u",SVC,"--since",f"@{start_unix:.0f}",
                "--until",f"@{end_unix:.0f}","--no-pager","-o","cat",timeout=30)
    except RuntimeError:
        return None
    return sum(("Finished portbw-watch.service" in x or
                ("Deactivated successfully" in x and "portbw" not in x))
               for x in raw.splitlines()) if raw else 0

def benchmark(seconds,poll,include_ports):
    if not 60<=seconds<=3600:raise RuntimeError("--seconds must be 60..3600")
    if not .10<=poll<=1.0:raise RuntimeError("--poll must be 0.10..1.00")
    begin=properties()
    typ=begin.get("Type")
    if typ not in ("oneshot","notify","simple","exec"):
        raise RuntimeError(f"unsupported Watchdog Type: {typ!r}")
    if begin.get("CPUAccounting")!="yes":
        raise RuntimeError("CPUAccounting not enabled; no reliable CPU result")
    mode="timer" if typ=="oneshot" else "resident"
    if mode=="resident" and (begin.get("ActiveState")!="active" or
                             (num(begin.get("MainPID")) or 0)<=0):
        raise RuntimeError("resident service not active")
    sha=(hashlib.sha256(PROG.read_bytes()).hexdigest() if PROG.is_file()
         else "not_installed")
    ports=port_summary() if include_ports else None
    pids={};old_samples={};readings=0;sample_errors=0
    cpu0=stat_cpu()
    wall_begin=time.time()
    start=time.monotonic()
    deadline=start+seconds
    next_sample=start
    resident_start=num(begin.get("CPUUsageNSec"))
    last=begin
    # Every legacy oneshot sample is keyed by systemd's unique invocation start
    # monotonic microseconds. Observe finalized CPU while ActiveState=inactive.
    # Do NOT sum CPUUsageNSec across every poll (that double-counts invocations).
    while True:
        now=time.monotonic()
        if now>=deadline:break
        if now<next_sample:
            time.sleep(min(next_sample-now,.07))
            continue
        try:
            item=properties()
            readings+=1
            if mode=="timer":
                stamp=num(item.get("ExecMainStartTimestampMonotonic"))
                used=num(item.get("CPUUsageNSec"))
                if (item.get("ActiveState")=="inactive" and stamp and used is not None
                    and used>=0):
                    old_samples[stamp]=max(used,old_samples.get(stamp,0))
            else:
                pid=num(item.get("MainPID"))
                if pid and pid>0:
                    pids[pid]=True
            last=item
        except RuntimeError:
            sample_errors+=1
        next_sample+=poll
        if next_sample<time.monotonic()-poll:next_sample=time.monotonic()+poll
    cpu1=stat_cpu()
    wall_end=time.time()
    elapsed=time.monotonic()-start
    final=properties()
    host_busy=100*(1-(cpu1[1]-cpu0[1])/(cpu1[0]-cpu0[0])) if cpu1[0]>cpu0[0] else None
    logical=os.cpu_count() or 1
    result={"format":"portbw-cpu-v1","timestamp_unix":int(wall_begin),
            "host":run("hostname").strip(),"old_or_new":mode,
            "service_type":typ,"source_sha256":sha,"ports":ports,
            "seconds":round(elapsed,2),"logical_cpus":logical,
            "system_cpu_percent_all_cores":round(host_busy,3) if host_busy is not None else None,
            "observer_polls":readings,"observer_errors":sample_errors}
    if mode=="timer":
        finished=journal_completions(wall_begin,wall_end)
        observed=len(old_samples)
        total_ns=sum(old_samples.values())
        pct=100*total_ns/1e9/elapsed
        coverage=(observed/finished if finished and finished>0 else None)
        result.update(watchdog_cpu_pct_single_core_lower_bound=round(pct,4),
                      watchdog_cpu_pct_all_cores_lower_bound=round(pct/logical,4),
                      observed_finished_invocations=observed,
                      journal_finished_events=finished,
                      observed_journal_coverage=round(coverage,4) if coverage is not None else None,
                      caveat=("Lower bound due to missed invocations; no fair CPU win/loss claim"
                              if coverage is None or coverage<.95 else
                              "Nearly all service completions observed; timer CPU estimate"))
    else:
        end_used=num(final.get("CPUUsageNSec"))
        stable=(begin.get("MainPID")==final.get("MainPID")
                and final.get("ActiveState")=="active"
                and len(pids)<=1 and resident_start is not None
                and end_used is not None and end_used>=resident_start)
        result.update(watchdog_cpu_pct_single_core=round(
                            100*(end_used-resident_start)/1e9/elapsed,4) if stable else None,
                      watchdog_cpu_pct_all_cores=round(
                            100*(end_used-resident_start)/1e9/elapsed/logical,4) if stable else None,
                      resident_pid_stable=stable,
                      caveat=("Stable service CPU accounting" if stable else
                              "Resident restarted/reset during observation; invalid comparison"))
    print("PORTBW_CPU_5MIN="+json.dumps(result,ensure_ascii=False,sort_keys=True),flush=True)
    if mode=="timer":
        print("CPU_RESULT=LOWER_BOUND (timer oneshot; check observed_journal_coverage)",flush=True)
    else:
        print("CPU_RESULT="+("VALID" if result["resident_pid_stable"] else "INVALID"),flush=True)
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--seconds",type=int,default=300)
    p.add_argument("--poll",type=float,default=.2)
    p.add_argument("--omit-policies",action="store_true",
                   help="omit actual port config values from the JSON summary")
    args=p.parse_args()
    try:benchmark(args.seconds,args.poll,not args.omit_policies)
    except (RuntimeError,PermissionError,OSError,ValueError) as e:
        print("CPU_BENCH_STOP:",e,file=sys.stderr);sys.exit(1)

if __name__=="__main__":main()
