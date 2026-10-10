"""Logic of the generated code nodes. This source is shipped verbatim into every code node of the workflow,
after the date library (datefacts.LIB_SOURCE), and dispatched by MODE. It runs in Freya's sandbox: only json, re and
datetime; reads and writes the call's variable table through `vars`; must never raise; must not contain a double
opening or closing brace sequence (the platform treats those as placeholders), so nested literals are built step by step.

The same functions run offline in tests (builder/tests) against the same library, so what we test is what runs.
Call variables from the brief are referred to by the names in CFG['spec']['call_variables'].
"""
import json, re, datetime


# ---- small helpers ------------------------------------------------------------------------------------------------

def _g(vars, name, default=""):
    v = vars.get(name)
    return default if v is None or v == "" else v

def _gi(vars, name, default=0):
    try: return int(float(_g(vars, name, default)))
    except Exception: return default

def _gf(vars, name, default=0.0):
    try: return float(_g(vars, name, default))
    except Exception: return default

def _fill(text, vars):
    """Replace [[name]] with the call variable's value (spec sentences carry call variables this way)."""
    try:
        def rep(m): return str(vars.get(m.group(1), "") or "")
        return re.sub(r"\[\[\s*([A-Za-z_][\w]*)\s*\]\]", rep, str(text or ""))
    except Exception: return str(text or "")

def _cal(CFG): return CFG.get("calendar") or dict()

def _today(vars, CFG):
    now = _parse_now(str(_g(vars, CFG.get("now_var", "now"), "")))
    if now is None: now = datetime.datetime.now()
    return now

def _outcome(vars, obj, fallback_outcome="", fallback_reason=""):
    obj = obj if isinstance(obj, dict) else dict()
    vars["outcome"] = str(obj.get("outcome") or fallback_outcome or "")
    vars["reason"] = str(obj.get("reason") or fallback_reason or "")

def _money(x, CFG): return _speak_money(x, _cal(CFG))

def _pk(k, name): return "p" + str(int(k)) + "_" + name

def _pget(vars, k, name, default=""): return _g(vars, _pk(k, name), default)
def _pset(vars, k, name, value): vars[_pk(k, name)] = value

def _n_products(vars): return _gi(vars, "n_products", 0)

def _spec(CFG): return CFG.get("spec") or dict()

def _s(CFG, path, default=None):
    cur = _spec(CFG)
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur: return default
        cur = cur[part]
    return default if cur is None or cur == "" else cur

def _situation_outcome(CFG, situation):
    """The close_call outcome object for a product-level situation."""
    m = dict()
    m["refused"] = _s(CFG, "persuasion.exhausted")
    m["hardship"] = _s(CFG, "hardship.decline_outcome")
    m["dispute"] = _s(CFG, "situations.dispute.outcome")
    m["paid"] = _s(CFG, "situations.already_paid.outcome")
    m["service_error"] = _s(CFG, "confirmation.failure_outcome")
    return m.get(situation) or dict()

def _note_reason(CFG, situation):
    rm = _s(CFG, "multi_product.notes_reason_map") or dict()
    if situation in rm and rm[situation]: return str(rm[situation])
    direct = dict()
    direct["hardship"] = _s(CFG, "hardship.decline_note_reason")
    direct["dispute"] = _s(CFG, "situations.dispute.note_reason")
    direct["paid"] = _s(CFG, "situations.already_paid.note_reason")
    direct["service_error"] = _s(CFG, "confirmation.failure_note_reason")
    if direct.get(situation): return str(direct[situation])
    allowed = CFG.get("note_reasons") or []
    return situation if situation in allowed else ""


# ---- opening --------------------------------------------------------------------------------------------------------

def _node_opening_tally(vars, CFG):
    """After an opening turn that did not identify who is on the line."""
    ack = str(_g(vars, "ack", "none"))
    vars["ack"] = "none"
    ask = _fill(_s(CFG, "opening.ask_for_customer", "Am I speaking with the account holder?"), vars)
    route = "again"
    if ack == "wants_human":
        vars["resume_to"] = "opening"; route = "human"
    elif ack == "refuses":
        n = _gi(vars, "dnt_count", 0) + 1; vars["dnt_count"] = n
        if n >= int(_s(CFG, "situations.dont_want_to_talk.times", 2) or 2):
            _outcome(vars, _s(CFG, "situations.dont_want_to_talk.before_verified") or _s(CFG, "identity.declined.outcome"))
            vars["farewell_instruction"] = "Say you understand and will not keep them. Thank them and say goodbye."
            route = "close"
    if route == "again":
        n = _gi(vars, "ask_count", 1) + 1; vars["ask_count"] = n
        if n > int(_s(CFG, "opening.max_asks", 2) or 2):
            _outcome(vars, _s(CFG, "opening.unclear"))
            vars["farewell_instruction"] = "Say you could not confirm who is on the line and will call back another time. Say goodbye."
            route = "close"
        else:
            vars["op_instruction"] = ("If the customer asked something, answer it in one short sentence first (standard replies). "
                                      "Do not say why you are calling. Then ask again, exactly: " + ask)
    vars["route"] = route


# ---- identity ---------------------------------------------------------------------------------------------------------

def _questions(CFG): return list(_s(CFG, "identity.questions") or [])

def _node_identity_prep(vars, CFG):
    qs = _questions(CFG)
    vars["id_done"] = ""; vars["id_wrong"] = 0; vars["id_state"] = "continue"; vars["id_refusals"] = 0
    vars["id_stance"] = "answering"; vars["resume_to"] = "identity"
    if qs:
        vars["id_next_field"] = str(qs[0].get("field", ""))
        vars["id_instruction"] = ("Thank the customer briefly. Say you need to ask two quick security questions. Then ask for " +
                                  str(qs[0].get("ask", "the first security answer")) + ". Ask nothing else.")
    else:
        vars["id_next_field"] = ""; vars["id_state"] = "verified"
        vars["id_instruction"] = "Thank the customer."
    vars["route"] = "identity"


def _node_identity_tally(vars, CFG):
    """A turn in the identity step where the customer did not answer the question."""
    st = str(_g(vars, "id_stance", "answering")); vars["id_stance"] = "answering"
    qs = _questions(CFG); cur = str(_g(vars, "id_next_field", ""))
    ask = ""
    for q in qs:
        if str(q.get("field", "")) == cur: ask = str(q.get("ask", ""))
    route = "identity"
    if st == "wants_human":
        vars["resume_to"] = "identity"; route = "human"
    elif st in ("declines", "asks_what_about", "dont_want_to_talk"):
        n = _gi(vars, "id_refusals", 0) + 1; vars["id_refusals"] = n
        limit = int(_s(CFG, "identity.declined.max_refusals", 2) or 2)
        if st == "dont_want_to_talk":
            d = _gi(vars, "dnt_count", 0) + 1; vars["dnt_count"] = d
            limit = min(limit, int(_s(CFG, "situations.dont_want_to_talk.times", 2) or 2))
        if n >= limit:
            _outcome(vars, _s(CFG, "identity.declined.outcome"))
            vars["farewell_instruction"] = "Say that without the security check you cannot continue today. Thank them and say goodbye."
            route = "close"
        else:
            explain = str(_s(CFG, "identity.declined.explain_once", "These questions protect your account.") or "")
            vars["id_instruction"] = ("Say exactly: " + explain + " Do not say why you are calling. Then ask again for " + (ask or "the security answer") + ".")
    else:
        vars["id_instruction"] = "Ask again for " + (ask or "the security answer") + "."
    vars["route"] = route


# ---- third party ------------------------------------------------------------------------------------------------------

def _cb_allowed_dates(today, CFG):
    cb = _s(CFG, "third_party.callback") or dict(); cal = _cal(CFG)
    kind = str(cb.get("days_kind") or "today_or_next_business_day"); n = int(cb.get("days_n") or 0)
    out = [today]
    if kind == "today_only": return out
    if kind == "today_or_next_business_day": return out + [_next_business_day(today, cal)]
    if kind == "within_n_business_days":
        d = today
        for i in range(max(n, 1)):
            d = _next_business_day(d, cal); out.append(d)
        return out
    if kind == "within_n_calendar_days": return [today + datetime.timedelta(days=i) for i in range(max(n, 1) + 1)]
    return out + [_next_business_day(today, cal)]


def _node_tp_eval(vars, CFG):
    now = _today(vars, CFG); today = now.date(); cal = _cal(CFG)
    st = str(_g(vars, "tp_stance", "other")); vars["tp_stance"] = "other"
    dtext = str(_g(vars, "cb_date_text", "")); ttext = str(_g(vars, "cb_time_text", ""))
    vars["cb_date_text"] = ""; vars["cb_time_text"] = ""
    cb = _s(CFG, "third_party.callback") or dict()
    route = "again"
    if st == "wrong_number":
        _outcome(vars, _s(CFG, "third_party.wrong_number.outcome")); vars["farewell_instruction"] = "Apologise for the inconvenience and say goodbye."; route = "close"
    elif st == "deceased":
        _outcome(vars, _s(CFG, "third_party.deceased.outcome")); vars["farewell_instruction"] = "Say exactly: " + str(_s(CFG, "third_party.deceased.sentence", "I am sorry for your loss.")) + " Ask nothing else and say goodbye."; route = "close"
    elif st == "refuses" or not cb.get("enabled", True):
        _outcome(vars, cb.get("not_scheduled") or _s(CFG, "opening.unclear")); vars["farewell_instruction"] = "Thank them and say goodbye."; route = "close"
    else:
        allowed = _cb_allowed_dates(today, CFG)
        d_status, d_val = _resolve_date_expr(dtext, now, cal) if dtext else ("none", "")
        d = _to_date(d_val) if d_status == "date" else None
        t = _parse_time(ttext) if ttext else None
        if d is None and t is not None:
            # a time with no day: today if still ahead, else the next allowed day
            if t > now.strftime("%H:%M"): d = today
            elif len(allowed) > 1: d = allowed[1]
        ws = str(cb.get("window_start") or "00:00"); we = str(cb.get("window_end") or "23:59")
        ok = d is not None and t is not None and d in allowed and ws <= t <= we
        if ok and cb.get("after_now", True) and d == today and t <= now.strftime("%H:%M"): ok = False
        if ok:
            vars["cb_date"] = d.isoformat(); vars["cb_time"] = t; route = "schedule"
            vars["farewell_instruction"] = "Say you will call back on " + str(_speak_date(d.isoformat())) + " at " + t + ". Thank them and say goodbye."
        else:
            tries = _gi(vars, "cb_tries", 0) + 1; vars["cb_tries"] = tries
            if tries > int(cb.get("retries_if_outside") or 1):
                _outcome(vars, cb.get("not_scheduled")); vars["farewell_instruction"] = "Say you will try again another time. Thank them and say goodbye."; route = "close"
            else:
                days = " or ".join(_speak_date(x.isoformat()) or "" for x in allowed[:2])
                vars["tp_instruction"] = ("That day or time is not possible. Say the callback can only be " + days + " between " + ws + " and " + we +
                                          ". Ask once more when the customer can be reached. Do not say why you are calling.")
    vars["route"] = route


# ---- products -----------------------------------------------------------------------------------------------------------

def _roles(CFG): return CFG.get("roles") or dict()

def _pname(p, CFG):
    wording = _s(CFG, "debt_statement.product_wording") or dict()
    try:
        return _product_name_from(p, wording, _roles(CFG))
    except Exception:
        return str(p.get(_roles(CFG).get("type", "type"), "product")).replace("_", " ")

def _product_name_from(p, wording, roles):
    t = str(p.get(roles.get("type", "type"), ""))
    tpl = wording.get(t)
    if not tpl: return t.replace("_", " ") or "product"
    out = str(tpl)
    for key, val in p.items():
        out = out.replace("{" + str(key) + "}", str(val))
    return re.sub(r"\{[A-Za-z_][\w]*\}", "", out).strip()


def _node_product_facts(vars, CFG):
    now = _today(vars, CFG); today = now.date(); cal = _cal(CFG); roles = _roles(CFG)
    products = _products_from_vars(vars)
    bands = list(_s(CFG, "bands") or [])
    floor_cfg = dict()
    floor_cfg["floor_kind"] = _s(CFG, "amount_rules.floor_kind", "by_product_type")
    floor_cfg["floor_by_type"] = _s(CFG, "amount_rules.floor_by_type") or dict()
    floor_cfg["floor_fraction"] = _s(CFG, "amount_rules.floor_fraction", 0)
    floor_cfg["floor_fixed"] = _s(CFG, "amount_rules.floor_fixed", 0)
    vars["today_iso"] = today.isoformat(); vars["today_text"] = (_speak_date(today.isoformat()) or today.isoformat()) + " " + str(today.year)
    n = len(products); vars["n_products"] = n
    if n == 0:
        vars["acct_state"] = "error"; vars["route"] = "error"
        _outcome(vars, _s(CFG, "confirmation.failure_outcome"))
        vars["farewell_instruction"] = "Say that the account details are not available right now and the bank will call again. Thank them and say goodbye."
        return
    vars["acct_state"] = "ok"
    sentences = []
    for i, p in enumerate(products):
        k = i + 1
        pid = str(p.get(roles.get("id", "product_id"), "p" + str(k)))
        full = float(p.get(roles.get("past_due", "past_due"), 0) or 0)
        late = int(float(p.get(roles.get("days_late", "days_late"), 0) or 0))
        band = _band_for(late, bands, cal) or dict()
        deadline = _deadline_for(today, band, cal) if band else None
        floor = _product_floor(p, floor_cfg)
        if floor is None or floor <= 0 or floor > full: floor = full
        name = _pname(p, CFG)
        _pset(vars, k, "id", pid); _pset(vars, k, "name", name); _pset(vars, k, "full", full); _pset(vars, k, "floor", floor)
        _pset(vars, k, "days_late", late); _pset(vars, k, "band", str(band.get("name", ""))); _pset(vars, k, "deadline", deadline or "")
        _pset(vars, k, "attempts_max", int(band.get("persuasion_attempts", 1) or 0)); _pset(vars, k, "attempts_used", 0)
        _pset(vars, k, "ask_amount", full); _pset(vars, k, "state", "open"); _pset(vars, k, "agreed_date", ""); _pset(vars, k, "agreed_amount", "")
        _pset(vars, k, "floor_offered", 0); _pset(vars, k, "vague_asked", 0); _pset(vars, k, "deadline_offered", 0)
        _pset(vars, k, "offer_date", ""); _pset(vars, k, "offer_amount", ""); _pset(vars, k, "refused_offers", "[]"); _pset(vars, k, "capped", 0)
        _pset(vars, k, "recorded", 0); _pset(vars, k, "turns", 0)
        sentences.append("the " + name + ": " + _money(full, CFG) + " past due, " + str(late) + " days late")
    vars["cur_k"] = 1; vars["promise_count"] = 0; vars["transfer_flag"] = 0; vars["transfer_queue"] = ""
    vars["stance"] = "none"; vars["prop_date_text"] = ""; vars["prop_amount_text"] = ""; vars["prop_product_text"] = ""
    intro = str(_s(CFG, "debt_statement.intro", "This call is about a late payment.") or "")
    first_ask = str(_s(CFG, "persuasion.first_ask", "Can you make this payment today?") or "")
    vars["multi_mode"] = 1 if (n > 1 and _s(CFG, "multi_product.ask_all_today_first", True)) else 0
    if vars["multi_mode"]:
        vars["neg_phase"] = "all"
        vars["neg_instruction"] = ("Say: " + intro + " State every late product, one sentence each: " + "; ".join(sentences) +
                                   ". Then ask whether the customer can pay all of them today.")
    else:
        vars["neg_phase"] = "product"
        vars["neg_instruction"] = ("Say: " + intro + " State: " + sentences[0] + ". Then ask exactly: " + first_ask)
    vars["route"] = "negotiate"


# ---- negotiation ----------------------------------------------------------------------------------------------------------

def _attempt_offers(vars, k, CFG):
    band = str(_pget(vars, k, "band", ""))
    out = []
    for a in list(_s(CFG, "persuasion.attempts") or []):
        bands = a.get("bands") or []
        if bands and band not in bands: continue
        out.append(a)
    return out

def _offer_amount(vars, k, kind):
    if kind == "full": return _gf(vars, _pk(k, "full"))
    if kind == "floor": return _gf(vars, _pk(k, "floor"))
    return _gf(vars, _pk(k, "ask_amount"), _gf(vars, _pk(k, "full")))

def _speak_offer(vars, k, date_iso, amount, CFG):
    return _money(amount, CFG) + " for the " + str(_pget(vars, k, "name", "product")) + " on " + str(_speak_date(date_iso) or date_iso)

def _make_attempt(vars, k, CFG, now):
    """Use one persuasion attempt. Returns an instruction, or '' when attempts are exhausted."""
    cal = _cal(CFG); today = now.date()
    used = _gi(vars, _pk(k, "attempts_used"), 0) + 1; _pset(vars, k, "attempts_used", used)
    offers = _attempt_offers(vars, k, CFG); amax = _gi(vars, _pk(k, "attempts_max"), 0)
    try: refused = json.loads(str(_pget(vars, k, "refused_offers", "[]")))
    except Exception: refused = []
    last_d = str(_pget(vars, k, "offer_date", "")); last_a = _pget(vars, k, "offer_amount", "")
    if last_d or last_a != "": refused.append([last_d, str(last_a)])
    _pset(vars, k, "refused_offers", json.dumps(refused))
    deadline = str(_pget(vars, k, "deadline", ""))
    i = used - 1
    while i < len(offers) and used <= amax:
        a = offers[i]
        d = _resolve_offer_date(str(a.get("date_kind", "")), today, deadline, cal)
        if not d and a.get("date_text"): d = deadline
        amt = _offer_amount(vars, k, str(a.get("amount", "current_ask")))
        if d and [d, str(amt)] not in refused:
            _pset(vars, k, "offer_date", d); _pset(vars, k, "offer_amount", amt)
            if str(a.get("amount")) == "floor": _pset(vars, k, "floor_offered", 1)
            extra = ""
            if str(a.get("amount")) == "floor" and _s(CFG, "amount_rules.too_much_say"): extra = " Add: " + str(_s(CFG, "amount_rules.too_much_say"))
            return "Propose exactly this and nothing else: " + _speak_offer(vars, k, d, amt, CFG) + ". Ask whether that works." + extra
        i += 1; used += 1; _pset(vars, k, "attempts_used", used)
    return ""

def _advance(vars, CFG, now):
    """Current product is settled. Move to the next open product, or to confirmation / closing."""
    n = _n_products(vars)
    for k in range(1, n + 1):
        if str(_pget(vars, k, "state", "open")) == "open":
            vars["cur_k"] = k
            _pset(vars, k, "turns", 0)
            if _gi(vars, "multi_mode", 0):
                # after the all-products question: each product starts at attempt 1 (no 'today' question again)
                instr = _make_attempt(vars, k, CFG, now)
                if instr:
                    vars["neg_instruction"] = "Now the " + str(_pget(vars, k, "name")) + " (" + _money(_gf(vars, _pk(k, "full")), CFG) + " past due). " + instr
                    return "negotiate"
                _pset(vars, k, "state", "refused")
                continue
            first_ask = str(_s(CFG, "persuasion.first_ask", "Can you make this payment today?") or "")
            vars["neg_instruction"] = ("Now the " + str(_pget(vars, k, "name")) + ": " + _money(_gf(vars, _pk(k, "full")), CFG) + " past due, " +
                                       str(_pget(vars, k, "days_late")) + " days late. Ask exactly: " + first_ask)
            return "negotiate"
    agreed = [k for k in range(1, n + 1) if str(_pget(vars, k, "state")) == "agreed"]
    if agreed:
        _build_readback(vars, CFG); return "confirm"
    return "close"

def _build_readback(vars, CFG):
    n = _n_products(vars); parts = []
    for k in range(1, n + 1):
        if str(_pget(vars, k, "state")) != "agreed": continue
        d = str(_pget(vars, k, "agreed_date")); a = _gf(vars, _pk(k, "agreed_amount"))
        s = _money(a, CFG) + " for the " + str(_pget(vars, k, "name")) + " on " + str(_speak_date(d) or d)
        if _gi(vars, _pk(k, "capped"), 0): s += " (its latest possible date)"
        parts.append(s)
    q = str(_s(CFG, "confirmation.question", "Do you confirm?") or "Do you confirm?")
    vars["readback_text"] = "; ".join(parts)
    vars["confirm_instruction"] = "Read back exactly: " + "; ".join(parts) + ". Then ask exactly: " + q
    vars["confirm_stance"] = "none"

def _validate_date(vars, k, d_status, d_val, CFG, now):
    """Returns (ok_iso, instruction). ok_iso set when the date is acceptable as is."""
    cal = _cal(CFG); today = now.date(); deadline = str(_pget(vars, k, "deadline", "")); dl = _to_date(deadline)
    rules = _s(CFG, "date_rules") or dict()
    if d_status == "vague":
        if rules.get("vague_ask_exact_once", True) and not _gi(vars, _pk(k, "vague_asked"), 0):
            _pset(vars, k, "vague_asked", 1)
            return "", "Ask for the exact day they will pay. Propose nothing yet."
        then = str(rules.get("vague_then") or "propose_deadline")
        d = deadline if then == "propose_deadline" else _next_business_day(today, cal).isoformat()
        if d:
            amt = _gf(vars, _pk(k, "ask_amount")); _pset(vars, k, "offer_date", d); _pset(vars, k, "offer_amount", amt)
            return "", "Propose exactly: " + _speak_offer(vars, k, d, amt, CFG) + ". Ask whether that works."
        return "", "Ask for the exact day they will pay."
    if d_status != "date": return "", "Ask for the exact day they will pay."
    d = _to_date(d_val)
    if d is None: return "", "Ask for the exact day they will pay."
    earliest = today
    if str(rules.get("earliest")) == "tomorrow": earliest = today + datetime.timedelta(days=1)
    if str(rules.get("earliest")) == "next_business_day": earliest = _next_business_day(today, cal)
    if d < earliest:
        return "", "That date has passed. Ask for a day from " + str(_speak_date(earliest.isoformat())) + " on."
    if dl is not None and d > dl:
        if str(rules.get("after_deadline") or "offer_deadline") == "offer_deadline":
            _pset(vars, k, "deadline_offered", 1); amt = _gf(vars, _pk(k, "ask_amount"))
            _pset(vars, k, "offer_date", deadline); _pset(vars, k, "offer_amount", amt)
            return "", ("Say the latest date you can record is " + str(_speak_date(deadline)) + ". Offer exactly: " +
                        _speak_offer(vars, k, deadline, amt, CFG) + ". Ask whether that works.")
        return "", "Say that date is after the latest possible date, " + str(_speak_date(deadline)) + ". Ask for an earlier day."
    if rules.get("must_be_business_day", True) and not _is_business_day(d, cal):
        act = str(rules.get("non_business_day") or "offer_next_business_day")
        nb = _next_business_day(d, cal)
        if act == "offer_previous_business_day":
            nb = d
            while not _is_business_day(nb, cal): nb = nb - datetime.timedelta(days=1)
        if act in ("offer_next_business_day", "offer_previous_business_day") and nb is not None:
            if dl is not None and nb > dl:
                nb = dl; _pset(vars, k, "deadline_offered", 1)
            amt = _gf(vars, _pk(k, "ask_amount")); _pset(vars, k, "offer_date", nb.isoformat()); _pset(vars, k, "offer_amount", amt)
            why = "a bank holiday" if d.weekday() in (cal.get("business_weekdays") or [0, 1, 2, 3, 4]) else "a weekend day"
            return "", ("Say " + str(_speak_date(d.isoformat())) + " is " + why + " and offer exactly: " +
                        _speak_offer(vars, k, nb.isoformat(), amt, CFG) + ". Ask whether that works.")
        return "", "Say that day is not a business day and ask for another day."
    return d.isoformat(), ""

def _validate_amount(vars, k, amt, CFG):
    """Returns (ok_amount, instruction)."""
    full = _gf(vars, _pk(k, "full")); floor = _gf(vars, _pk(k, "floor"), full)
    rules = _s(CFG, "amount_rules") or dict()
    if amt is None: return _gf(vars, _pk(k, "ask_amount"), full), ""
    if amt >= full - 0.005: return full, ""
    if amt >= floor - 0.005:
        if str(rules.get("between_floor_and_full") or "accept") == "accept": return amt, ""
        return None, "Say you can only record the full amount of " + _money(full, CFG) + ". Ask whether they can pay that."
    if rules.get("below_floor_offer_floor_once", True) and not _gi(vars, _pk(k, "floor_offered"), 0):
        _pset(vars, k, "floor_offered", 1); _pset(vars, k, "ask_amount", floor); _pset(vars, k, "offer_amount", floor)
        say = str(rules.get("below_floor_say") or "That amount cannot be recorded.")
        return None, "Say: " + say + " Offer exactly the minimum of " + _money(floor, CFG) + " instead. Ask whether they can pay that."
    return None, "FLAT_REFUSAL"

def _settle(vars, k, date_iso, amount, CFG):
    _pset(vars, k, "agreed_date", date_iso); _pset(vars, k, "agreed_amount", amount); _pset(vars, k, "state", "agreed")

def _node_eval(vars, CFG):
    now = _today(vars, CFG); today = now.date(); cal = _cal(CFG)
    k = _gi(vars, "cur_k", 1); n = _n_products(vars)
    stance = str(_g(vars, "stance", "none")); dtext = str(_g(vars, "prop_date_text", "")); atext = str(_g(vars, "prop_amount_text", ""))
    ptext = str(_g(vars, "prop_product_text", ""))
    vars["stance"] = "none"; vars["prop_date_text"] = ""; vars["prop_amount_text"] = ""; vars["prop_product_text"] = ""
    _pset(vars, k, "turns", _gi(vars, _pk(k, "turns"), 0) + 1)
    d_status, d_val = _resolve_date_expr(dtext, now, cal) if dtext else ("none", "")
    amt = _parse_amount(atext) if atext else None
    phase = str(_g(vars, "neg_phase", "product"))
    route = "negotiate"
    if stance in ("refuses", "other", "none", "vague", "agrees") and (d_status != "none" or amt is not None):
        if stance != "agrees" or d_status == "date" or amt is not None: stance = "proposes"
    if stance == "question":
        vars["neg_instruction"] = "Answer the customer's question in one sentence using the standard replies (say you do not have information you were not given). Then repeat your last question or proposal."
        vars["route"] = route; return
    if stance == "human":
        vars["resume_to"] = "negotiate"; vars["neg_instruction_saved"] = str(_g(vars, "neg_instruction", "")); vars["route"] = "human"; return
    if stance == "plan":
        _transfer(vars, CFG, str(_s(CFG, "situations.plan_request.queue", "") or ""), _s(CFG, "situations.plan_request.outcome"))
        vars["route"] = "transfer"; return
    if stance == "hardship":
        vars["hs_instruction"] = ("Say exactly: " + str(_s(CFG, "hardship.sympathy", "I am sorry to hear that.")) + " Then offer: " +
                                  str(_s(CFG, "hardship.offer", "to connect them with the customer support team")) + ". Make no payment proposal.")
        vars["hs_stance"] = "none"; vars["route"] = "hardship"; return
    if stance == "dont_want_to_talk":
        d = _gi(vars, "dnt_count", 0) + 1; vars["dnt_count"] = d
        if d >= int(_s(CFG, "situations.dont_want_to_talk.times", 2) or 2):
            for j in range(1, n + 1):
                if str(_pget(vars, j, "state")) == "open": _pset(vars, j, "state", "refused")
            vars["force_outcome"] = json.dumps(_s(CFG, "situations.dont_want_to_talk.after_verified") or dict())
            vars["route"] = "close"; return
        vars["neg_instruction"] = "Say you understand it is not a good moment and will be brief. Then repeat your last question or proposal."
        vars["route"] = route; return
    if stance == "paid":
        if phase == "all" and n > 1:
            for j in range(1, n + 1):
                if str(_pget(vars, j, "state")) == "open": _pset(vars, j, "state", "paid")
        else: _pset(vars, k, "state", "paid")
        vars["paid_note"] = str(_s(CFG, "situations.already_paid.say", "Payments can take one business day to appear."))
        if not _s(CFG, "multi_product.dispute_or_paid_does_not_end_call", True) and n > 1:
            for j in range(1, n + 1):
                if str(_pget(vars, j, "state")) == "open": _pset(vars, j, "state", "paid")
        vars["route"] = _advance_with_note(vars, CFG, now, "Say exactly: " + vars["paid_note"] + " "); return
    if stance == "dispute":
        if phase == "all" and n > 1:
            for j in range(1, n + 1):
                if str(_pget(vars, j, "state")) == "open": _pset(vars, j, "state", "dispute")
        else: _pset(vars, k, "state", "dispute")
        if not _s(CFG, "multi_product.dispute_or_paid_does_not_end_call", True) and n > 1:
            for j in range(1, n + 1):
                if str(_pget(vars, j, "state")) == "open": _pset(vars, j, "state", "dispute")
        vars["route"] = _advance_with_note(vars, CFG, now, "Say you have noted that they dispute it and will not argue. "); return
    if phase == "all" and n > 1:
        if stance == "agrees":
            for j in range(1, n + 1):
                if str(_pget(vars, j, "state")) == "open": _settle(vars, j, today.isoformat(), _gf(vars, _pk(j, "full")), CFG)
            vars["route"] = _advance(vars, CFG, now); return
        if stance == "proposes":
            target = _match_product(vars, ptext, n)
            if target:
                vars["neg_phase"] = "product"; vars["cur_k"] = target; k = target
                stance = "proposes"   # fall through to the single-product handling below
            else:
                ok_any = False
                for j in range(1, n + 1):
                    if str(_pget(vars, j, "state")) != "open": continue
                    d_ok, instr = _validate_date(vars, j, d_status, d_val, CFG, now)
                    a_ok, a_instr = _validate_amount(vars, j, amt if n == 1 else None, CFG)
                    if d_ok and a_ok is not None:
                        _settle(vars, j, d_ok, a_ok, CFG); ok_any = True
                    elif d_status == "date" and _to_date(d_val) is not None and _to_date(str(_pget(vars, j, "deadline"))) is not None and _to_date(d_val) > _to_date(str(_pget(vars, j, "deadline"))) and str(_s(CFG, "multi_product.one_date_past_a_deadline", "that_product_on_its_own_deadline")) == "that_product_on_its_own_deadline":
                        _settle(vars, j, str(_pget(vars, j, "deadline")), _gf(vars, _pk(j, "full")), CFG); _pset(vars, j, "capped", 1); ok_any = True
                    else:
                        vars["cur_k"] = j; vars["neg_phase"] = "product"; vars["neg_instruction"] = instr; vars["route"] = "negotiate"; return
                if ok_any: vars["route"] = _advance(vars, CFG, now); return
        if stance in ("refuses", "too_much", "other", "none"):
            vars["neg_phase"] = "product"
            if stance == "too_much":
                for j in range(1, n + 1): _pset(vars, j, "ask_amount", _gf(vars, _pk(j, "floor")))
            vars["route"] = _advance(vars, CFG, now); return
    # ---- single product k ----
    if stance == "agrees":
        d = str(_pget(vars, k, "offer_date", "")) or today.isoformat()
        a = _pget(vars, k, "offer_amount", "")
        a = float(a) if a != "" else _gf(vars, _pk(k, "ask_amount"), _gf(vars, _pk(k, "full")))
        if not _is_business_day(_to_date(d), cal) and _s(CFG, "date_rules.must_be_business_day", True):
            d = _next_business_day(_to_date(d), cal).isoformat()
        _settle(vars, k, d, a, CFG); vars["route"] = _advance(vars, CFG, now); return
    if stance == "proposes":
        a_ok, a_instr = _validate_amount(vars, k, amt, CFG)
        if a_instr == "FLAT_REFUSAL": stance = "refuses"
        else:
            if a_ok is None:
                pd = _to_date(d_val) if d_status == "date" else None
                dl = _to_date(str(_pget(vars, k, "deadline", "")))
                if pd is not None and pd >= today and _is_business_day(pd, cal) and (dl is None or pd <= dl):
                    _pset(vars, k, "offer_date", pd.isoformat())
                    vars["neg_instruction"] = a_instr + " (for " + str(_speak_date(pd.isoformat())) + ")"
                else:
                    vars["neg_instruction"] = a_instr
                vars["route"] = route; return
            if d_status == "none":
                if amt is not None:
                    _pset(vars, k, "ask_amount", a_ok); _pset(vars, k, "offer_amount", a_ok)
                    od = str(_pget(vars, k, "offer_date", "")) or today.isoformat(); _pset(vars, k, "offer_date", od)
                    vars["neg_instruction"] = "Accept " + _money(a_ok, CFG) + ". Ask exactly whether they can pay " + _money(a_ok, CFG) + " on " + str(_speak_date(od)) + "."
                else:
                    vars["neg_instruction"] = "Ask for the exact day they will pay."
                vars["route"] = route; return
            d_ok, d_instr = _validate_date(vars, k, d_status, d_val, CFG, now)
            if d_ok:
                _settle(vars, k, d_ok, a_ok, CFG); vars["route"] = _advance(vars, CFG, now); return
            if amt is not None: _pset(vars, k, "ask_amount", a_ok)
            vars["neg_instruction"] = d_instr; vars["route"] = route; return
    if stance == "too_much":
        full = _gf(vars, _pk(k, "full")); floor = _gf(vars, _pk(k, "floor"), full)
        if _s(CFG, "amount_rules.too_much_offer_floor_once", True) and not _gi(vars, _pk(k, "floor_offered"), 0) and floor < full:
            _pset(vars, k, "floor_offered", 1); _pset(vars, k, "ask_amount", floor)
            od = str(_pget(vars, k, "offer_date", "")) or today.isoformat()
            _pset(vars, k, "offer_date", od); _pset(vars, k, "offer_amount", floor)
            say = str(_s(CFG, "amount_rules.too_much_say", "The rest stays overdue.") or "")
            vars["neg_instruction"] = ("Offer exactly the minimum of " + _money(floor, CFG) + " for the " + str(_pget(vars, k, "name")) +
                                       " on " + str(_speak_date(od)) + ". Say: " + say + " Ask whether they can pay that.")
            vars["route"] = route; return
        stance = "refuses"
    # flat refusal or non-answer: use an attempt
    instr = _make_attempt(vars, k, CFG, now)
    if instr:
        vars["neg_instruction"] = instr; vars["route"] = route; return
    _pset(vars, k, "state", "refused")
    vars["route"] = _advance_with_note(vars, CFG, now, "Say you understand and will not insist. ")

def _advance_with_note(vars, CFG, now, prefix):
    r = _advance(vars, CFG, now)
    if r == "negotiate": vars["neg_instruction"] = prefix + str(_g(vars, "neg_instruction", ""))
    else: vars["close_prefix"] = prefix
    return r

def _match_product(vars, text, n):
    t = str(text or "").lower()
    if not t: return 0
    for k in range(1, n + 1):
        name = str(_pget(vars, k, "name", "")).lower()
        words = [w for w in re.split(r"[^a-z0-9]+", name) if len(w) > 3]
        if name and (name in t or any(w in t for w in words)): return k
    return 0

def _transfer(vars, CFG, queue, outcome_obj):
    vars["transfer_queue"] = str(queue or ""); vars["transfer_flag"] = 1
    _outcome(vars, outcome_obj)
    vars["transfer_instruction"] = "Say you will connect them to the " + (str(queue or "right") + " team") + " now. Thank them and say goodbye."


def _node_eval_hardship(vars, CFG):
    now = _today(vars, CFG); n = _n_products(vars)
    st = str(_g(vars, "hs_stance", "none")); vars["hs_stance"] = "none"
    dtext = str(_g(vars, "prop_date_text", "")); atext = str(_g(vars, "prop_amount_text", ""))
    if st == "accepts":
        _transfer(vars, CFG, str(_s(CFG, "hardship.accept_queue", "") or ""), _s(CFG, "hardship.accept_outcome")); vars["route"] = "transfer"; return
    if st == "proposes" and (dtext or atext) and _s(CFG, "hardship.record_if_customer_names_date_or_amount", True):
        vars["stance"] = "proposes"; vars["route"] = "eval"; return
    if st == "declines" or st == "other" or st == "none":
        for j in range(1, n + 1):
            if str(_pget(vars, j, "state")) == "open": _pset(vars, j, "state", "hardship")
        vars["close_prefix"] = "Say you understand. "
        vars["route"] = _advance(vars, CFG, now); return
    vars["route"] = "again"


def _node_eval_human(vars, CFG):
    st = str(_g(vars, "hum_stance", "other")); vars["hum_stance"] = "other"
    if st == "insists":
        _transfer(vars, CFG, str(_s(CFG, "situations.human_request.queue", "") or ""), _s(CFG, "situations.human_request.outcome")); vars["route"] = "transfer"; return
    back = str(_g(vars, "resume_to", "negotiate"))
    if back == "negotiate": vars["neg_instruction"] = "Continue: " + str(_g(vars, "neg_instruction_saved", "") or _g(vars, "neg_instruction", ""))
    elif back == "identity": vars["id_instruction"] = "Continue the security check: ask again for the pending security answer."
    else: vars["op_instruction"] = "Ask again, exactly: " + _fill(_s(CFG, "opening.ask_for_customer", ""), vars)
    vars["route"] = back


# ---- confirmation and recording -------------------------------------------------------------------------------------------

def _node_eval_confirm(vars, CFG):
    now = _today(vars, CFG); n = _n_products(vars)
    st = str(_g(vars, "confirm_stance", "none")); vars["confirm_stance"] = "none"
    dtext = str(_g(vars, "prop_date_text", "")); atext = str(_g(vars, "prop_amount_text", "")); ptext = str(_g(vars, "prop_product_text", ""))
    vars["prop_date_text"] = ""; vars["prop_amount_text"] = ""; vars["prop_product_text"] = ""
    if st == "yes":
        vars["route"] = _next_record(vars, CFG); return
    if st == "change" or (st in ("other", "none", "question") and (dtext or atext)):
        agreed = [k for k in range(1, n + 1) if str(_pget(vars, k, "state")) == "agreed"]
        k = _match_product(vars, ptext, n) or (agreed[0] if len(agreed) == 1 else 0)
        if not k:
            vars["confirm_instruction"] = "Ask which product the change is for. Then read back again."; vars["route"] = "confirm"; return
        _pset(vars, k, "state", "open"); vars["cur_k"] = k; vars["neg_phase"] = "product"
        vars["stance"] = "proposes"; vars["prop_date_text"] = dtext; vars["prop_amount_text"] = atext
        vars["route"] = "eval"; return
    if st == "no":
        for k in range(1, n + 1):
            if str(_pget(vars, k, "state")) == "agreed": _pset(vars, k, "state", "open")
        vars["cur_k"] = [k for k in range(1, n + 1) if str(_pget(vars, k, "state")) == "open"][0] if n else 1
        vars["neg_phase"] = "product"; vars["stance"] = "refuses"; vars["route"] = "eval"; return
    vars["confirm_instruction"] = "Answer briefly if they asked something. Then read back again exactly: " + str(_g(vars, "readback_text", "")) + ". Ask exactly: " + str(_s(CFG, "confirmation.question", "Do you confirm?"))
    vars["route"] = "confirm"

def _next_record(vars, CFG):
    n = _n_products(vars)
    for k in range(1, n + 1):
        if str(_pget(vars, k, "state")) == "agreed" and not _gi(vars, _pk(k, "recorded"), 0) and str(_pget(vars, k, "rec_tried", "")) != "1":
            _pset(vars, k, "rec_tried", "1")
            vars["rec_k"] = k; vars["rec_pid"] = str(_pget(vars, k, "id")); vars["rec_amount"] = _gf(vars, _pk(k, "agreed_amount")); vars["rec_date"] = str(_pget(vars, k, "agreed_date"))
            vars["rec_ok"] = ""; vars["rec_ok_retry"] = ""
            return "record"
    return "close"

def _node_after_record(vars, CFG):
    k = _gi(vars, "rec_k", 1)
    ok = str(_g(vars, "rec_ok", "")).lower() == "true" or str(_g(vars, "rec_ok_retry", "")).lower() == "true"
    if ok:
        _pset(vars, k, "recorded", 1); vars["promise_count"] = _gi(vars, "promise_count", 0) + 1
    else:
        _pset(vars, k, "state", "service_error")
    vars["route"] = _next_record(vars, CFG)


# ---- closing ----------------------------------------------------------------------------------------------------------------

def _node_notes_plan(vars, CFG):
    n = _n_products(vars)
    transfer = _gi(vars, "transfer_flag", 0) == 1
    notes_on = bool(_s(CFG, "multi_product.notes_enabled", False)) and CFG.get("has_add_note", False)
    if transfer and _s(CFG, "multi_product.notes_none_on_transfer", True): notes_on = False
    recorded = []; states = []
    for k in range(1, n + 1):
        st = str(_pget(vars, k, "state", "open"))
        if _gi(vars, _pk(k, "recorded"), 0): recorded.append(k)
        elif st in ("open", "agreed"): st = "refused"
        states.append((k, st))
    notes = []
    if notes_on:
        for k, st in states:
            if k in recorded: continue
            r = _note_reason(CFG, st)
            if r: notes.append((k, r))
    vars["note_1_pid"] = ""; vars["note_1_reason"] = ""; vars["note_2_pid"] = ""; vars["note_2_reason"] = ""; vars["note_3_pid"] = ""; vars["note_3_reason"] = ""
    if len(notes) > 0: vars["note_1_pid"] = str(_pget(vars, notes[0][0], "id")); vars["note_1_reason"] = notes[0][1]
    if len(notes) > 1: vars["note_2_pid"] = str(_pget(vars, notes[1][0], "id")); vars["note_2_reason"] = notes[1][1]
    if len(notes) > 2: vars["note_3_pid"] = str(_pget(vars, notes[2][0], "id")); vars["note_3_reason"] = notes[2][1]
    # outcome
    forced = str(_g(vars, "force_outcome", ""))
    if transfer:
        pass  # outcome already set by _transfer
    elif forced:
        try: _outcome(vars, json.loads(forced))
        except Exception: _outcome(vars, dict())
    elif str(_g(vars, "outcome", "")) and str(_g(vars, "acct_state", "ok")) != "ok":
        pass  # account error outcome already set
    elif recorded:
        vars["outcome"] = str(_s(CFG, "closing.any_promise_outcome", "promise") or "promise"); vars["reason"] = ""
    elif n and all(st == "paid" for k, st in states):
        _outcome(vars, _situation_outcome(CFG, "paid"), str(_s(CFG, "closing.all_paid_outcome", "paid") or "paid"))
    else:
        first = ""
        for k, st in states:
            if st != "paid": first = st; break
        if not first: first = states[0][1] if states else "refused"
        _outcome(vars, _situation_outcome(CFG, first), "", "")
    # farewell
    parts = [str(_g(vars, "close_prefix", ""))]
    if recorded:
        items = []
        for k in recorded:
            items.append(_money(_gf(vars, _pk(k, "agreed_amount")), CFG) + " for the " + str(_pget(vars, k, "name")) + " on " + str(_speak_date(str(_pget(vars, k, "agreed_date")))))
        parts.append("Say the promise is recorded: " + "; ".join(items) + ".")
        for s in list(_s(CFG, "confirmation.after_recorded_sentences") or []): parts.append("Then say exactly: " + str(s))
        for ms in list(_s(CFG, "mandatory_sentences") or []):
            if str(ms.get("when")) == "after_promise_recorded" and str(ms.get("text")) not in (_s(CFG, "confirmation.after_recorded_sentences") or []): parts.append("Then say exactly: " + str(ms.get("text")))
    failed = [k for k, st in states if st == "service_error"]
    if failed:
        parts.append("Say exactly: " + str(_s(CFG, "confirmation.failure_say", "I could not record the promise.")) + " (for the " + ", ".join(str(_pget(vars, k, "name")) for k in failed) + ").")
    if any(st == "paid" for k, st in states) and not recorded:
        parts.append("Say exactly: " + str(_s(CFG, "situations.already_paid.say", "Payments can take one business day to appear.")))
    if not recorded and not failed and not transfer and not forced and states and all(st in ("refused", "hardship", "dispute") for k, st in states):
        parts.append("Do not repeat any offer.")
    vars["farewell_instruction"] = " ".join(p for p in parts if p).strip() or "Thank the customer."
    vars["route"] = "note_1" if notes else "farewell"


def _node_set(vars, CFG):
    """Generic terminal setter: CFG['set'] holds outcome and farewell instruction."""
    s = CFG.get("set") or dict()
    if s.get("outcome"): _outcome(vars, s.get("outcome"))
    if s.get("farewell_instruction"): vars["farewell_instruction"] = _fill(s.get("farewell_instruction"), vars)
    vars["route"] = str(s.get("route") or "farewell")


# ---- dispatcher ---------------------------------------------------------------------------------------------------------------

def _run_node(mode, vars, CFG):
    fn = dict()
    fn["opening_tally"] = _node_opening_tally; fn["identity_prep"] = _node_identity_prep; fn["identity_tally"] = _node_identity_tally
    fn["tp_eval"] = _node_tp_eval; fn["product_facts"] = _node_product_facts; fn["eval"] = _node_eval
    fn["eval_hardship"] = _node_eval_hardship; fn["eval_human"] = _node_eval_human; fn["eval_confirm"] = _node_eval_confirm
    fn["after_record"] = _node_after_record; fn["notes_plan"] = _node_notes_plan; fn["set"] = _node_set
    f = fn.get(mode)
    if f is None:
        vars["route"] = "farewell"; return
    f(vars, CFG)
