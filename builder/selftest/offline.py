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
    cal = cfg["calendar"]; ok = 0; total = 0; fails = []; roles = cfg["roles"]
    types = list(((spec.get("debt_statement") or {}).get("product_wording") or {}).keys()) or ["product"]
    floor_fields = (spec.get("amount_rules") or {}).get("floor_by_type") or {}
    bands = spec.get("bands") or []
    late_a = int(bands[0].get("days_late_min", 1) or 1) + 1 if bands else 5
    late_b = int(bands[-1].get("days_late_min", 20) or 20) + 1 if bands else 20
    def product(i, typ, due, late):
        p = {roles["id"]: f"p{i}", roles["type"]: typ, roles["past_due"]: due, roles["days_late"]: late, "card_last4": "0000"}
        ff = floor_fields.get(typ)
        if ff: p[ff] = round(due * 0.3, 2)
        return p
    products = [product(1, types[0], 300.0, late_a), product(2, types[-1], 900.0, late_b)]
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
    # spoken security answers are normalised in code: check the formats this brief uses
    ns = datefacts.lib_namespace(); exec(codegen.NODE_MIN, ns)
    words = ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
    bad = []
    for q in (spec.get("identity") or {}).get("questions") or []:
        fmt = q.get("answer_format") or "text"; qq = dict(q)
        n = int(qq.get("digits_len") or 4); digits = "".join(str((i % 9) + 1) for i in range(n))
        samples = {"date_ymd": [("the twenty-eighth of April nineteen ninety-three", "1993-04-28"), ("14/03/1988", "1988-03-14"), ("March 14, 1988", "1988-03-14")],
                   "digits": [(" ".join(words[int(d) - 1] for d in digits), digits), (digits, digits), (digits[: n // 2] + " " + digits[n // 2:], digits)],
                   "year": [("two thousand and twelve", "2012"), ("1998", "1998")], "alnum": [("sw1a 1aa", "SW1A1AA")]}
        for text, want in samples.get(fmt, []):
            got, complete = ns["_norm_answer"](text, qq)
            if not complete or got != want: bad.append(f"{fmt}: {text!r} -> {got!r}")
    trace.test("offline/answer_formats", "PASS" if not bad else "FAIL", "; ".join(bad)[:300] if bad else "spoken answers normalise")
    return ok == total and not bad
