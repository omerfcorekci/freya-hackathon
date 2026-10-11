"""Process watchdog for long test batches: nothing runs for ever.

    python3 builder/watchdog.py [--max-run-minutes 20] [--lifetime-hours 4]

Every two minutes: kill any tools/run_cases.py process older than --max-run-minutes (its parent run_cases_safe.py then
cancels the platform simulation), cancel any simulation the platform has reported as running for longer than that,
and log what it did to results/watchdog.log. Exits after --lifetime-hours.
"""
import argparse, os, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def log(msg):
    line = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) + " " + msg
    print(line, flush=True)
    with open(os.path.join(ROOT, "results", "watchdog.log"), "a") as f: f.write(line + "\n")


def old_scorers(max_age_s):
    out = subprocess.run(["ps", "-axo", "pid=,etimes=,command="], capture_output=True, text=True).stdout
    hits = []
    for line in out.splitlines():
        parts = line.split(None, 2)
        if len(parts) < 3: continue
        pid, age, cmd = parts
        if "tools/run_cases.py" in cmd and "watchdog" not in cmd:
            try:
                if int(age) > max_age_s: hits.append((int(pid), int(age), cmd[:80]))
            except ValueError: pass
    return hits


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--max-run-minutes", type=float, default=20); ap.add_argument("--lifetime-hours", type=float, default=4)
    a = ap.parse_args()
    os.makedirs(os.path.join(ROOT, "results"), exist_ok=True)
    log(f"watchdog start: kill scorer runs older than {a.max_run_minutes} min, lifetime {a.lifetime_hours} h")
    t_end = time.time() + a.lifetime_hours * 3600
    while time.time() < t_end:
        for pid, age, cmd in old_scorers(a.max_run_minutes * 60):
            try: os.kill(pid, 15); log(f"killed run_cases pid {pid} after {age}s: {cmd}")
            except Exception as e: log(f"could not kill {pid}: {e}")
        try:
            from builder import freya_ext as fx
            import freya
            r = freya.api("GET", "/api/v2/simulations", workspaceId=freya.workspace_id(), limit=3)
            for s in (r.get("simulations") or r.get("items") or r) or []:
                if not isinstance(s, dict) or s.get("status") != "running": continue
                created = s.get("createdAt") or ""
                try:
                    t0 = time.mktime(time.strptime(created[:19], "%Y-%m-%dT%H:%M:%S")) - time.timezone
                    age = time.time() - t0
                except Exception: age = 0
                if age > a.max_run_minutes * 60:
                    fx.cancel_simulation(s["id"]); log(f"cancelled simulation {s['id']} ({s.get('name')}) running for {age:.0f}s")
        except Exception as e:
            log(f"platform check failed: {str(e)[:120]}")
        time.sleep(120)
    log("watchdog end of lifetime")


if __name__ == "__main__":
    main()
