"""Offline self-test: run the generated code nodes locally for several call dates and check brief-independent invariants."""
import datetime, json

from builder import codegen, datefacts


def _nows(spec):
    cal = spec.get("calendar") or {}; hol = sorted(cal.get("holidays") or [])
    base = datetime.date.today()
    out = [base.isoformat() + "T11:00"]
    for h in hol[:2]:
        d = datetime.date.fromisoformat(h); out.append((d - datetime.timedelta(days=1)).isoformat() + "T11:00"); out.append(d.isoformat() + "T11:00")
    fri = base + datetime.timedelta(days=(4 - base.weekday()) % 7); out.append(fri.isoformat() + "T18:55")
    out.append(base.replace(month=12, day=31).isoformat() + "T10:00")
    return out


def run(spec, cfg, trace):
    cal = cfg["calendar"]; ok = 0; total = 0; fails = []
    products = [{"product_id": "p1", "type": "credit_card", "card_last4": "0000", "past_due": 300.0, "days_late": 5, "minimum_payment": 90.0},
                {"product_id": "p2", "type": "personal_loan", "past_due": 900.0, "days_late": 20, "instalment_amount": 300.0}]
    for now in _nows(spec):
        total += 1
        try:
            v = {cfg["customer_id_var"]: "c", cfg["now_var"]: now, "products": products}
            datefacts.sandbox_exec(codegen.code_source("product_facts", cfg), v)
            assert v.get("route") == "negotiate", "route " + str(v.get("route")) + " " + str(v.get("node_error"))
            today = datetime.date.fromisoformat(now[:10])
            for k in (1, 2):
                dl = v.get(f"p{k}_deadline")
                assert dl, f"p{k} has no deadline"
                d = datetime.date.fromisoformat(dl)
                assert d > today and d.weekday() in cal["business_weekdays"] and dl not in cal["holidays"], f"p{k} deadline {dl} not a business day after today"
                assert float(v.get(f"p{k}_floor", 0)) <= float(v.get(f"p{k}_full", 0)), f"p{k} floor above full"
            v.update({"stance": "refuses"}); datefacts.sandbox_exec(codegen.code_source("eval", cfg), v)
            assert v.get("route") in ("negotiate", "confirm", "close"), "eval route " + str(v.get("route")) + " " + str(v.get("node_error"))
            od = v.get("p1_offer_date") or ""
            if od: assert od != today.isoformat() or v.get("multi_mode"), "first offer is today"
            ok += 1
        except Exception as e:
            fails.append(f"now={now}: {e}")
    trace.test("offline/code_nodes", "PASS" if ok == total else "FAIL", f"{ok}/{total} call dates" + (" | " + "; ".join(fails)[:400] if fails else ""))
    return ok == total
