"""Copy the pack's test customers into the Worker (`src/data.json`) and write `expected.json` for check.py.

    python3 mock/build_data.py case/test-environment/test-customers.json
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
# service name -> (method, path, request fields that select the answer). Provisional until the bank's integration
# document fixes paths and field names; `routes.js` reads the same table from data.json.
# service -> (path, fields that select the answer in the pack, 404 code for an unknown record or "" for a 400)
# From the service contract: card services carry only the card number, so the customer is found through the card.
SERVICES = {
    "cards.list":            ("/voice/v1/cards.list",            ["customerNo"],                   "FB_IVR_CHANNEL_102"),
    "cards.balance":         ("/voice/v1/cards.balance",         ["cardNumber"],                   "FB_IVR_CHANNEL_120"),
    "statement.week.get":    ("/voice/v1/statement.week.get",    ["cardNumber"],                   "FB_IVR_CHANNEL_121"),
    "statement.week.decide": ("/voice/v1/statement.week.decide", ["cardNumber", "newStatementWeek"], ""),
    "statement.week.change": ("/voice/v1/statement.week.change", ["cardNumber", "newStatementWeek"], ""),
    "contact.email.get":     ("/voice/v1/contact.email.get",     ["customerNo"],                   ""),
    "statement.pdf.send":    ("/voice/v1/statement.pdf.send",    ["customerNo", "cardNumber"],     "FB_IVR_CHANNEL_107"),
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
    data = {"services": {k: {"path": p, "keys": f, "notFound": nf} for k, (p, f, nf) in SERVICES.items()}, "customers": {}, "cards": {}}
    expected = []
    for c in pack["customers"]:
        no = str(c["customerNo"]); entry = {"firstName": c.get("firstName"), "lastName": c.get("lastName"), "services": {}}
        for svc, tree in (c.get("services") or {}).items():
            if svc not in SERVICES: continue
            fields = SERVICES[svc][1]
            card_keyed = fields[0] == "cardNumber"
            table = {}
            for key, a in answers(tree, fields[1:] if not card_keyed else fields):
                table["|".join(key)] = {"http": a.get("http", 200), "delay": a.get("delaySeconds") or a.get("gecikmeSaniye") or 0, "body": a.get("response", a.get("yanit"))}
                body = {"data": {}, "call": {"ani": "05000000000", "lang": "tr"}}
                if not card_keyed: body["data"]["customerNo"] = no
                for f, v in zip(fields[1:] if not card_keyed else fields, key): body["data"][f] = v
                if svc == "cards.list": body["data"]["aiFlow"] = "CardOps"
                if svc == "contact.email.get": body["data"]["intAddressInfoType"] = "E"
                if svc in ("statement.week.decide", "statement.week.change"): body["data"]["statementDay"] = 5
                if svc == "statement.pdf.send":
                    cards = ((((c.get("services") or {}).get("cards.list") or {}).get("response") or {}).get("data") or {}).get("cards") or []
                    body["data"].setdefault("cardNumber", (cards[0].get("cardNumber") if cards else "540000******0000"))
                    body["data"].update({"currencyType": "TL", "statementDate": "05.10.2026", "emailAddress": "x@example"})
                if card_keyed and key: data["cards"].setdefault(key[0], []).append(no)
                expected.append({"name": f"{no} {svc} {'/'.join(key)}", "method": "POST", "path": SERVICES[svc][0], "body": body,
                                 "status": a.get("http", 200), "response": a.get("response", a.get("yanit"))})
            entry["services"][svc] = table
        data["customers"][no] = entry
    data["cards"] = {k: sorted(set(v)) for k, v in data["cards"].items()}
    shared = {k: v for k, v in data["cards"].items() if len(v) > 1}
    json.dump(data, open(os.path.join(HERE, "src", "data.json"), "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(expected, open(os.path.join(HERE, "expected.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print(f"customers={len(data['customers'])} cards={len(data['cards'])} shared card numbers={len(shared)} {list(shared.items())[:3]} answers={len(expected)}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "case/test-environment/test-customers.json")
