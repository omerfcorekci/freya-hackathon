"""Copy the pack's test customers into the Worker (`src/data.json`) and write `expected.json` for check.py.

    python3 mock/build_data.py case/test-environment/test-customers.json
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
# service name -> (method, path, request fields that select the answer). Provisional until the bank's integration
# document fixes paths and field names; `routes.js` reads the same table from data.json.
SERVICES = {
    "cards.list":            ("POST", "/voice/v1/cards.list",            ["customerNo"]),
    "cards.balance":         ("POST", "/voice/v1/cards.balance",         ["customerNo", "cardNumber"]),
    "statement.week.get":    ("POST", "/voice/v1/statement.week.get",    ["customerNo", "cardNumber"]),
    "statement.week.decide": ("POST", "/voice/v1/statement.week.decide", ["customerNo", "cardNumber", "newStatementWeek"]),
    "statement.week.change": ("POST", "/voice/v1/statement.week.change", ["customerNo", "cardNumber", "newStatementWeek"]),
    "contact.email.get":     ("POST", "/voice/v1/contact.email.get",     ["customerNo"]),
    "statement.pdf.send":    ("POST", "/voice/v1/statement.pdf.send",    ["customerNo", "cardNumber"]),
}


def answers(node, keys):
    """Flatten the nested answer tree of one service into (key tuple, answer)."""
    if isinstance(node, dict) and "http" in node: return [((), node)]
    out = []
    for k, v in (node or {}).items():
        for sub, a in answers(v, keys[1:]): out.append(((k,) + sub, a))
    return out


def main(src):
    pack = json.load(open(src, encoding="utf-8"))
    data = {"services": {k: {"method": m, "path": p, "keys": f} for k, (m, p, f) in SERVICES.items()}, "customers": {}}
    expected = []
    for c in pack["customers"]:
        no = str(c["customerNo"]); entry = {"firstName": c.get("firstName"), "lastName": c.get("lastName"), "services": {}}
        for svc, tree in (c.get("services") or {}).items():
            if svc not in SERVICES: continue
            fields = SERVICES[svc][2][1:]                      # keys after the customer number
            table = {}
            for key, a in answers(tree, fields):
                table["|".join(key)] = {"http": a.get("http", 200), "delay": a.get("gecikmeSaniye") or 0, "body": a.get("response", a.get("yanit"))}
                body = {"data": {"customerNo": no}, "call": {"callId": "check", "channel": "IVR"}}
                for f, v in zip(fields, key): body["data"][f] = v
                expected.append({"name": f"{no} {svc} {'/'.join(key)}", "method": SERVICES[svc][0], "path": SERVICES[svc][1], "body": body,
                                 "status": a.get("http", 200), "response": a.get("response", a.get("yanit"))})
            entry["services"][svc] = table
        data["customers"][no] = entry
    json.dump(data, open(os.path.join(HERE, "src", "data.json"), "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(expected, open(os.path.join(HERE, "expected.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print(f"customers={len(data['customers'])} answers={len(expected)} -> mock/src/data.json, mock/expected.json")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "case/test-environment/test-customers.json")
