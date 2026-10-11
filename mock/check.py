"""Check the deployed mock against the pack's expected answers.

    python3 mock/check.py https://<worker>.workers.dev [mock/expected.json]

`expected.json` is a list of {"name", "method", "path", "body", "status", "response"}; `response` may give only the keys
that must match (deep subset). Written from the pack's test customers and service examples once they arrive.
"""
import json, sys, urllib.request, urllib.error


def call(base, method, path, body=None):
    req = urllib.request.Request(base.rstrip("/") + path, method=method, headers={"content-type": "application/json", "user-agent": "freya-mock-check/1.0"},
                                 data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=20) as r: return r.status, json.loads(r.read().decode() or "null")
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try: return e.code, json.loads(raw)
        except Exception: return e.code, raw


def subset(exp, got):
    if isinstance(exp, dict): return isinstance(got, dict) and all(k in got and subset(v, got[k]) for k, v in exp.items())
    if isinstance(exp, list): return isinstance(got, list) and len(exp) == len(got) and all(subset(a, b) for a, b in zip(exp, got))
    return exp == got


def main(base, path="mock/expected.json"):
    cases = json.load(open(path)); ok = 0
    for c in cases:
        status, got = call(base, c.get("method", "GET"), c["path"], c.get("body"))
        good = status == c["status"] and subset(c.get("response", {}), got)
        ok += good
        print(("PASS " if good else "FAIL ") + c["name"] + f" | {c.get('method','GET')} {c['path']} -> {status}" + ("" if good else f" | got {json.dumps(got, ensure_ascii=False)[:300]}"))
    print(f"{ok} / {len(cases)} checks pass")
    return 0 if ok == len(cases) else 1


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
