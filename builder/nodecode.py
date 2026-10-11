"""Logic of the generated code nodes. This source is shipped into every code node of the workflow after the date
library (datefacts.LIB_SOURCE). It runs in Freya's sandbox: only json, re and datetime; it reads and writes the call's
variable table through `vars`; it must never raise; and it must not contain a double opening or closing brace sequence
(the platform treats those as placeholders), so nested literals are built step by step.

Every sentence the phone agent says is composed here and spoken by the next conversation node (`vars['say']`).
The dialogue model is never relied on; the extraction model classifies what the customer said.
The same functions run offline in builder/tests against the same library, so what we test is what runs.
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
    try:
        def rep(m): return str(vars.get(m.group(1), "") or "")
        return re.sub(r"\[\[\s*([A-Za-z_][\w]*)\s*\]\]", rep, str(text or ""))
    except Exception: return str(text or "")

def _cal(CFG): return CFG.get("calendar") or dict()

def _today(vars, CFG):
    now = _parse_now(str(_g(vars, CFG.get("now_var", "now"), "")))
    if now is None: now = datetime.datetime.now()
    return now

def _spec(CFG): return CFG.get("spec") or dict()

def _s(CFG, path, default=None):
    cur = _spec(CFG)
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur: return default
        cur = cur[part]
    return default if cur is None or cur == "" else cur

def _outcome(vars, obj, fallback_outcome="", fallback_reason=""):
    obj = obj if isinstance(obj, dict) else dict()
    vars["outcome"] = str(obj.get("outcome") or fallback_outcome or "")
    vars["reason"] = str(obj.get("reason") or fallback_reason or "")

def _money(x, CFG): return _speak_money(x, _cal(CFG))

def _pk(k, name): return "p" + str(int(k)) + "_" + name
def _pget(vars, k, name, default=""): return _g(vars, _pk(k, name), default)
def _pset(vars, k, name, value): vars[_pk(k, name)] = value
def _n_products(vars): return _gi(vars, "n_products", 0)

def _sentence(s):
    s = " ".join(str(s or "").split())
    if s and s[-1] not in ".?!": s += "."
    return s

def _say(vars, text, ask=None):
    """Set what the next node says. `ask` (default: the last question composed by _ask_pay, else the text) is what
    gets repeated after a side question or a non-answer, so an offer's explanation is never said twice."""
    text = " ".join(str(text or "").split())
    vars["say"] = text
    if ask is None and str(_g(vars, "last_question", "")) and str(_g(vars, "last_question", "")) in text: ask = str(_g(vars, "last_question", ""))
    vars["last_question"] = ""
    vars["last_ask"] = " ".join(str(ask if ask is not None else text).split())

_CORRECTION = re.compile(r"\b(sorry|i mean|i meant|actually|no wait|wait no|wait,|no,|correction|scratch that|make that|rather|not that|let me correct|i mean to say)\b[:,]?", re.I)

def _corrected(text):
    """'the 21st, sorry, I mean the 20th' -> 'the 20th': customers correct themselves; the last part is what they mean."""
    t = str(text or "")
    parts = _CORRECTION.split(t)
    # split keeps the markers as separate items; take the last non-marker, non-empty part
    out = t
    for part in reversed(parts):
        if part and not _CORRECTION.fullmatch(part.strip()) and part.strip(" ,:"):
            out = part; break
    return out.strip(" ,:.")

def _cut(vars):
    """True when the extraction says the customer's last message was cut off mid-sentence (the platform does this)."""
    c = str(_g(vars, "clarity", "complete")); vars["clarity"] = "complete"
    return c == "cut_off"

def _std_reply(vars, CFG, kind):
    kind = str(kind or "none")
    if kind == "robot": return _sentence(_s(CFG, "opening.robot_reply", "I am a digital assistant."))
    if kind == "scam": return _sentence(_s(CFG, "situations.scam_question.say", "You can verify this call by phoning the bank's customer service number."))
    if kind == "what_about":
        if _gi(vars, "verified", 0): return _sentence(_s(CFG, "debt_statement.intro", "This call is about a late payment."))
        return "I can explain the reason for my call after a short security check."
    if kind == "other": return _sentence(_s(CFG, "situations.unknown_question.say", "I do not have that information."))
    return ""

def _situation_outcome(CFG, situation):
    m = dict()
    m["refused"] = _s(CFG, "persuasion.exhausted"); m["hardship"] = _s(CFG, "hardship.decline_outcome")
    m["dispute"] = _s(CFG, "situations.dispute.outcome"); m["paid"] = _s(CFG, "situations.already_paid.outcome")
    m["service_error"] = _s(CFG, "confirmation.failure_outcome")
    return m.get(situation) or dict()

def _note_reason(CFG, situation):
    rm = _s(CFG, "multi_product.notes_reason_map") or dict()
    if situation in rm and rm[situation]: return str(rm[situation])
    direct = dict()
    direct["hardship"] = _s(CFG, "hardship.decline_note_reason"); direct["dispute"] = _s(CFG, "situations.dispute.note_reason")
    direct["paid"] = _s(CFG, "situations.already_paid.note_reason"); direct["service_error"] = _s(CFG, "confirmation.failure_note_reason")
    if direct.get(situation): return str(direct[situation])
    allowed = CFG.get("note_reasons") or []
    return situation if situation in allowed else ""

def _customer_name(vars, CFG):
    title = str(_g(vars, "title", "")); last = str(_g(vars, "last_name", "")); first = str(_g(vars, "first_name", ""))
    if title and last: return title + " " + last
    if first and last: return first + " " + last
    return last or first or "the account holder"

def _goodbye(): return "Thank you for your time. Goodbye."


# ---- opening --------------------------------------------------------------------------------------------------------

def _ask_line(vars, CFG):
    return _fill(_s(CFG, "opening.ask_for_customer", "Am I speaking with [[title]] [[last_name]]?"), vars)

def _custom(CFG, label):
    """The custom situation behind a 'custom_<i>' stance label, or None."""
    try:
        i = int(str(label).split("_")[1]) - 1
        cs = list(_s(CFG, "situations.custom") or [])
        return cs[i] if 0 <= i < len(cs) else None
    except Exception:
        return None

def _apply_custom(vars, CFG, c):
    """Say the situation's sentence and close or transfer as the brief says. Returns the route."""
    n = _n_products(vars)
    say = _sentence(c.get("say") or "I understand.")
    act = str(c.get("action") or "close")
    if act == "transfer":
        _transfer(vars, CFG, str(c.get("transfer_queue") or ""), c.get("outcome"))
        vars["say"] = (say + " " + str(_g(vars, "say", ""))).strip(); return "transfer"
    if act == "continue":
        _say(vars, say + " " + str(_g(vars, "last_ask", "")), str(_g(vars, "last_ask", ""))); return "negotiate"
    nr = str(c.get("note_reason") or "")
    for j in range(1, n + 1):
        if str(_pget(vars, j, "state")) == "open": _pset(vars, j, "state", nr or "refused")
    if c.get("outcome"): vars["force_outcome"] = json.dumps(c.get("outcome"))
    vars["custom_note_reason"] = nr
    vars["say_prefix"] = say + " "
    return "close"

def _node_opening_tally(vars, CFG):
    ack = str(_g(vars, "ack", "unclear")); vars["ack"] = "unclear"
    if ack.startswith("custom_") and _custom(CFG, ack):
        c = _custom(CFG, ack); _outcome(vars, c.get("outcome"))
        _say(vars, _sentence(c.get("say") or "I understand.") + " " + _goodbye()); vars["route"] = "close"; return
    qk = str(_g(vars, "q_kind", "none")); vars["q_kind"] = "none"
    ask = _ask_line(vars, CFG)
    route = "again"
    if ack == "customer":
        vars["route"] = "identity"; return
    if ack == "third_party":
        vars["route"] = "third_party"; return
    if ack == "wants_human":
        vars["resume_to"] = "opening"; vars["resume_ask"] = ask
        _say(vars, "Is there anything I can help you with first?"); vars["route"] = "human"; return
    if ack == "wrong_number":
        _outcome(vars, _s(CFG, "third_party.wrong_number.outcome") or _s(CFG, "opening.unclear"))
        _say(vars, "I apologise for the inconvenience. " + _goodbye()); vars["route"] = "close"; return
    if ack == "deceased":
        _outcome(vars, _s(CFG, "third_party.deceased.outcome") or _s(CFG, "opening.unclear"))
        _say(vars, _sentence(_s(CFG, "third_party.deceased.sentence", "I am sorry for your loss.")) + " Goodbye."); vars["route"] = "close"; return
    if ack == "refuses":
        n = _gi(vars, "dnt_count", 0) + 1; vars["dnt_count"] = n
        if n >= int(_s(CFG, "situations.dont_want_to_talk.times", 2) or 2):
            _outcome(vars, _s(CFG, "situations.dont_want_to_talk.before_verified") or _s(CFG, "identity.declined.outcome"))
            _say(vars, "I understand and will not keep you. " + _goodbye()); vars["route"] = "close"; return
    if _cut(vars) and ack in ("unclear", "question") and _gi(vars, "cut_turns", 0) < 3:
        vars["cut_turns"] = _gi(vars, "cut_turns", 0) + 1
        _say(vars, "Sorry, you were cut off. " + ask, ask); vars["route"] = "again"; return
    n = _gi(vars, "ask_count", 1) + 1; vars["ask_count"] = n
    if n > int(_s(CFG, "opening.max_asks", 2) or 2):
        _outcome(vars, _s(CFG, "opening.unclear"))
        _say(vars, "I am sorry, I could not confirm who is on the line, so I will call back another time. Goodbye."); vars["route"] = "close"; return
    reply = _std_reply(vars, CFG, qk) if ack in ("question", "unclear", "refuses") else ""
    if ack == "refuses" and not reply: reply = "I understand, this will only take a moment."
    _say(vars, (reply + " " + ask).strip(), ask); vars["route"] = route


# ---- identity ---------------------------------------------------------------------------------------------------------

def _questions(CFG): return list(_s(CFG, "identity.questions") or [])

def _question(CFG, field):
    for q in _questions(CFG):
        if str(q.get("field", "")) == str(field): return q
    return dict()

def _ask_for(q): return str((q or dict()).get("ask") or "the security answer")

def _node_identity_prep(vars, CFG):
    qs = _questions(CFG)
    vars["id_done"] = ""; vars["id_wrong"] = 0; vars["id_refusals"] = 0; vars["id_buf"] = ""; vars["verified"] = 0
    vars["id_stance"] = "other"; vars["id_answer_text"] = ""; vars["resume_to"] = "identity"
    if not qs:
        vars["id_next_field"] = ""; vars["verified"] = 1; vars["say_prefix"] = "Thank you. "; vars["route"] = "fetch"; return
    vars["id_next_field"] = str(qs[0].get("field", ""))
    howmany = "two" if len(qs) == 2 else ("a few" if len(qs) > 2 else "one")
    ask = "Could you please tell me " + _ask_for(qs[0]) + "?"
    _say(vars, "Thank you. To protect your account, I need to ask you " + howmany + " quick security question" + ("s" if len(qs) != 1 else "") + ". " + ask, ask)
    vars["route"] = "identity"

MONTHS = dict(jan=1, feb=2, mar=3, apr=4, may=5, jun=6, jul=7, aug=8, sep=9, oct=10, nov=11, dec=12)

def _norm_answer(text, q):
    """Normalise a security answer for the tool. Returns (value, complete)."""
    fmt = str((q or dict()).get("answer_format") or "text"); s = str(text or "").strip()
    low = s.lower()
    if fmt == "date_ymd":
        order = str(q.get("numeric_order") or "dmy")
        m = None
        for mm in re.finditer(r"(\d{4})-(\d{1,2})-(\d{1,2})", low): m = mm
        if m: return "%04d-%02d-%02d" % (int(m.group(1)), int(m.group(2)), int(m.group(3))), True
        low2 = _words_to_digits(low)
        low2 = re.sub(r"(\d{1,2})(st|nd|rd|th)\b", r"\1", low2)
        low2 = re.sub(r"\b(\d{1,2})\s+of\s+", r"\1 ", low2)
        low2 = re.sub(r"\bthe\s+(\d{1,2})\b", r"\1", low2)
        for mm in re.finditer(r"(\d{1,2})\s+([a-z]+)\.?,?\s+(?:of\s+)?(\d{4})", low2): m = mm
        if m and m.group(2)[:3] in MONTHS: return "%04d-%02d-%02d" % (int(m.group(3)), MONTHS[m.group(2)[:3]], int(m.group(1))), True
        m = None
        for mm in re.finditer(r"([a-z]+)\.?\s+(\d{1,2}),?\s+(?:of\s+)?(\d{4})", low2): m = mm
        if m and m.group(1)[:3] in MONTHS: return "%04d-%02d-%02d" % (int(m.group(3)), MONTHS[m.group(1)[:3]], int(m.group(2))), True
        m = None
        for mm in re.finditer(r"(\d{4}),?\s+([a-z]+)\s+(\d{1,2})\b", low2): m = mm
        if m and m.group(2)[:3] in MONTHS: return "%04d-%02d-%02d" % (int(m.group(1)), MONTHS[m.group(2)[:3]], int(m.group(3))), True

        m = None
        for mm in re.finditer(r"(\d{1,2})[./\s-](\d{1,2})[./\s-](\d{4})", low2): m = mm
        if m:
            a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            d, mo = (a, b) if order != "mdy" else (b, a)
            if mo > 12 and d <= 12: d, mo = mo, d
            return "%04d-%02d-%02d" % (y, mo, d), True
        return s, False
    if fmt == "digits":
        n = int(q.get("digits_len") or 0)
        digits = re.sub(r"\D", "", _digit_words(low))
        if n:
            if len(digits) >= n: return digits[-n:], True
            return digits, False
        return (digits, bool(digits))
    if fmt == "year":
        m = None
        for mm in re.finditer(r"\b(1[5-9]\d{2}|20\d{2})\b", _words_to_digits(low)): m = mm
        return (m.group(0), True) if m else (s, False)
    if fmt == "alnum":
        v = re.sub(r"[^A-Za-z0-9]", "", s).upper(); return v, bool(v)
    return s, bool(s)

_ONES = dict(zero=0, oh=0, one=1, two=2, three=3, four=4, five=5, six=6, seven=7, eight=8, nine=9, ten=10, eleven=11, twelve=12,
             thirteen=13, fourteen=14, fifteen=15, sixteen=16, seventeen=17, eighteen=18, nineteen=19)
_TENS = dict(twenty=20, thirty=30, forty=40, fifty=50, sixty=60, seventy=70, eighty=80, ninety=90)
_ORD = dict(first=1, second=2, third=3, fourth=4, fifth=5, sixth=6, seventh=7, eighth=8, ninth=9, tenth=10, eleventh=11, twelfth=12,
            thirteenth=13, fourteenth=14, fifteenth=15, sixteenth=16, seventeenth=17, eighteenth=18, nineteenth=19, twentieth=20, thirtieth=30)

def _words_to_digits(s):
    """Spoken numbers to digits: 'twenty-eighth of April nineteen ninety-three' -> '28 of april 1993',
    'two thousand and five' -> '2005', 'forty-four seventy-one' -> '44 71', 'double four' -> '44'."""
    toks = [t for t in re.split(r"[\s,-]+", str(s).lower().replace(".", " . ")) if t]
    out = []; i = 0; n = len(toks)
    def small(j):
        if j >= n: return None, 0
        t = toks[j]
        if t in _TENS:
            if j + 1 < n and toks[j + 1] in _ONES and 0 < _ONES[toks[j + 1]] < 10: return _TENS[t] + _ONES[toks[j + 1]], 2
            if j + 1 < n and toks[j + 1] in _ORD and _ORD[toks[j + 1]] < 10: return _TENS[t] + _ORD[toks[j + 1]], 2
            return _TENS[t], 1
        if t in _ONES: return _ONES[t], 1
        if t in _ORD: return _ORD[t], 1
        return None, 0
    while i < n:
        t = toks[i]
        if t == "double" and i + 1 < n and toks[i + 1] in _ONES and _ONES[toks[i + 1]] < 10:
            out.append(str(_ONES[toks[i + 1]]) * 2); i += 2; continue
        if t in ("nineteen", "eighteen", "seventeen") and i + 1 < n and (toks[i + 1] in _TENS or toks[i + 1] in _ONES or toks[i + 1] == "hundred"):
            if toks[i + 1] == "hundred":
                j = i + 2 + (1 if i + 2 < n and toks[i + 2] == "and" else 0); v, c = small(j)
                out.append(str(_ONES[t] * 100 + (v or 0))); i = j + c; continue
            v, c = small(i + 1)
            if v is not None and v < 100: out.append(str(_ONES[t] * 100 + v)); i += 1 + c; continue
        if t == "twenty" and i + 1 < n and (toks[i + 1] in _TENS or toks[i + 1] in ("hundred", "oh")):
            if toks[i + 1] == "hundred":
                j = i + 2 + (1 if i + 2 < n and toks[i + 2] == "and" else 0); v, c = small(j)
                out.append(str(2000 + (v or 0))); i = j + c; continue
            if toks[i + 1] == "oh":
                v, c = small(i + 2); out.append(str(2000 + (v or 0))); i += 2 + c; continue
            v, c = small(i + 1); out.append(str(2000 + v)); i += 1 + c; continue
        if t == "two" and i + 1 < n and toks[i + 1] == "thousand":
            j = i + 2 + (1 if i + 2 < n and toks[i + 2] == "and" else 0); v, c = small(j)
            out.append(str(2000 + (v or 0))); i = j + c; continue
        if t in ("hundred", "thousand", "and"):
            out.append(t); i += 1; continue
        v, c = small(i)
        if v is not None: out.append(str(v)); i += c; continue
        out.append(t); i += 1
    out = [x for x in out if x != "."]
    # digits said one by one: 'one nine nine three' -> 1993, 'four four seven one' -> 4471 (runs of 3 or more single digits)
    joined = []; run = []
    for x in out + [None]:
        if x is not None and re.fullmatch(r"\d", x): run.append(x); continue
        if len(run) >= 3: joined.append("".join(run))
        else: joined.extend(run)
        run = []
        if x is not None: joined.append(x)
    return " ".join(joined)

def _digit_words(s):
    return _words_to_digits(s)

def _node_identity_eval(vars, CFG): _with_question_reply(vars, CFG, _identity_eval_body)

def _identity_eval_body(vars, CFG):
    st = str(_g(vars, "id_stance", "other")); vars["id_stance"] = "other"
    qk = str(_g(vars, "q_kind", "none")); vars["q_kind"] = "none"
    text = _corrected(_g(vars, "id_answer_text", "")); vars["id_answer_text"] = ""
    field = str(_g(vars, "id_next_field", "")); q = _question(CFG, field)
    ask = "Could you please tell me " + _ask_for(q) + "?"
    if st == "wants_human":
        vars["resume_to"] = "identity"; vars["resume_ask"] = ask
        _say(vars, "Is there anything I can help you with first?"); vars["route"] = "human"; return
    cut = _cut(vars)
    if cut and not text and st in ("declines", "dont_want_to_talk", "other", "answering", "question"):
        _say(vars, "Sorry, you were cut off. " + ask, ask); vars["route"] = "identity"; return
    if st == "asks_what_about" and not _gi(vars, "id_asked_about", 0):
        vars["id_asked_about"] = 1
        _say(vars, _std_reply(vars, CFG, "what_about"), ask); vars["route"] = "identity"; return
    if st in ("declines", "asks_what_about", "dont_want_to_talk"):
        n = _gi(vars, "id_refusals", 0) + 1; vars["id_refusals"] = n
        limit = int(_s(CFG, "identity.declined.max_refusals", 2) or 2)
        if st == "dont_want_to_talk":
            d = _gi(vars, "dnt_count", 0) + 1; vars["dnt_count"] = d
            limit = min(limit, int(_s(CFG, "situations.dont_want_to_talk.times", 2) or 2))
        if n >= limit:
            _outcome(vars, _s(CFG, "identity.declined.outcome"))
            _say(vars, "I understand. Without the security check I cannot continue today. " + _goodbye()); vars["route"] = "close"; return
        explain = _sentence(_s(CFG, "identity.declined.explain_once", "These questions protect your account."))
        _say(vars, explain + " " + ask, ask); vars["route"] = "identity"; return
    if (st == "question" or qk != "none") and not text:
        reply = _std_reply(vars, CFG, qk if qk != "none" else "other")
        _say(vars, reply, ask); vars["route"] = "identity"; return
    if not text:
        _say(vars, "I am sorry, I did not catch that. " + ask, ask); vars["route"] = "identity"; return
    vars["id_refusals"] = 0     # the customer is answering: earlier reluctance no longer counts
    buf = (str(_g(vars, "id_buf", "")) + " " + text).strip()
    value, complete = _norm_answer(buf, q)
    if not complete and not _gi(vars, "id_partial", 0):
        vars["id_buf"] = buf; vars["id_partial"] = 1
        _say(vars, "Please go on, I am listening.", ask); vars["route"] = "identity"; return
    vars["id_buf"] = ""; vars["id_partial"] = 0; vars["id_answer"] = value
    for k in ("vi_ok", "vi_verified", "vi_all", "vi_left", "vi_hint", "vi_error"): vars[k] = ""
    vars["route"] = "verify"

def _truthy(x): return str(x).strip().lower() == "true"

def _node_identity_after(vars, CFG):
    _identity_after_body(vars, CFG)
    pend = str(_g(vars, "q_reply_pending", "")); vars["q_reply_pending"] = ""
    if pend:
        if str(_g(vars, "route", "")) == "fetch": vars["say_prefix"] = pend + " " + str(_g(vars, "say_prefix", ""))
        else: vars["say"] = (pend + " " + str(_g(vars, "say", ""))).strip()

def _identity_after_body(vars, CFG):
    field = str(_g(vars, "id_next_field", "")); q = _question(CFG, field)
    ask = "Could you please tell me " + _ask_for(q) + "?"
    ok = str(_g(vars, "vi_ok", "")); verified = _g(vars, "vi_verified", ""); allv = _g(vars, "vi_all", "")
    left = _g(vars, "vi_left", ""); hint = str(_g(vars, "vi_hint", "")); err = str(_g(vars, "vi_error", ""))
    if ok == "" and verified == "":
        _say(vars, "I am sorry, the verification service did not respond. " + ask, ask); vars["route"] = "identity"; return
    hints = (q or dict()).get("hints") or dict()
    if hint and hint in hints:
        h = hints[hint] or dict()
        if h.get("counts_as_wrong"): vars["id_wrong"] = _gi(vars, "id_wrong", 0) + 1
        _say(vars, _sentence(h.get("say") or "Could you repeat that?") + " " + ask, ask); vars["route"] = "identity"; return
    if not _truthy(ok) and not _truthy(verified):
        if err and "verified" not in err.lower() and "wrong" not in err.lower():
            _say(vars, "I am sorry, I could not read that. " + ask, ask); vars["route"] = "identity"; return
    if _truthy(verified):
        done = [x for x in str(_g(vars, "id_done", "")).split(",") if x]
        if field and field not in done: done.append(field)
        vars["id_done"] = ",".join(done)
        nxt = ""
        for qq in _questions(CFG):
            if str(qq.get("field", "")) not in done and not nxt: nxt = str(qq.get("field", ""))
        if _truthy(allv) or not nxt:
            vars["verified"] = 1; vars["id_next_field"] = ""; vars["say_prefix"] = "Thank you, that is verified. "
            vars["route"] = "fetch"; return
        vars["id_next_field"] = nxt
        ask2 = "Could you please tell me " + _ask_for(_question(CFG, nxt)) + "?"
        _say(vars, "Thank you. And " + ask2[0].lower() + ask2[1:], ask2); vars["route"] = "identity"; return
    wrong = _gi(vars, "id_wrong", 0) + 1; vars["id_wrong"] = wrong
    try: left_n = int(float(left))
    except Exception: left_n = int(_s(CFG, "identity.max_wrong_total", 3) or 3) - wrong
    if left_n <= 0 or wrong >= int(_s(CFG, "identity.max_wrong_total", 3) or 3):
        _outcome(vars, _s(CFG, "identity.failed.outcome"))
        failed = _sentence(_s(CFG, "identity.failed.say", "Please use the mobile app or visit a branch."))
        _say(vars, "I am sorry, that does not match and I cannot verify your identity on this call. " + failed + " " + _goodbye()); vars["route"] = "close"; return
    _say(vars, "I am sorry, that does not match our records. " + ask, ask); vars["route"] = "identity"


# ---- third party ------------------------------------------------------------------------------------------------------

def _node_tp_prep(vars, CFG):
    vars["cb_tries"] = 0
    ask = "When would be a good time to reach " + _customer_name(vars, CFG) + "?"
    _say(vars, "I understand. " + ask, ask); vars["route"] = "third_party"

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

def _node_tp_eval(vars, CFG): _with_question_reply(vars, CFG, _tp_eval_body)

def _tp_eval_body(vars, CFG):
    now = _today(vars, CFG); today = now.date(); cal = _cal(CFG)
    st = str(_g(vars, "tp_stance", "other")); vars["tp_stance"] = "other"
    qk = str(_g(vars, "q_kind", "none")); vars["q_kind"] = "none"
    dtext = _corrected(_g(vars, "cb_date_text", "")); ttext = _corrected(_g(vars, "cb_time_text", ""))
    vars["cb_date_text"] = ""; vars["cb_time_text"] = ""
    cb = _s(CFG, "third_party.callback") or dict()
    name = _customer_name(vars, CFG)
    ask = str(_g(vars, "last_ask", "When would be a good time to reach " + name + "?"))
    if st == "wrong_number":
        _outcome(vars, _s(CFG, "third_party.wrong_number.outcome")); _say(vars, "I apologise for the inconvenience. " + _goodbye()); vars["route"] = "close"; return
    if st == "deceased":
        _outcome(vars, _s(CFG, "third_party.deceased.outcome")); _say(vars, _sentence(_s(CFG, "third_party.deceased.sentence", "I am sorry for your loss.")) + " Goodbye."); vars["route"] = "close"; return
    if st == "refuses" or not cb.get("enabled", True):
        _outcome(vars, cb.get("not_scheduled") or _s(CFG, "opening.unclear")); _say(vars, "I understand. " + _goodbye()); vars["route"] = "close"; return
    if _cut(vars) and not dtext and not ttext:
        _say(vars, "Sorry, you were cut off. " + ask, ask); vars["route"] = "again"; return
    if not dtext and not ttext:
        reply = _std_reply(vars, CFG, qk) if qk != "none" else "I am afraid I can only discuss this with " + name + "."
        _say(vars, reply + " " + ask, ask); vars["route"] = "again"; return
    allowed = _cb_allowed_dates(today, CFG)
    d_status, d_val = _resolve_date_expr(dtext, now, cal) if dtext else ("none", "")
    d = _to_date(d_val) if d_status == "date" else None
    t = _parse_time(ttext) if ttext else None
    if d is None and t is not None:
        if t > now.strftime("%H:%M"): d = today
        elif len(allowed) > 1: d = allowed[1]
    ws = str(cb.get("window_start") or "00:00"); we = str(cb.get("window_end") or "23:59")
    ok = d is not None and t is not None and d in allowed and ws <= t <= we
    if ok and cb.get("after_now", True) and d == today and t <= now.strftime("%H:%M"): ok = False
    if ok:
        vars["cb_date"] = d.isoformat(); vars["cb_time"] = t
        _say(vars, "Thank you. I will call back on " + str(_speak_date(d.isoformat())) + " at " + t + ". " + _goodbye()); vars["route"] = "schedule"; return
    tries = _gi(vars, "cb_tries", 0) + 1; vars["cb_tries"] = tries
    if tries > int(cb.get("retries_if_outside") or 1):
        _outcome(vars, cb.get("not_scheduled")); _say(vars, "I understand. We will try again another time. " + _goodbye()); vars["route"] = "close"; return
    days = " or ".join(str(_speak_date(x.isoformat()) or "") for x in allowed[:2])
    if t is None and d is not None: ask2 = "What time on " + str(_speak_date(d.isoformat())) + " would suit, between " + ws + " and " + we + "?"
    else: ask2 = "I can arrange a call back " + days + ", between " + ws + " and " + we + ". When would suit?"
    _say(vars, ("I am sorry, that time is not possible. " if (t is not None or d is not None) else "") + ask2, ask2); vars["route"] = "again"


# ---- products -----------------------------------------------------------------------------------------------------------

def _roles(CFG): return CFG.get("roles") or dict()

def _pname(p, CFG):
    wording = _s(CFG, "debt_statement.product_wording") or dict(); roles = _roles(CFG)
    t = str(p.get(roles.get("type", "type"), ""))
    tpl = wording.get(t)
    if not tpl: return t.replace("_", " ") or "product"
    out = str(tpl)
    for key, val in p.items(): out = out.replace("{" + str(key) + "}", str(val))
    return re.sub(r"\{[A-Za-z_][\w]*\}", "", out).strip()

def _first_ask(CFG): return _sentence(_s(CFG, "persuasion.first_ask", "Can you make this payment today?"))

def _node_product_facts(vars, CFG):
    now = _today(vars, CFG); today = now.date(); cal = _cal(CFG); roles = _roles(CFG)
    products = _products_from_vars(vars)
    bands = list(_s(CFG, "bands") or [])
    floor_cfg = dict()
    floor_cfg["floor_kind"] = _s(CFG, "amount_rules.floor_kind", "by_product_type"); floor_cfg["floor_by_type"] = _s(CFG, "amount_rules.floor_by_type") or dict()
    floor_cfg["floor_fraction"] = _s(CFG, "amount_rules.floor_fraction", 0); floor_cfg["floor_fixed"] = _s(CFG, "amount_rules.floor_fixed", 0)
    vars["today_iso"] = today.isoformat()
    n = len(products); vars["n_products"] = n
    prefix = str(_g(vars, "say_prefix", "")); vars["say_prefix"] = ""
    if n == 0:
        vars["acct_state"] = "error"; _outcome(vars, _s(CFG, "confirmation.failure_outcome"))
        _say(vars, prefix + "I am sorry, your account details are not available right now; the bank will call you again. " + _goodbye()); vars["route"] = "error"; return
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
        _pset(vars, k, "recorded", 0); _pset(vars, k, "rec_tried", ""); _pset(vars, k, "turns", 0)
        sentences.append("Your " + name + " has " + _money(full, CFG) + " past due, " + str(late) + " days late.")
    vars["cur_k"] = 1; vars["promise_count"] = 0; vars["transfer_flag"] = 0; vars["transfer_queue"] = ""
    vars["stance"] = "none"; vars["prop_date_text"] = ""; vars["prop_amount_text"] = ""; vars["prop_product_text"] = ""; vars["q_kind"] = "none"
    intro = _sentence(_s(CFG, "debt_statement.intro", "This call is about a late payment."))
    vars["multi_mode"] = 1 if (n > 1 and _s(CFG, "multi_product.ask_all_today_first", True)) else 0
    if vars["multi_mode"]:
        vars["neg_phase"] = "all"; ask = "Can you pay all of them today?"
        _say(vars, prefix + intro + " " + " ".join(sentences) + " " + ask, ask)
    else:
        vars["neg_phase"] = "product"; ask = _first_ask(CFG)
        _say(vars, prefix + intro + " " + sentences[0] + " " + ask, ask)
    vars["route"] = "negotiate"


# ---- negotiation ----------------------------------------------------------------------------------------------------------

def _attempt_offers(vars, k, CFG):
    band = str(_pget(vars, k, "band", "")); out = []
    for a in list(_s(CFG, "persuasion.attempts") or []):
        bands = a.get("bands") or []
        if bands and band not in bands: continue
        out.append(a)
    return out

def _offer_amount(vars, k, kind):
    if kind == "full": return _gf(vars, _pk(k, "full"))
    if kind == "floor": return _gf(vars, _pk(k, "floor"))
    return _gf(vars, _pk(k, "ask_amount"), _gf(vars, _pk(k, "full")))

def _when(vars, CFG, date_iso):
    today = str(_g(vars, "today_iso", ""))
    if date_iso == today: return "today"
    return "on " + str(_speak_date(date_iso) or date_iso)

def _ask_pay(vars, k, amount, date_iso, CFG, lead=""):
    q = "Can you pay " + _money(amount, CFG) + " for the " + str(_pget(vars, k, "name", "product")) + " " + _when(vars, CFG, date_iso) + "?"
    vars["last_question"] = q
    return (lead + " " if lead else "") + q

def _make_attempt(vars, k, CFG, now):
    """Use one persuasion attempt. Returns the sentence to say, or '' when attempts are exhausted."""
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
            lead = "I understand."
            if str(a.get("amount")) == "floor":
                _pset(vars, k, "floor_offered", 1)
                lead = "I understand. The minimum I can record is " + _money(amt, CFG) + "; " + _sentence(_s(CFG, "amount_rules.too_much_say", "the rest stays overdue")).lower().capitalize()
                return lead + " " + _ask_pay(vars, k, amt, d, CFG)
            return _ask_pay(vars, k, amt, d, CFG, lead)
        i += 1; used += 1; _pset(vars, k, "attempts_used", used)
    return ""

def _advance(vars, CFG, now):
    """The current product is settled. Next open product, or confirmation, or closing."""
    n = _n_products(vars); prefix = str(_g(vars, "say_prefix", "")); vars["say_prefix"] = ""
    for k in range(1, n + 1):
        if str(_pget(vars, k, "state", "open")) == "open":
            vars["cur_k"] = k; _pset(vars, k, "turns", 0)
            head = "Now the " + str(_pget(vars, k, "name")) + ": " + _money(_gf(vars, _pk(k, "full")), CFG) + " past due, " + str(_pget(vars, k, "days_late")) + " days late."
            if _gi(vars, "multi_mode", 0):
                line = _make_attempt(vars, k, CFG, now)
                if line:
                    _say(vars, prefix + head + " " + line.replace("I understand. ", "", 1)); return "negotiate"
                _pset(vars, k, "state", "refused"); continue
            _say(vars, prefix + head + " " + _first_ask(CFG), _first_ask(CFG)); return "negotiate"
    agreed = [k for k in range(1, n + 1) if str(_pget(vars, k, "state")) == "agreed"]
    if agreed:
        _build_readback(vars, CFG, prefix); return "confirm"
    vars["say_prefix"] = prefix
    return "close"

def _build_readback(vars, CFG, prefix=""):
    n = _n_products(vars); parts = []
    for k in range(1, n + 1):
        if str(_pget(vars, k, "state")) != "agreed": continue
        d = str(_pget(vars, k, "agreed_date")); a = _gf(vars, _pk(k, "agreed_amount"))
        s = _money(a, CFG) + " for the " + str(_pget(vars, k, "name")) + " " + _when(vars, CFG, d)
        if _gi(vars, _pk(k, "capped"), 0): s += ", which is its latest possible date"
        parts.append(s)
    q = _sentence(_s(CFG, "confirmation.question", "Do you confirm?"))
    vars["readback_text"] = "; ".join(parts)
    ask = "To confirm: " + "; ".join(parts) + ". " + q
    _say(vars, prefix + ask, ask); vars["confirm_stance"] = "none"

def _validate_date(vars, k, d_status, d_val, CFG, now):
    """Returns (ok_iso, sentence). ok_iso is set when the date is acceptable as is."""
    cal = _cal(CFG); today = now.date(); deadline = str(_pget(vars, k, "deadline", "")); dl = _to_date(deadline)
    rules = _s(CFG, "date_rules") or dict(); amt = _gf(vars, _pk(k, "ask_amount"))
    if d_status == "vague":
        if rules.get("vague_ask_exact_once", True) and not _gi(vars, _pk(k, "vague_asked"), 0):
            _pset(vars, k, "vague_asked", 1); return "", "Which exact day can you pay?"
        then = str(rules.get("vague_then") or "propose_deadline")
        d = deadline if then == "propose_deadline" else _next_business_day(today, cal).isoformat()
        if d:
            _pset(vars, k, "offer_date", d); _pset(vars, k, "offer_amount", amt)
            return "", _ask_pay(vars, k, amt, d, CFG, "I need an exact day; the latest I can record is " + str(_speak_date(d)) + ".")
        return "", "Which exact day can you pay?"
    if d_status != "date": return "", "Which exact day can you pay?"
    d = _to_date(d_val)
    if d is None: return "", "Which exact day can you pay?"
    earliest = today
    if str(rules.get("earliest")) == "tomorrow": earliest = today + datetime.timedelta(days=1)
    if str(rules.get("earliest")) == "next_business_day": earliest = _next_business_day(today, cal)
    if d < earliest: return "", "That date has already passed. Which day from " + ("today" if earliest == today else str(_speak_date(earliest.isoformat()))) + " can you pay?"
    if dl is not None and d > dl:
        if str(rules.get("after_deadline") or "offer_deadline") == "offer_deadline":
            _pset(vars, k, "deadline_offered", 1); _pset(vars, k, "offer_date", deadline); _pset(vars, k, "offer_amount", amt)
            return "", _ask_pay(vars, k, amt, deadline, CFG, "The latest date I can record is " + str(_speak_date(deadline)) + ".")
        return "", "That is after the latest possible date, " + str(_speak_date(deadline)) + ". Which earlier day can you pay?"
    if rules.get("must_be_business_day", True) and not _is_business_day(d, cal):
        act = str(rules.get("non_business_day") or "offer_next_business_day")
        nb = _next_business_day(d, cal)
        if act == "offer_previous_business_day":
            nb = d
            while not _is_business_day(nb, cal): nb = nb - datetime.timedelta(days=1)
        if act in ("offer_next_business_day", "offer_previous_business_day") and nb is not None:
            if dl is not None and nb > dl: nb = dl; _pset(vars, k, "deadline_offered", 1)
            _pset(vars, k, "offer_date", nb.isoformat()); _pset(vars, k, "offer_amount", amt)
            why = "a bank holiday" if d.weekday() in (cal.get("business_weekdays") or [0, 1, 2, 3, 4]) else "a weekend day"
            return "", _ask_pay(vars, k, amt, nb.isoformat(), CFG, str(_speak_date(d.isoformat())) + " is " + why + ", so the next business day is " + str(_speak_date(nb.isoformat())) + ".")
        return "", "That day is not a business day. Which other day can you pay?"
    return d.isoformat(), ""

def _validate_amount(vars, k, amt, CFG):
    """Returns (ok_amount, sentence)."""
    full = _gf(vars, _pk(k, "full")); floor = _gf(vars, _pk(k, "floor"), full)
    rules = _s(CFG, "amount_rules") or dict()
    if amt is None: return _gf(vars, _pk(k, "ask_amount"), full), ""
    if amt >= full - 0.005: return full, ""
    if amt >= floor - 0.005:
        if str(rules.get("between_floor_and_full") or "accept") == "accept": return amt, ""
        return None, "I can only record the full amount of " + _money(full, CFG) + ". Can you pay that?"
    if rules.get("below_floor_offer_floor_once", True) and not _gi(vars, _pk(k, "floor_offered"), 0):
        _pset(vars, k, "floor_offered", 1); _pset(vars, k, "ask_amount", floor); _pset(vars, k, "offer_amount", floor)
        say = _sentence(rules.get("below_floor_say") or "That amount cannot be recorded.")
        return None, say + " The minimum I can record is " + _money(floor, CFG) + "."
    return None, "FLAT_REFUSAL"

def _settle(vars, k, date_iso, amount, CFG):
    _pset(vars, k, "agreed_date", date_iso); _pset(vars, k, "agreed_amount", amount); _pset(vars, k, "state", "agreed")

def _with_question_reply(vars, CFG, body):
    """A side question in the customer's message gets its standard reply in front of whatever the node says next."""
    qk = str(_g(vars, "q_kind", "none"))
    body(vars, CFG)
    if qk != "none" and str(_g(vars, "route", "")) in ("negotiate", "confirm", "hardship", "again", "identity", "third_party"):
        reply = _std_reply(vars, CFG, qk)
        say = str(_g(vars, "say", ""))
        if reply and reply.lower() not in say.lower(): vars["say"] = (reply + " " + say).strip()
    elif qk != "none" and str(_g(vars, "route", "")) in ("verify", "fetch", "schedule"):
        vars["q_reply_pending"] = _std_reply(vars, CFG, qk)

def _node_eval(vars, CFG): _with_question_reply(vars, CFG, _eval_body)

def _eval_body(vars, CFG):
    now = _today(vars, CFG); today = now.date(); cal = _cal(CFG)
    k = _gi(vars, "cur_k", 1); n = _n_products(vars)
    stance = str(_g(vars, "stance", "none")); dtext = _corrected(_g(vars, "prop_date_text", "")); atext = _corrected(_g(vars, "prop_amount_text", ""))
    ptext = str(_g(vars, "prop_product_text", "")); qk = str(_g(vars, "q_kind", "none"))
    # 'pieces': an amount said in two parts ('six hundred thirty-seven' then 'fifty') - a bare small number right after an amount is its cents
    prev_amt = str(_g(vars, "last_amount_text", "")); vars["last_amount_text"] = atext
    if atext and prev_amt and re.fullmatch(r"\s*(\d{1,2}|[a-z-]+)\s*", atext) and _parse_amount(atext) is not None and _parse_amount(atext) < 100 and _parse_amount(prev_amt) is not None and float(_parse_amount(prev_amt)).is_integer():
        atext = ("%d" % int(_parse_amount(prev_amt))) + "." + ("%02d" % int(_parse_amount(atext))); vars["last_amount_text"] = atext
    vars["stance"] = "none"; vars["prop_date_text"] = ""; vars["prop_amount_text"] = ""; vars["prop_product_text"] = ""; vars["q_kind"] = "none"
    _pset(vars, k, "turns", _gi(vars, _pk(k, "turns"), 0) + 1)
    # a bare day number is a day of the month when it comes as a payment date ('on 30' -> 'the 30th')
    if re.fullmatch(r"\s*(?:the\s+)?([0-9]{1,2})(?:st|nd|rd|th)?\.?\s*", dtext or ""):
        dtext = "the " + re.sub(r"\D", "", dtext) + "th"
    d_status, d_val = _resolve_date_expr(dtext, now, cal) if dtext else ("none", "")
    # 'pieces': a date said in two parts ('30' then 'October'); keep the unresolved piece and retry with the next one
    prev_piece = str(_g(vars, "date_piece", ""))
    if dtext and d_status != "date" and prev_piece:
        combo = prev_piece + " " + dtext
        st2, val2 = _resolve_date_expr(combo, now, cal)
        if st2 == "date": d_status, d_val, dtext = st2, val2, combo
        else:
            combo = dtext + " " + prev_piece; st2, val2 = _resolve_date_expr(combo, now, cal)
            if st2 == "date": d_status, d_val, dtext = st2, val2, combo
    vars["date_piece"] = dtext if (dtext and d_status != "date") else ""
    amt = _parse_amount(atext) if atext else None
    phase = str(_g(vars, "neg_phase", "product"))
    last_ask = str(_g(vars, "last_ask", _first_ask(CFG)))
    if stance in ("refuses", "other", "none", "vague", "agrees", "question") and (d_status != "none" or amt is not None):
        if stance != "agrees" or d_status == "date" or amt is not None: stance = "proposes"
    if stance.startswith("custom_") and _custom(CFG, stance):
        r = _apply_custom(vars, CFG, _custom(CFG, stance)); vars["route"] = r if r != "close" else "close"; return
    if stance == "question" or (stance in ("other", "none") and qk != "none"):
        _say(vars, _std_reply(vars, CFG, qk if qk != "none" else "other") + " " + last_ask, last_ask); vars["route"] = "negotiate"; return
    # a turn with nothing about the payment in it (small talk, a sentence the platform cut off): ask again before it counts
    cut = _cut(vars)
    if (stance in ("other", "none") or (cut and stance in ("refuses", "vague", "too_much"))) and d_status == "none" and amt is None and not ptext:
        na = _gi(vars, "nonanswer_count", 0) + 1; vars["nonanswer_count"] = na
        if na <= (8 if cut else 4):
            _say(vars, ("Sorry, you were cut off. " if cut else "Sorry, I missed that. ") + last_ask, last_ask); vars["route"] = "negotiate"; return
        vars["nonanswer_count"] = 0
        if stance in ("other", "none"): stance = "refuses"
    else:
        vars["nonanswer_count"] = 0
    if stance == "human":
        vars["resume_to"] = "negotiate"; vars["resume_ask"] = last_ask
        _say(vars, "Is there anything I can help you with first?"); vars["route"] = "human"; return
    if stance == "plan":
        _transfer(vars, CFG, str(_s(CFG, "situations.plan_request.queue", "") or ""), _s(CFG, "situations.plan_request.outcome")); vars["route"] = "transfer"; return
    if stance == "hardship":
        offer = str(_s(CFG, "hardship.offer", "connect you with our customer support team") or "")
        q = offer if offer.strip().endswith("?") else "Would you like me to " + offer.rstrip(".") + "?"
        _say(vars, _sentence(_s(CFG, "hardship.sympathy", "I am sorry to hear that.")) + " " + q, q)
        vars["hs_stance"] = "none"; vars["route"] = "hardship"; return
    if stance == "dont_want_to_talk":
        d = _gi(vars, "dnt_count", 0) + 1; vars["dnt_count"] = d
        if d >= int(_s(CFG, "situations.dont_want_to_talk.times", 2) or 2):
            for j in range(1, n + 1):
                if str(_pget(vars, j, "state")) == "open": _pset(vars, j, "state", "refused")
            vars["force_outcome"] = json.dumps(_s(CFG, "situations.dont_want_to_talk.after_verified") or dict())
            vars["say_prefix"] = "I understand and will not keep you. "; vars["route"] = "close"; return
        _say(vars, "I understand, I will be brief. " + last_ask, last_ask); vars["route"] = "negotiate"; return
    if stance == "paid":
        if (phase == "all" and n > 1) or not _s(CFG, "multi_product.dispute_or_paid_does_not_end_call", True):
            for j in range(1, n + 1):
                if str(_pget(vars, j, "state")) == "open": _pset(vars, j, "state", "paid")
        else: _pset(vars, k, "state", "paid")
        vars["say_prefix"] = "Thank you. " + _sentence(_s(CFG, "situations.already_paid.say", "Payments can take one business day to appear.")) + " "
        vars["route"] = _advance(vars, CFG, now); return
    if stance == "dispute":
        if (phase == "all" and n > 1) or not _s(CFG, "multi_product.dispute_or_paid_does_not_end_call", True):
            for j in range(1, n + 1):
                if str(_pget(vars, j, "state")) == "open": _pset(vars, j, "state", "dispute")
        else: _pset(vars, k, "state", "dispute")
        vars["say_prefix"] = "I have noted that you dispute this, and I will not argue the point. "
        vars["route"] = _advance(vars, CFG, now); return
    if phase == "all" and n > 1:
        if stance == "agrees":
            for j in range(1, n + 1):
                if str(_pget(vars, j, "state")) == "open": _settle(vars, j, today.isoformat(), _gf(vars, _pk(j, "full")), CFG)
            vars["route"] = _advance(vars, CFG, now); return
        if stance == "proposes" and d_status != "date" and amt is None and not _match_product(vars, ptext, n):
            asked = _gi(vars, "all_exact_asked", 0) + 1; vars["all_exact_asked"] = asked
            if asked <= 2:
                _say(vars, "Which exact day can you pay?"); vars["route"] = "negotiate"; return
            vars["neg_phase"] = "product"; vars["route"] = _advance(vars, CFG, now); return
        if stance == "proposes":
            target = _match_product(vars, ptext, n)
            if target:
                vars["neg_phase"] = "product"; vars["cur_k"] = target; k = target
            else:
                ok_any = False
                for j in range(1, n + 1):
                    if str(_pget(vars, j, "state")) != "open": continue
                    pd = _to_date(d_val) if d_status == "date" else None; dl = _to_date(str(_pget(vars, j, "deadline")))
                    if pd is not None and dl is not None and pd > dl and str(_s(CFG, "multi_product.one_date_past_a_deadline", "that_product_on_its_own_deadline")) == "that_product_on_its_own_deadline":
                        _settle(vars, j, dl.isoformat(), _gf(vars, _pk(j, "full")), CFG); _pset(vars, j, "capped", 1); ok_any = True; continue
                    d_ok, line = _validate_date(vars, j, d_status, d_val, CFG, now)
                    if d_ok:
                        _settle(vars, j, d_ok, _gf(vars, _pk(j, "full")), CFG); ok_any = True
                    else:
                        vars["cur_k"] = j; vars["neg_phase"] = "product"; _say(vars, line); vars["route"] = "negotiate"; return
                if ok_any: vars["route"] = _advance(vars, CFG, now); return
        if stance in ("refuses", "too_much", "other", "none"):
            vars["neg_phase"] = "product"
            if stance == "too_much":
                for j in range(1, n + 1): _pset(vars, j, "ask_amount", _gf(vars, _pk(j, "floor")))
            vars["route"] = _advance(vars, CFG, now); return
    # ---- single product k ----
    if stance == "proposes" and n > 1 and _means_all(ptext) and d_status == "date" and amt is None:
        if _settle_all_open(vars, CFG, d_status, d_val, now):
            vars["route"] = _advance(vars, CFG, now); return
    if stance == "agrees":
        d = str(_pget(vars, k, "offer_date", "")) or today.isoformat()
        a = _pget(vars, k, "offer_amount", "")
        a = float(a) if a != "" else _gf(vars, _pk(k, "ask_amount"), _gf(vars, _pk(k, "full")))
        if _s(CFG, "date_rules.must_be_business_day", True) and not _is_business_day(_to_date(d), cal): d = _next_business_day(_to_date(d), cal).isoformat()
        _settle(vars, k, d, a, CFG); vars["route"] = _advance(vars, CFG, now); return
    if stance == "proposes":
        a_ok, a_line = _validate_amount(vars, k, amt, CFG)
        if a_line == "FLAT_REFUSAL": stance = "refuses"
        else:
            if a_ok is None:
                pd = _to_date(d_val) if d_status == "date" else None; dl = _to_date(str(_pget(vars, k, "deadline", "")))
                od = str(_pget(vars, k, "offer_date", "")) or today.isoformat()
                if pd is not None and pd >= today and _is_business_day(pd, cal) and (dl is None or pd <= dl): od = pd.isoformat()
                _pset(vars, k, "offer_date", od)
                _say(vars, a_line + " " + _ask_pay(vars, k, _gf(vars, _pk(k, "offer_amount")), od, CFG)); vars["route"] = "negotiate"; return
            if d_status == "none":
                if amt is not None:
                    _pset(vars, k, "ask_amount", a_ok); _pset(vars, k, "offer_amount", a_ok)
                    od = str(_pget(vars, k, "offer_date", "")) or today.isoformat(); _pset(vars, k, "offer_date", od)
                    _say(vars, _ask_pay(vars, k, a_ok, od, CFG, "I can record " + _money(a_ok, CFG) + "."))
                else:
                    _say(vars, "Which exact day can you pay?")
                vars["route"] = "negotiate"; return
            d_ok, d_line = _validate_date(vars, k, d_status, d_val, CFG, now)
            if d_ok:
                _settle(vars, k, d_ok, a_ok, CFG); vars["route"] = _advance(vars, CFG, now); return
            if amt is not None: _pset(vars, k, "ask_amount", a_ok)
            _say(vars, d_line); vars["route"] = "negotiate"; return
    if stance == "too_much":
        full = _gf(vars, _pk(k, "full")); floor = _gf(vars, _pk(k, "floor"), full)
        if _s(CFG, "amount_rules.too_much_offer_floor_once", True) and not _gi(vars, _pk(k, "floor_offered"), 0) and floor < full:
            _pset(vars, k, "floor_offered", 1); _pset(vars, k, "ask_amount", floor)
            od = str(_pget(vars, k, "offer_date", "")) or today.isoformat(); _pset(vars, k, "offer_date", od); _pset(vars, k, "offer_amount", floor)
            rest = _sentence(_s(CFG, "amount_rules.too_much_say", "The rest stays overdue."))
            _say(vars, _ask_pay(vars, k, floor, od, CFG, "I understand. The minimum I can record is " + _money(floor, CFG) + "; " + rest[0].lower() + rest[1:])); vars["route"] = "negotiate"; return
        stance = "refuses"
    line = _make_attempt(vars, k, CFG, now)
    if line:
        _say(vars, line); vars["route"] = "negotiate"; return
    _pset(vars, k, "state", "refused")
    vars["say_prefix"] = "I understand, I will not insist. "
    vars["route"] = _advance(vars, CFG, now)

def _means_all(text):
    return bool(re.search(r"\b(both|all|everything|all of them|the two|the three|each of them|every one)\b", str(text or "").lower()))

def _settle_all_open(vars, CFG, d_status, d_val, now):
    """One date for every open product: each is capped to its own deadline when the brief says so. Returns True when any settled."""
    n = _n_products(vars); ok_any = False
    pd = _to_date(d_val) if d_status == "date" else None
    if pd is None: return False
    for j in range(1, n + 1):
        if str(_pget(vars, j, "state")) != "open": continue
        dl = _to_date(str(_pget(vars, j, "deadline")))
        if dl is not None and pd > dl and str(_s(CFG, "multi_product.one_date_past_a_deadline", "that_product_on_its_own_deadline")) == "that_product_on_its_own_deadline":
            _settle(vars, j, dl.isoformat(), _gf(vars, _pk(j, "ask_amount"), _gf(vars, _pk(j, "full"))), CFG); _pset(vars, j, "capped", 1); ok_any = True; continue
        d_ok, line = _validate_date(vars, j, d_status, d_val, CFG, now)
        if d_ok: _settle(vars, j, d_ok, _gf(vars, _pk(j, "ask_amount"), _gf(vars, _pk(j, "full"))), CFG); ok_any = True
    return ok_any

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
    team = (str(queue or "").replace("_", " ") + " team") if queue else "right team"
    _say(vars, "I will connect you to the " + team + " now. " + _goodbye())


def _node_eval_hardship(vars, CFG): _with_question_reply(vars, CFG, _eval_hardship_body)

def _eval_hardship_body(vars, CFG):
    now = _today(vars, CFG); n = _n_products(vars)
    st = str(_g(vars, "hs_stance", "none")); vars["hs_stance"] = "none"
    qk = str(_g(vars, "q_kind", "none")); vars["q_kind"] = "none"
    dtext = str(_g(vars, "prop_date_text", "")); atext = str(_g(vars, "prop_amount_text", ""))
    last_ask = str(_g(vars, "last_ask", ""))
    if st == "accepts":
        _transfer(vars, CFG, str(_s(CFG, "hardship.accept_queue", "") or ""), _s(CFG, "hardship.accept_outcome")); vars["route"] = "transfer"; return
    if (st == "proposes" or dtext or atext) and _s(CFG, "hardship.record_if_customer_names_date_or_amount", True) and (dtext or atext):
        vars["stance"] = "proposes"; vars["route"] = "eval"; return
    if st in ("other", "none") and qk != "none":
        _say(vars, _std_reply(vars, CFG, qk) + " " + last_ask, last_ask); vars["route"] = "again"; return
    for j in range(1, n + 1):
        if str(_pget(vars, j, "state")) == "open": _pset(vars, j, "state", "hardship")
    vars["say_prefix"] = "I understand. "
    vars["route"] = _advance(vars, CFG, now)


def _node_eval_human(vars, CFG):
    st = str(_g(vars, "hum_stance", "other")); vars["hum_stance"] = "other"
    if st == "insists":
        _transfer(vars, CFG, str(_s(CFG, "situations.human_request.queue", "") or ""), _s(CFG, "situations.human_request.outcome")); vars["route"] = "transfer"; return
    back = str(_g(vars, "resume_to", "negotiate")); ask = str(_g(vars, "resume_ask", "") or _g(vars, "last_ask", ""))
    _say(vars, "Thank you. " + ask, ask)
    vars["route"] = back


# ---- confirmation and recording -------------------------------------------------------------------------------------------

def _node_eval_confirm(vars, CFG): _with_question_reply(vars, CFG, _eval_confirm_body)

def _eval_confirm_body(vars, CFG):
    now = _today(vars, CFG); n = _n_products(vars)
    st = str(_g(vars, "confirm_stance", "none")); vars["confirm_stance"] = "none"
    qk = str(_g(vars, "q_kind", "none")); vars["q_kind"] = "none"
    dtext = _corrected(_g(vars, "prop_date_text", "")); atext = _corrected(_g(vars, "prop_amount_text", "")); ptext = str(_g(vars, "prop_product_text", ""))
    vars["prop_date_text"] = ""; vars["prop_amount_text"] = ""; vars["prop_product_text"] = ""
    last_ask = str(_g(vars, "last_ask", ""))
    if st == "yes":
        vars["route"] = _next_record(vars, CFG); return
    if st == "change" or (st in ("other", "none", "question", "no") and (dtext or atext)):
        agreed = [k for k in range(1, n + 1) if str(_pget(vars, k, "state")) == "agreed"]
        k = _match_product(vars, ptext, n) or (agreed[0] if len(agreed) == 1 else 0)
        if not k:
            ask = "Which product is that change for?"; _say(vars, ask, ask); vars["route"] = "confirm"; return
        _pset(vars, k, "state", "open"); vars["cur_k"] = k; vars["neg_phase"] = "product"
        vars["stance"] = "proposes"; vars["prop_date_text"] = dtext; vars["prop_amount_text"] = atext
        vars["route"] = "eval"; return
    if st == "no":
        for k in range(1, n + 1):
            if str(_pget(vars, k, "state")) == "agreed": _pset(vars, k, "state", "open")
        opens = [k for k in range(1, n + 1) if str(_pget(vars, k, "state")) == "open"]
        vars["cur_k"] = opens[0] if opens else 1
        vars["neg_phase"] = "product"; vars["stance"] = "refuses"; vars["route"] = "eval"; return
    cut = _cut(vars)
    reply = _std_reply(vars, CFG, qk) if qk != "none" else ("Sorry, you were cut off." if cut else "I am sorry, I need a clear yes or no.")
    _say(vars, reply + " " + last_ask, last_ask); vars["route"] = "confirm"

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
    ok = _truthy(_g(vars, "rec_ok", "")) or _truthy(_g(vars, "rec_ok_retry", ""))
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
    allowed = CFG.get("note_reasons") or []
    if notes_on:
        for k, st in states:
            if k in recorded: continue
            r = _note_reason(CFG, st)
            if not r and st in allowed: r = st
            if r: notes.append((k, r))
    vars["note_1_pid"] = ""; vars["note_1_reason"] = ""; vars["note_2_pid"] = ""; vars["note_2_reason"] = ""; vars["note_3_pid"] = ""; vars["note_3_reason"] = ""
    vars["note_4_pid"] = ""; vars["note_4_reason"] = ""; vars["note_5_pid"] = ""; vars["note_5_reason"] = ""
    if len(notes) > 0: vars["note_1_pid"] = str(_pget(vars, notes[0][0], "id")); vars["note_1_reason"] = notes[0][1]
    if len(notes) > 1: vars["note_2_pid"] = str(_pget(vars, notes[1][0], "id")); vars["note_2_reason"] = notes[1][1]
    if len(notes) > 2: vars["note_3_pid"] = str(_pget(vars, notes[2][0], "id")); vars["note_3_reason"] = notes[2][1]
    if len(notes) > 3: vars["note_4_pid"] = str(_pget(vars, notes[3][0], "id")); vars["note_4_reason"] = notes[3][1]
    if len(notes) > 4: vars["note_5_pid"] = str(_pget(vars, notes[4][0], "id")); vars["note_5_reason"] = notes[4][1]
    forced = str(_g(vars, "force_outcome", ""))
    if transfer: pass
    elif forced:
        try: _outcome(vars, json.loads(forced))
        except Exception: _outcome(vars, dict())
    elif str(_g(vars, "acct_state", "ok")) != "ok" and str(_g(vars, "outcome", "")): pass
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
    # the farewell
    parts = [str(_g(vars, "say_prefix", ""))]; vars["say_prefix"] = ""
    if transfer:
        _say(vars, (parts[0] + str(_g(vars, "say", ""))).strip()); vars["route"] = "farewell"; return
    if recorded:
        items = []
        for k in recorded: items.append(_money(_gf(vars, _pk(k, "agreed_amount")), CFG) + " for the " + str(_pget(vars, k, "name")) + " " + _when(vars, CFG, str(_pget(vars, k, "agreed_date"))))
        parts.append("Thank you. Your promise to pay " + "; ".join(items) + " is recorded.")
        said = []
        for s in list(_s(CFG, "confirmation.after_recorded_sentences") or []):
            parts.append(_sentence(s)); said.append(_sentence(s))
        for ms in list(_s(CFG, "mandatory_sentences") or []):
            if str(ms.get("when")) == "after_promise_recorded" and _sentence(ms.get("text")) not in said: parts.append(_sentence(ms.get("text")))
    failed = [k for k, st in states if st == "service_error"]
    if failed:
        parts.append(_sentence(_s(CFG, "confirmation.failure_say", "I am sorry, I could not record the promise.")) + (" This concerns the " + " and the ".join(str(_pget(vars, k, "name")) for k in failed) + "." if n > 1 else ""))
    if any(st == "paid" for k, st in states) and not recorded and "business day" not in parts[0]:
        parts.append(_sentence(_s(CFG, "situations.already_paid.say", "Payments can take one business day to appear.")))
    parts.append(_goodbye())
    _say(vars, " ".join(p for p in parts if p).strip())
    vars["route"] = "note_1" if notes else "farewell"


def _node_set(vars, CFG):
    s = CFG.get("set") or dict()
    if s.get("outcome"): _outcome(vars, s.get("outcome"))
    if s.get("say"): _say(vars, _fill(s.get("say"), vars))
    vars["route"] = str(s.get("route") or "farewell")


# ---- dispatcher ---------------------------------------------------------------------------------------------------------------

def _run_node(mode, vars, CFG):
    fn = dict()
    fn["opening_tally"] = _node_opening_tally; fn["identity_prep"] = _node_identity_prep; fn["identity_eval"] = _node_identity_eval
    fn["identity_after"] = _node_identity_after; fn["tp_prep"] = _node_tp_prep; fn["tp_eval"] = _node_tp_eval
    fn["product_facts"] = _node_product_facts; fn["eval"] = _node_eval; fn["eval_hardship"] = _node_eval_hardship
    fn["eval_human"] = _node_eval_human; fn["eval_confirm"] = _node_eval_confirm; fn["after_record"] = _node_after_record
    fn["notes_plan"] = _node_notes_plan; fn["set"] = _node_set
    f = fn.get(mode)
    if f is None:
        vars["route"] = "farewell"; return
    f(vars, CFG)
