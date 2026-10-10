"""Run the practice cases in sequence under the watchdog and print a summary table.

    python3 builder/batch_tests.py [--reps 3] [--styles pieces,corrects,talkative,asks_back,in_words] [--briefs A,B] [--only PUB-04,PUB-06]

One simulation runs at a time per workspace, so everything here is sequential. Each run is also appended to
results/log.jsonl by the kit's scorer. Agent ids come from .freya-agents.json (slots brief-a and brief-b).
"""
import argparse, json, os, re, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def run_one(agent, letter, reps, style, only):
    cmd = [sys.executable, os.path.join(ROOT, "builder", "run_cases_safe.py"), agent, "--brief", letter, "--reps", str(reps), "--limit-seconds", str(600 * reps + 300)]
    if style: cmd += ["--style", style]
    if only: cmd += ["--only", only]
    t0 = time.time()
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    out = p.stdout
    m = re.search(r"(\d+) / (\d+) passed", out)
    failed = re.findall(r"^FAIL (PUB-\d+)", out, flags=re.M)
    return {"brief": letter, "reps": reps, "style": style or "-", "passed": m.group(1) if m else "?", "total": m.group(2) if m else "?",
            "failed": sorted(set(failed)), "seconds": round(time.time() - t0), "tail": out.strip().splitlines()[-1:] if out.strip() else [p.stderr[-200:]]}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--reps", type=int, default=3); ap.add_argument("--styles", default="")
    ap.add_argument("--briefs", default="A,B"); ap.add_argument("--only", default=None); a = ap.parse_args()
    agents = json.load(open(os.path.join(ROOT, ".freya-agents.json")))
    slot = {"A": "brief-a", "B": "brief-b"}
    rows = []
    for letter in a.briefs.split(","):
        agent = agents[slot[letter]]["agent_id"]
        for style in [None] + [s for s in a.styles.split(",") if s]:
            r = run_one(agent, letter, a.reps, style, a.only); rows.append(r)
            print(f"{letter} reps={a.reps} style={r['style']:<10} {r['passed']}/{r['total']} failed={r['failed']} {r['seconds']}s", flush=True)
    print("\nsummary"); print(f"{'brief':<6}{'style':<12}{'passed':<10}failed")
    for r in rows: print(f"{r['brief']:<6}{r['style']:<12}{str(r['passed']) + '/' + str(r['total']):<10}{', '.join(r['failed'])}")
    json.dump(rows, open(os.path.join(ROOT, "results", f"batch-{time.strftime('%m%d-%H%M')}.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
