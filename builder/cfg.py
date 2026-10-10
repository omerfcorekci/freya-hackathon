"""CFG: what the code nodes and hooks receive. Built from the spec and the tool API; nothing in it is hand-written."""
import copy, re


def _placeholders(obj):
    """{{var}} in spec sentences becomes [[var]] so that code sources never contain double braces."""
    if isinstance(obj, str): return re.sub(r"{{\s*([A-Za-z_][\w]*)\s*}}", r"[[\1]]", obj)
    if isinstance(obj, list): return [_placeholders(x) for x in obj]
    if isinstance(obj, dict): return {k: _placeholders(v) for k, v in obj.items()}
    return obj


def _pick(names, *needles, default=None):
    for n in needles:
        for name in names:
            if n in name.lower(): return name
    return default


def resolve_roles(spec, api):
    """Which field plays which role in each tool, read from the tool API (names and enums may differ per brief)."""
    r = {}
    ga = api.tool("get_account") if api.has("get_account") else {"fields": {}, "response_schema": {}}
    props = (ga.get("response_schema") or {}).get("properties") or {}
    list_field = None; item_props = {}
    for name, p in props.items():
        if p.get("type") == "array":
            list_field = name; item_props = ((p.get("items") or {}).get("properties") or {}); break
    r["products_field"] = list_field or "products"
    names = list(item_props.keys())
    r["id"] = _pick(names, "product_id", "_id", "id", default="product_id")
    r["type"] = _pick(names, "type", "kind", "product", default="type")
    r["past_due"] = _pick(names, "past_due", "due", "overdue", "balance", "amount", default="past_due")
    r["days_late"] = _pick(names, "days_late", "late", "days", "dpd", default="days_late")
    r["product_fields"] = names
    def body(tool): return list(api.tool(tool)["fields"].keys()) if api.has(tool) else []
    def typed(tool, typ):
        if not api.has(tool): return None
        for n, f in api.tool(tool)["fields"].items():
            if f.get("type") == typ and n != "customer_id": return n
        return None
    def fmt(tool, f):
        if not api.has(tool): return None
        for n, fd in api.tool(tool)["fields"].items():
            if fd.get("format") == f: return n
        return None
    cp = body("create_promise")
    r["cp_product"] = _pick(cp, "product", default="product_id"); r["cp_amount"] = typed("create_promise", "number") or _pick(cp, "amount", default="amount")
    r["cp_date"] = fmt("create_promise", "date") or _pick(cp, "date", "day", default="date")
    sc = body("schedule_callback")
    r["cb_date"] = fmt("schedule_callback", "date") or _pick(sc, "date", "day", default="date"); r["cb_time"] = _pick(sc, "time", "hour", default="time")
    an = body("add_note")
    r["note_product"] = _pick(an, "product", default="product_id"); r["note_reason"] = _pick(an, "reason", "code", default="reason"); r["note_text"] = _pick(an, "text", "note", "comment", default=None)
    ta = body("transfer_to_agent"); r["queue"] = _pick(ta, "queue", "team", "department", default="queue")
    cc = body("close_call"); r["outcome"] = _pick(cc, "outcome", "result", "status", default="outcome"); r["reason"] = _pick(cc, "reason", "code", default="reason")
    vi = body("verify_identity")
    enum_field = None
    if api.has("verify_identity"):
        for n, f in api.tool("verify_identity")["fields"].items():
            if f.get("enum"): enum_field = n; break
    r["vi_field"] = enum_field or _pick(vi, "field", "question", "kind", default="field")
    r["vi_answer"] = _pick([x for x in vi if x not in (r["vi_field"], "customer_id")], "answer", "value", default=None) or next((x for x in vi if x not in (r["vi_field"], "customer_id")), "answer")
    r["customer_id"] = "customer_id"
    return r


def build_cfg(spec, api):
    spec = _placeholders(copy.deepcopy(spec))
    cal = spec.get("calendar") or {}
    cfg = {
        "spec": spec,
        "calendar": {"business_weekdays": cal.get("business_weekdays") or [0, 1, 2, 3, 4], "holidays": list(cal.get("holidays") or []),
                     "next_weekday_means": cal.get("next_weekday_means") or "following_calendar_week",
                     "currency_word": (spec.get("meta") or {}).get("currency_word") or "", "band_fallback": "last"},
        "roles": resolve_roles(spec, api),
        "now_var": (spec.get("call_variables") or {}).get("now") or "now",
        "customer_id_var": (spec.get("call_variables") or {}).get("customer_id") or "customer_id",
        "note_reasons": list(api.enum("add_note", "reason") or []) if api.has("add_note") else [],
        "has_add_note": api.has("add_note"),
        "close_reasons": {o.get("outcome"): list(o.get("reasons") or []) for o in (spec.get("closing") or {}).get("outcomes") or []},
    }
    return cfg
