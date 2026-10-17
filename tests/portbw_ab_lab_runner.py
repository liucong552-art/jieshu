#!/usr/bin/env python3
"""Real nft/tc CPU A/B lab, refuses host network namespace.

Must be launched by the accompanying shell script using unshare --net.
Only creates veth interfaces and nft/tc rules inside a throwaway netns.
A = pinned main, B = pinned feature branch. Never invokes systemctl.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time


IFACE = "pbwl0"
PEER = "pbwl1"
PORT = 43000


def execute(*args, **kwargs):
    return subprocess.run(args, text=True, check=True, **kwargs)


def isolated():
    if os.getenv("PORTBW_LAB_ACK") != "isolated-netns-only":
        raise SystemExit("REFUSED: lab not explicitly enabled")
    if os.geteuid():
        raise SystemExit("REFUSED: must be root in disposable network namespace")
    if os.stat("/proc/self/ns/net").st_ino == os.stat("/proc/1/ns/net").st_ino:
        raise SystemExit("REFUSED: host network namespace")
    # /sys/class/net may still display the HOST network namespace when
    # unshare --net inherits the host's sysfs mount. Netlink queries through
    # ip -j link are scoped to the ACTUAL running network namespace.
    links = json.loads(execute("ip", "-j", "link", "show",
                               stdout=subprocess.PIPE).stdout)
    names = {link.get("ifname") for link in links}
    if "eth0" in names or "wg-nat" in names:
        raise SystemExit("REFUSED: production interfaces visible via netlink")
    if IFACE in names or PEER in names:
        raise SystemExit("REFUSED: lab interfaces already exist in namespace")


def module(path):
    spec = importlib.util.spec_from_file_location("portbw_lab_original", path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def make_rec(mod, port, n, automatic):
    prefs = {f"{family}_{transport}": 65000 - n * 4 - offset
             for offset, (family, transport) in enumerate(
                 ((4, "tcp"), (4, "udp"), (6, "tcp"), (6, "udp")))}
    rec = {"port": port, "up": 125000, "down": 125000,
           "updated": int(time.time()), "pending": True,
           "deleting": False, "tc_prefs": prefs}
    if automatic:
        opts = {"version": mod.AUTO_VERSION,
                "base": {"up": 125000, "down": 125000},
                "limited": {"up": 62500, "down": 62500},
                "trigger_bp": 7000, "after": 5, "hold": 20, "cooldown": 0}
        rec["auto"] = opts
        mod.reset_auto_boot(rec, mod.boot_id())
    mod.validate_record(port, rec)
    return rec


def prepare_ports(mod, config, count, automatic):
    for i in range(count):
        port = PORT + i
        path = mod.port_file(port)
        if path.is_file():
            continue
        rec = make_rec(mod, port, i, automatic and i == 0)
        mod.write_json(path, rec)
        mod.finish_apply(port, rec, config)
    return list(range(PORT, PORT + count))


def reset_automatic(mod, config, enabled):
    if not enabled:
        return
    rec = mod.read_json(mod.port_file(PORT))
    mod.reset_auto_boot(rec, mod.boot_id())
    rec["updated"] = int(time.time())
    mod.write_json(mod.port_file(PORT), rec)
    mod.volatile_clear(PORT)
    mod.finish_apply(PORT, rec, config)


def audit_records(mod, config, ports):
    nft = mod.nft_snapshot()
    tc = mod.tc_snapshot(config["iface"])
    errors = []
    for port in ports:
        rec = mod.read_json(mod.port_file(port))
        state, is_nft_ok, is_tc_ok = mod.audit_one(port, rec, config, nft, tc)
        if state != "OK":
            errors.append({"port": port, "state": state,
                           "nft_ok": is_nft_ok, "tc_ok": is_tc_ok})
    if errors:
        raise RuntimeError(f"rule audit failed: {errors}")
    return len(ports)


def set_up_link():
    execute("ip", "link", "set", "lo", "up")
    # Sleep process enters its OWN disposable network namespace. A veth peer is
    # moved only into that child, never into the host's netns.
    child = subprocess.Popen(["unshare", "--net", "--", "sleep", "10000"])
    try:
        time.sleep(.15)
        if child.poll() is not None:
            raise RuntimeError("child unshare exited: nested network namespaces unavailable")
        execute("ip", "link", "add", IFACE, "type", "veth", "peer", "name", PEER)
        execute("ip", "link", "set", PEER, "netns", str(child.pid))
        execute("ip", "addr", "add", "198.18.0.1/30", "dev", IFACE)
        execute("ip", "link", "set", IFACE, "up")
        execute("nsenter", "-t", str(child.pid), "-n", "ip", "link", "set", "lo", "up")
        execute("nsenter", "-t", str(child.pid), "-n", "ip", "addr", "add",
                "198.18.0.2/30", "dev", PEER)
        execute("nsenter", "-t", str(child.pid), "-n", "ip", "link", "set", PEER, "up")
        # IPv6 availability is reported, not silently substituted for IPv4.
        ipv6 = False
        try:
            execute("ip", "-6", "addr", "add", "2001:db8:4300::1/64", "dev", IFACE, "nodad")
            execute("nsenter", "-t", str(child.pid), "-n", "ip", "-6", "addr",
                    "add", "2001:db8:4300::2/64", "dev", PEER, "nodad")
            ipv6 = True
        except subprocess.CalledProcessError:
            print("NOTE: IPv6 namespace addresses unavailable; IPv6 filter tests still required")
        if ipv6:
            # Query netlink in each namespace; the inherited sysfs mount can
            # refer to host interfaces rather than the real net namespace.
            for prefix, device, address in (
                ([], IFACE, "2001:db8:4300::1"),
                (["nsenter", "-t", str(child.pid), "-n"], PEER, "2001:db8:4300::2"),
            ):
                raw=execute(*(prefix+["ip","-j","-6","address","show","dev",device]),
                            stdout=subprocess.PIPE).stdout
                rows=json.loads(raw)
                present=any(o.get("local")==address
                            and "tentative" not in o.get("flags",[])
                            and "dadfailed" not in o.get("flags",[])
                            for row in rows for o in row.get("addr_info",[]))
                if not present:
                    raise RuntimeError(f"IPv6 {device} {address} not usable: {raw[:1000]}")
        return child, ipv6
    except Exception:
        child.terminate()
        try:
            child.wait(timeout=3)
        except subprocess.TimeoutExpired:
            child.kill()
        raise


def run_trial(name, source, root, seconds, index, mode, child_pid, traffic, automatic=False, proto="udp", family="ipv4"):
    trial_name = f"{index:02d}_{name}_{mode}_{proto}_{family}"
    output = root / "results"
    output.mkdir(parents=True, exist_ok=True)
    probe = root / "tools" / "portbw_cpu_probe.py"
    traffic_file = root / "tools" / "portbw_lab_traffic.py"
    background = []
    handles = []
    try:
        if traffic == "udp":
            duration = seconds + 8
            server_log = (output / f"{trial_name}_server.json").open("w")
            handles.append(server_log)
            server = subprocess.Popen([sys.executable, str(traffic_file), "server", "--proto", proto, "--family", family,
                                       "--port", str(PORT), "--seconds", str(duration)],
                                      stdout=server_log, stderr=subprocess.STDOUT)
            background.append(server)
            time.sleep(.2)
            client_log = (output / f"{trial_name}_client.json").open("w")
            handles.append(client_log)
            client = subprocess.Popen(["nsenter", "-t", str(child_pid), "-n",
                                       sys.executable, str(traffic_file), "client", "--proto", proto, "--family", family,
                                       "--port", str(PORT), "--seconds",
                                       str(seconds + 5), "--mbit", "3"],
                                      stdout=client_log, stderr=subprocess.STDOUT)
            background.append(client)
        # Pure CPU comparison: do NOT enable cProfile during A/B, as its
        # instrumentation changes the cost of Python's per-rule loops.
        cmd = [sys.executable, str(probe), str(source), "--rounds",
               str(seconds), "--warmup", "3", "--interval", "1",
               "--label", trial_name]
        result = subprocess.run(cmd, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
        (output / f"{trial_name}_stdout.log").write_text(result.stdout,encoding="utf-8")
        (output / f"{trial_name}_stderr.log").write_text(result.stderr,encoding="utf-8")
        if result.returncode:
            raise RuntimeError(f"trial {trial_name} failed: {result.stderr[-1200:] or result.stdout[-1200:]}")
        markers=[line[len("PORTBW_PROBE_RESULT="):] for line in result.stdout.splitlines()
                 if line.startswith("PORTBW_PROBE_RESULT=")]
        if len(markers)!=1:raise RuntimeError(f"trial {trial_name}: missing/multiple CPU result markers")
        data = json.loads(markers[0])
        if automatic and traffic == "udp" and seconds >= 30:
            transitions=[line for line in result.stdout.splitlines()
                         if f"{PORT} " in line and "自动降速" in line]
            if not transitions:
                raise RuntimeError(
                    f"{trial_name}: sustained UDP did not activate automatic throttling; "
                    "inspect raw stdout, tc counters, and sampling continuity")
            print(json.dumps({"trial":trial_name,"automatic_throttling_events":transitions},
                             ensure_ascii=False),flush=True)
        (output / f"{trial_name}.json").write_text(
            json.dumps(data, ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print(json.dumps({"trial": trial_name, "rounds": data["completed_rounds"],
                          "one_core_cpu_process_children_pct": data["process_plus_children_one_core_pct"],
                          "process_pct": data["process_one_core_pct"],
                          "system_pct": data["machine_busy_pct"],
                          "commands": data["child_commands"],
                          "round_ms": data["round_wall_ms"]}, ensure_ascii=False),
              flush=True)
        return data
    finally:
        for proc in background:
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
        for h in handles:
            h.close()
        if traffic == "udp":
            server_result = output / f"{trial_name}_server.json"
            client_result = output / f"{trial_name}_client.json"
            if not server_result.is_file() or not client_result.is_file():
                raise RuntimeError("missing UDP traffic records")
            try:
                server_data = json.loads(server_result.read_text().strip().splitlines()[-1])
                client_data = json.loads(client_result.read_text().strip().splitlines()[-1])
            except (ValueError, IndexError) as exc:
                raise RuntimeError(
                    f"{trial_name}: invalid {proto}/{family} traffic logs; "
                    f"server={server_result.read_text()[-2000:]!r}; "
                    f"client={client_result.read_text()[-2000:]!r}"
                ) from exc
            # The shared ingress cap is 1 Mbps (auto mode 0.5 Mbps after
            # trigger); demand a genuine overload and a nonzero delivered flow.
            # Include generous scheduling and burst tolerance: this is a
            # useful gross-bypass test, NOT an SLA-accurate bandwidth test.
            tx_rate=client_data.get("tx_bytes",0)*8/(client_data.get("seconds",1)*1000000)
            rx_rate=server_data.get("rx_bytes",0)*8/(client_data.get("seconds",1)*1000000)
            if proto == "udp":
                if tx_rate < 1.4:
                    raise RuntimeError(f"{trial_name}: UDP load too weak: offered={tx_rate:.3f} Mbps")
                if not (0.05 < rx_rate <= 1.55 and rx_rate < tx_rate * 0.9):
                    raise RuntimeError(
                        f"{trial_name}: ingress policing not proven: offered={tx_rate:.3f}, "
                        f"received={rx_rate:.3f} Mbps (expected <=1 Mbps + tolerance)")
            else:
                # TCP backpressure can reduce sender's actual transmitted
                # bytes; do not demand an impossible UDP-like overload ratio.
                if not (0.05 < rx_rate <= 1.55 and client_data.get("tx_bytes",0)>0):
                    raise RuntimeError(f"{trial_name}: TCP rate/connection invalid: {rx_rate:.3f} Mbps")
            if client_data.get("rx_bytes", 0) <= 0:
                raise RuntimeError(f"{trial_name}: no {proto}/{family} echo packets received")
            print(json.dumps({"trial": trial_name, "offered_mbps": round(tx_rate,3), "transport":proto,"family":family,
                              "delivered_mbps": round(rx_rate,3),
                              "udp_send_errors": client_data["send_errors"]}),
                  flush=True)


def main():
    arg = argparse.ArgumentParser()
    arg.add_argument("--root", required=True)
    arg.add_argument("--seconds", type=int, default=30)
    arg.add_argument("--sizes", default="1,10,25")
    arg.add_argument("--traffic", choices=["idle", "udp"], default="idle")
    arg.add_argument("--auto", action="store_true")
    arg.add_argument("--proto", choices=["udp","tcp"], default="udp")
    arg.add_argument("--family", choices=["ipv4","ipv6"], default="ipv4")
    arg.add_argument("--baseline-only", action="store_true", help="Measure untouched main only; do not run candidate")
    arg.add_argument("--profile-baseline", action="store_true", help="Extra A-only profiler pass; not used for CPU comparison")
    args = arg.parse_args()
    isolated()
    root = Path(args.root).resolve()
    if not root.name.startswith("portbw-cpu-") or root.parent != Path("/tmp"):
        arg.error("root must be a direct /tmp/portbw-cpu-* directory")
    if not (10 <= args.seconds <= 3600):
        arg.error("seconds must be 10..3600")
    sizes = [int(n) for n in args.sizes.split(",")]
    if not sizes or sizes != sorted(set(sizes)) or sizes[0] < 1 or sizes[-1] > 25:
        arg.error("sizes must be increasing unique integers within 1..25")
    srcA, srcB = root / "A/portbw.py", root / "B/portbw.py"
    if not srcA.is_file() or (not args.baseline_only and not srcB.is_file()):
        arg.error("missing required A/B source")
    import hashlib
    origsha = hashlib.sha256(srcA.read_bytes()).hexdigest()
    newsha = hashlib.sha256(srcB.read_bytes()).hexdigest() if srcB.is_file() else None
    if origsha != "69058c8069e78d902c4814e1300c5aa38e2b91340f936cdb9cdc09a14936f359":
        raise SystemExit("REFUSED: A must be the immutable original main source")
    if not args.baseline_only and origsha == newsha:
        raise SystemExit("REFUSED: candidate source identical to original")
    # Each separate unshare run starts with a fresh kernel ruleset. Prior
    # phase's durable intent MUST also be reset, or prepare_ports() would
    # incorrectly skip applying rules in the new namespace. Preserve results.
    for name in ("state", "config", "run", "locks"):
        scratch = root / name
        if scratch.is_symlink():
            raise SystemExit(f"REFUSED: scratch path is symlink: {scratch}")
        if scratch.is_dir():
            shutil.rmtree(scratch)
        elif scratch.exists():
            raise SystemExit(f"REFUSED: scratch path is not a directory: {scratch}")
    child = None
    try:
        child, has_ipv6 = set_up_link()
        if args.traffic == "udp" and args.family == "ipv6" and not has_ipv6:
            raise RuntimeError("IPv6 requested but not configured")
        env_base = str(root)
        os.environ.update(PORTBW_STATE=env_base+"/state", PORTBW_CONF=env_base+"/config",
                          PORTBW_LOCK=env_base+"/locks/manager.lock",
                          PORTBW_RUN=env_base+"/run", PORTBW_UNITS=env_base+"/units")
        mod = module(srcA)
        config = {"iface": IFACE, "tc_enabled": True, "version": 2}
        mod.write_json(mod.CONF / "config.json", config)
        mod.tc_prepare(IFACE)
        trials = []
        for count in sizes:
            ports = prepare_ports(mod, config, count, args.auto)
            print(f"STAGE policy_count={count}, type={'auto+static' if args.auto else 'static'}",
                  flush=True)
            order = ("A",) if args.baseline_only else ("A", "B")
            for index, name in enumerate(order, 1):
                reset_automatic(mod, config, args.auto)
                audit_records(mod, config, ports)
                src = srcA if name == "A" else srcB
                data = run_trial(name, src, root, args.seconds,
                                 count, args.traffic, child.pid, args.traffic,
                                 automatic=args.auto, proto=args.proto, family=args.family)
                audit_records(mod, config, ports)
                trials.append({"policy_count": count, "version": name,
                               "cpu_total": data["process_plus_children_one_core_pct"],
                               "cmds": data["child_commands"],
                               "mean_ms": data["round_wall_ms"]["mean"]})
                if name == "A" and args.profile_baseline:
                    profile = root / "results" / f"{count:02d}_A_hotspots.pstats"
                    execute(sys.executable, str(root / "tools/portbw_cpu_probe.py"),
                            str(srcA), "--rounds", str(max(10, min(30, args.seconds))),
                            "--warmup", "2", "--interval", "1", "--profile", str(profile),
                            "--label", f"{count:02d}_A_profile", stdout=subprocess.PIPE)
                    print("BASELINE_PYTHON_HOTSPOTS: "+str(profile)+".txt",flush=True)
        result = {"success": True, "a_sha256": origsha, "b_sha256": newsha,
                  "ipv6_test_network_available": has_ipv6,
                  "duration_each_seconds": args.seconds, "sizes": sizes,
                  "traffic": args.traffic, "transport":args.proto,"family":args.family,
                  "automatic_policy": args.auto,
                  "baseline_only": args.baseline_only, "trials": trials}
        path = root / "results/summary.json"
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print("LAB SUCCESS: results at "+str(path), flush=True)
    finally:
        if child:
            child.terminate()
            try:
                child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                child.kill()


if __name__ == "__main__":
    main()
