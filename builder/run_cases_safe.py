"""tools/run_cases.py with a watchdog: the kit's scorer polls a simulation for ever; the platform sometimes leaves one in
'running' after every call has ended. This wrapper kills the scorer after a time limit and cancels the simulation.

    python3 builder/run_cases_safe.py <agent_id> --brief A [--limit-seconds 900] [other run_cases arguments]
"""
import os, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def main(argv):
    limit = 900
    if "--limit-seconds" in argv:
        i = argv.index("--limit-seconds"); limit = int(argv[i + 1]); argv = argv[:i] + argv[i + 2:]
    from builder import freya_ext as fx
    try:
        cancelled = fx.cancel_running_simulations()
        if cancelled: print("cancelled stale simulations:", cancelled, flush=True)
    except Exception as e:
        print("warning: could not check for stale simulations (platform error):", str(e)[:120], flush=True)
    cmd = [sys.executable, os.path.join(ROOT, "tools", "run_cases.py"), *argv]
    t0 = time.time()
    try:
        # the platform answers 503/504 for minutes at a time (seen 11 October): retry a run that could not start
        for attempt in range(1, 6):
            p = subprocess.run(cmd, timeout=max(60, limit - (time.time() - t0)), capture_output=True, text=True)
            sys.stdout.write(p.stdout); sys.stderr.write(p.stderr); sys.stdout.flush()
            err = p.stderr or ""
            transient = any(x in err for x in ("-> 502", "-> 503", "-> 504", "temporarily unavailable", "Remote end closed", "timed out", "URLError",
                                               "JSONDecodeError", "Expecting value", "concurrent simulations")) and "passed" not in p.stdout
            if p.returncode == 0 or not transient or time.time() - t0 > limit - 120: return p.returncode
            print(f"\nplatform error (attempt {attempt}); waiting 60 s and retrying the run", flush=True); time.sleep(60)
            try:
                stale = fx.cancel_running_simulations()
                if stale: print("cancelled stale simulations before retrying:", stale, flush=True)
            except Exception: pass
        return p.returncode
    except subprocess.TimeoutExpired:
        print(f"\nrun_cases exceeded {limit}s; cancelling the simulation", flush=True)
        try: print("cancelled:", fx.cancel_running_simulations(), flush=True)
        except Exception as e: print("warning: cancel failed:", str(e)[:120], flush=True)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
