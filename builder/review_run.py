"""Print, for one run_cases --out file, each call's transcript with its tool calls, so a human can check the agent against a
brief whose rules differ from the public expectations (used for the Brief C rehearsal).

    python3 builder/review_run.py results/c-A.json [PUB-04 PUB-06 ...]
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from builder import freya_ext as fx  # noqa: E402


def main():
    data = json.load(open(sys.argv[1])); only = set(sys.argv[2:])
    for row in data["rows"]:
        if only and row["id"] not in only: continue
        print(f"\n===== {row['id']} {row['family']} | scorer: {'PASS' if row['pass'] else 'FAIL'} | tools: {'>'.join(row['tools'])}")
        if not row.get("call_id"): print("  (no call)"); continue
        try:
            ev = fx.call_events(row["call_id"])
        except Exception as e:
            print("  could not fetch:", str(e)[:100]); continue
        for role, txt in ev["transcript"]: print(f"  {role[:5]}: {txt[:220]}")
        for t in ev["tools"]:
            if t["tool"] == "code_exec": continue
            print(f"  [tool {t['tool']}] args={json.dumps(t.get('args'))[:160]} result={json.dumps(t.get('result'))[:100]}")
        led = fx.ledger(row["customer_id"]) if row.get("customer_id") else {}
        if isinstance(led, dict): print("  ledger:", json.dumps({k: led.get(k) for k in ("outcome", "reason", "promises", "notes", "callbacks", "transfers")})[:300])


if __name__ == "__main__":
    main()
