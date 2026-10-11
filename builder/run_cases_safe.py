"""tools/run_cases.py with a watchdog and a resilient platform client: nothing runs for ever, and a platform that
answers 5xx for a minute (seen all Sunday morning) does not kill a run whose calls are already happening.

    python3 builder/run_cases_safe.py <agent_id> --brief A [--limit-seconds 900] [other run_cases arguments]

The kit's scorer runs in-process; every call it makes through freya.api and score.http is retried with back-off on
5xx, timeouts and non-JSON answers. The kit files are not changed.
"""
import json, os, sys, threading, time, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tools"))

TRANSIENT = ("-> 502", "-> 503", "-> 504", "-> 500", "temporarily unavailable", "timed out", "Remote end closed", "URLError", "Expecting value")


def retrying(fn, name, tries=8):
    def wrapped(*args, **kwargs):
        delay = 10
        for attempt in range(1, tries + 1):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                msg = f"{type(e).__name__}: {e}"
                if attempt == tries or not any(t in msg for t in TRANSIENT): raise
                print(f"[{name}] transient platform error (attempt {attempt}/{tries}): {msg[:100]}; retrying in {delay}s", flush=True)
                time.sleep(delay); delay = min(60, delay * 2)
    return wrapped


def main(argv):
    limit = 900
    if "--limit-seconds" in argv:
        i = argv.index("--limit-seconds"); limit = int(argv[i + 1]); argv = argv[:i] + argv[i + 2:]
    import freya, score
    from builder import freya_ext as fx
    freya.api = retrying(freya.api, "freya.api")
    score.http = retrying(score.http, "bank")
    try:
        stale = fx.cancel_running_simulations()
        if stale: print("cancelled stale simulations:", stale, flush=True)
    except Exception as e:
        print("warning: could not check for stale simulations:", str(e)[:100], flush=True)
    import run_cases
    run_cases.freya = freya; run_cases.http = score.http   # the scorer imported these names before the patch
    result = {"code": 0}

    def work():
        sys.argv = ["run_cases.py", *argv]
        try: run_cases.main()
        except SystemExit as e: result["code"] = int(e.code or 0)
        except Exception as e:
            print("run_cases failed:", f"{type(e).__name__}: {str(e)[:300]}", flush=True); result["code"] = 1

    t = threading.Thread(target=work, daemon=True); t.start(); t.join(limit)
    if t.is_alive():
        print(f"\nrun_cases exceeded {limit}s; cancelling the simulation", flush=True)
        try: print("cancelled:", fx.cancel_running_simulations(), flush=True)
        except Exception as e: print("warning: cancel failed:", str(e)[:100], flush=True)
        os._exit(2)
    return result["code"]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
