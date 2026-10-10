"""Chat self-test: plays scripted customers against the saved workflow through POST /api/v2/chat/message and checks
tool calls, the ledger (when the mock bank knows the customer) and the transcript. Needs no simulation slot."""
import json, os, time

from builder import freya_ext as fx
from builder.selftest import scenarios as sc

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _session_for(spec, cfg, cases_path):
    """A practice case whose identity fields match the spec's questions, so the chat scenarios can verify for real."""
    if not cases_path or not os.path.exists(cases_path): return None
    want = [q.get("field") for q in (spec.get("identity") or {}).get("questions") or []]
    for c in json.load(open(cases_path)):
        ident = c.get("identity") or {}
        if want and all(f in ident for f in want) and c.get("family") == "Happy path":
            v = fx.practice_session(c["id"])
            if v: return {"variables": v, "identity": ident, "case": c["id"]}
    return None


def run(spec, cfg, api, workflow_id, trace, budget, cases_path=None):
    session = _session_for(spec, cfg, cases_path)
    scen = sc.generate(spec, cfg, session)
    if not scen: trace.test("chat", "SKIP", "no scenarios"); return
    passed = 0
    for s in scen:
        if not budget.allows(90, "chat/" + s["name"]): break
        try: ok, detail = _play(s, cfg, workflow_id, session)
        except Exception as e: ok, detail = False, f"{type(e).__name__}: {str(e)[:160]}"
        trace.test("chat/" + s["name"], "PASS" if ok else "FAIL", detail); passed += ok
    trace.test("chat/total", "PASS" if passed == len(scen) else "FAIL", f"{passed}/{len(scen)} scenarios")


def _play(s, cfg, workflow_id, session):
    variables = dict((session or {}).get("variables") or {})
    if not variables: variables = {cfg["customer_id_var"]: "c_selftest", cfg["now_var"]: "2026-01-14T11:00", "first_name": "Test", "last_name": "Customer", "title": "Ms"}
    # a fresh session per scenario when the mock bank knows the case
    if session and session.get("case"):
        v = fx.practice_session(session["case"])
        if v: variables = v
    call_id = None; transcript = []
    for i, line in enumerate(s["turns"]):
        reply, call_id = fx.chat_turn(workflow_id, line, call_id, variables if i == 0 else None)
        transcript.append(("user", line)); transcript.append(("assistant", reply or ""))
    fx.chat_end(call_id)
    ev = fx.call_events(call_id)
    tools = [t["tool"] for t in ev["tools"] if t["tool"] != "code_exec"]
    problems = []
    exp = s.get("expect_tools") or []
    if [t for t in tools if t in exp] != exp and tools != exp: problems.append(f"tools {tools} expected {exp}")
    fb = s.get("forbid_before") or {}
    if fb:
        said_before = " ".join(r for role, r in transcript if role == "assistant")
        cut = None
        for t in ev["tools"]:
            if t["tool"] == fb["tool"]: cut = True; break
        # assistant lines before the first expected tool call: approximate with the whole transcript up to that call's turn
        for w in fb.get("words") or []:
            if w.lower() in said_before.lower()[: max(0, len(said_before) // 2 if cut else len(said_before))]: problems.append(f"said '{w}' before {fb['tool']}")
    for must in s.get("must_say") or []:
        if must and must.lower() not in " ".join(r for role, r in transcript if role == "assistant").lower(): problems.append(f"did not say '{must[:40]}'")
    el = s.get("expect_ledger") or {}
    if el and variables.get("customer_id", "").startswith("c_") and session:
        led = fx.ledger(variables["customer_id"])
        if isinstance(led, dict) and "outcome" in led:
            if el.get("outcome") and led.get("outcome") != el["outcome"]: problems.append(f"ledger outcome {led.get('outcome')} expected {el['outcome']}")
            if "reason" in el and (led.get("reason") or "") != (el.get("reason") or ""): problems.append(f"ledger reason {led.get('reason')} expected {el.get('reason')}")
            if "promises" in el and len(led.get("promises") or []) != el["promises"]: problems.append(f"ledger promises {len(led.get('promises') or [])} expected {el['promises']}")
            if el.get("callback"):
                cbs = led.get("callbacks") or []
                if not cbs or (cbs[0].get("date"), cbs[0].get("time")) != (el["callback"]["date"], el["callback"]["time"]): problems.append(f"ledger callbacks {cbs} expected {el['callback']}")
    if ev["errors"]: problems.append("engine errors: " + "; ".join(ev["errors"])[:200])
    detail = ("call=" + str(call_id) + " tools=" + ">".join(tools)) + (" | " + "; ".join(problems) if problems else "")
    return (not problems), detail[:400]
