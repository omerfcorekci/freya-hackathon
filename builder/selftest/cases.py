"""Run the kit's practice cases for this brief, when a case file exists, and copy the verdicts into the trace."""
import json, os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def detect(a):
    cases = a.cases or (os.path.join(ROOT, "public-test-set.json") if os.path.exists(os.path.join(ROOT, "public-test-set.json")) else None)
    letter = a.brief_letter
    if not letter:
        m = re.search(r"brief-([a-z])", os.path.basename(a.briefs[-1]).lower())
        letter = m.group(1).upper() if m else None
    if cases and letter:
        ids = [c["id"] for c in json.load(open(cases)) if c.get("brief") == letter]
        if ids: return cases, letter, ids
    return None, None, []


def run(a, spec, agent_id, trace, budget):
    cases, letter, ids = detect(a)
    if not cases:
        trace.test("cases", "SKIP", "no practice case file matches this brief"); return
    est = 60 + 25 * len(ids)
    if not budget.allows(est, f"practice cases ({len(ids)})"): return
    out = os.path.join(ROOT, "out", a.slot, "cases.json")
    cmd = [sys.executable, os.path.join(ROOT, "tools", "run_cases.py"), agent_id, "--brief", letter, "--cases", cases, "--out", out]
    trace.info("running: " + " ".join(os.path.relpath(c, ROOT) if os.path.isabs(c) else c for c in cmd))
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=max(120, budget.remaining() - 30))
    except subprocess.TimeoutExpired:
        trace.test("cases", "FAIL", "timed out"); return
    for line in p.stdout.splitlines():
        if line.startswith(("PASS", "FAIL")): trace.test("cases/" + line.split()[1], line.split()[0], line.split("|", 1)[-1].strip()[:160])
        elif line.strip().startswith("-"): trace.info("   " + line.strip()[:200])
    m = re.search(r"(\d+) / (\d+) passed", p.stdout)
    trace.test("cases/total", "PASS" if m and m.group(1) == m.group(2) else "FAIL", m.group(0) if m else (p.stderr[-300:] or "no summary"))
