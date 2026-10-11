"""Small additions to the kit's freya.py client: turn-by-turn chat and call event reading. Standard library only."""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path: sys.path.insert(0, ROOT)
import freya  # noqa: E402


def chat_turn(workflow_id, message, call_id=None, variables=None):
    """One turn against the published workflow. Returns (reply, call_id)."""
    body = {"workflowId": workflow_id, "message": message}
    if call_id: body["callId"] = call_id
    if variables: body["customerVariables"] = variables
    r = freya.api("POST", "/api/v2/chat/message", body)
    return (r or {}).get("response", ""), (r or {}).get("callId") or call_id


def chat_end(call_id):
    try: return freya.api("POST", "/api/v2/chat/end", {"callId": call_id})
    except Exception as e: return {"error": str(e)[:200]}


def call_events(call_id):
    """Tool calls (with args and results), node entries and the last variable table of a call."""
    call = freya.get_call(call_id)
    tools, nodes, last_vars, errors = [], [], {}, []
    for m in call.get("messages", []):
        if m.get("role") != "system": continue
        try: ev = json.loads(m.get("message") or "{}")
        except Exception: continue
        e = ev.get("event")
        if e == "node_enter": nodes.append(ev.get("node"))
        elif e == "function_call_start": tools.append({"tool": ev.get("function"), "url": (ev.get("args") or {}).get("url") if isinstance(ev.get("args"), dict) else None, "args": (ev.get("args") or {}).get("body") if isinstance(ev.get("args"), dict) else ev.get("args")})
        elif e == "function_call_complete":
            if tools and tools[-1].get("tool") == ev.get("function") and "result" not in tools[-1]: tools[-1]["result"] = (ev.get("result") or {}).get("data") if isinstance(ev.get("result"), dict) else ev.get("result")
        elif e == "function_call_error":
            if tools and tools[-1].get("tool") == ev.get("function"): tools[-1]["error"] = str(ev.get("message") or ev.get("details") or "error")[:200]
            errors.append(str(ev.get("function")) + ": " + str(ev.get("message") or ev.get("details") or "error")[:200])
        elif e == "route_evaluated":
            vt = ev.get("variable_table")
            if isinstance(vt, dict): last_vars = vt
        elif e == "error": errors.append(str(ev.get("message"))[:200])
    transcript = [(m.get("role"), m.get("message")) for m in call.get("messages", []) if m.get("role") in ("user", "assistant")]
    return {"nodes": nodes, "tools": tools, "vars": last_vars, "errors": errors, "transcript": transcript, "endedReason": call.get("endedReason")}


def practice_session(case_id):
    """Variables for a public practice case from the mock bank, or None when not available."""
    try:
        from tools.score import http
        r = http("/v1/practice/sessions", {"case": case_id})
        return r.get("variables") if isinstance(r, dict) else None
    except Exception:
        return None


def ledger(customer_id):
    try:
        from tools.score import http
        return http("/v1/practice/ledger/" + customer_id)
    except Exception as e:
        return {"error": str(e)[:200]}


def latest_simulation():
    r = freya.api("GET", "/api/v2/simulations", workspaceId=freya.workspace_id(), limit=1)
    sims = r.get("simulations") or r.get("items") or r
    return (sims or [None])[0] if isinstance(sims, list) else None


def cancel_simulation(sim_id):
    """POST /api/v2/simulations/{id}/cancel (found on 10 October): ends a simulation whose analysis hangs in 'running'."""
    return freya.api("POST", f"/api/v2/simulations/{sim_id}/cancel", {})


def cancel_running_simulations():
    """Cancel whatever simulation the workspace still reports as running, so a new one can start."""
    out = []
    r = freya.api("GET", "/api/v2/simulations", workspaceId=freya.workspace_id(), limit=5)
    for s in (r.get("simulations") or r.get("items") or r) or []:
        if isinstance(s, dict) and s.get("status") == "running":
            try: cancel_simulation(s["id"]); out.append(s["id"])
            except Exception: pass
    return out
