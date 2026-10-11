"""Lint a workflow file and dry-run it on the platform. Prints every problem, or `ok`.

    python3 builder/validate_case.py out/final/workflow.json
"""
import json, os, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from builder import lint as lintmod  # noqa: E402


def main(path):
    try: wf = json.load(open(path, encoding="utf-8"))
    except Exception as e:
        print("ERROR not valid JSON:", e); return 1
    errors, warnings = lintmod.lint(wf)
    for w in warnings: print("WARN", w)
    for e in errors: print("ERROR", e)
    if errors: return 1
    import freya
    for attempt in range(4):
        try:
            freya.validate_workflow("validate", wf); print("dryrun ok"); break
        except Exception as e:
            msg = str(e)
            if any(code in msg for code in (" 502", " 503", " 504", "timed out")) and attempt < 3:
                print("platform busy, retrying in 10 s"); time.sleep(10); continue
            print("ERROR dryrun:", msg[:1500]); return 1
    print("ok nodes=%d" % len(wf.get("nodes") or {}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "out/final/workflow.json"))
