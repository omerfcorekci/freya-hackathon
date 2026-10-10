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
    cancelled = fx.cancel_running_simulations()
    if cancelled: print("cancelled stale simulations:", cancelled, flush=True)
    cmd = [sys.executable, os.path.join(ROOT, "tools", "run_cases.py"), *argv]
    t0 = time.time()
    try:
        p = subprocess.run(cmd, timeout=limit)
        return p.returncode
    except subprocess.TimeoutExpired:
        print(f"\nrun_cases exceeded {limit}s; cancelling the simulation", flush=True)
        print("cancelled:", fx.cancel_running_simulations(), flush=True)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
