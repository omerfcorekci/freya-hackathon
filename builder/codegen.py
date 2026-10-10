"""Sources for code nodes and tool hooks. Everything is assembled from the date library, the node logic and the CFG."""
import ast, json, os

from builder import datefacts

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _strip_docstrings(src):
    """Smaller code nodes: drop docstrings and comments, keep the logic identical."""
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef, ast.Module)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(getattr(first, "value", None), ast.Constant) and isinstance(first.value.value, str):
                node.body = node.body[1:] or [ast.Pass()]
    return ast.unparse(tree)


_NODE_SRC = open(os.path.join(ROOT, "builder", "nodecode.py"), encoding="utf-8").read()
LIB_MIN = _strip_docstrings(datefacts.LIB_SOURCE)
NODE_MIN = _strip_docstrings(_NODE_SRC)
datefacts.assert_sandbox_safe(LIB_MIN); datefacts.assert_sandbox_safe(NODE_MIN)

RUNNER = """
try:
    _run_node(MODE, vars, CFG)
except Exception as _e:
    vars['node_error'] = (str(MODE) + ': ' + str(_e))[:300]
    if not vars.get('route'):
        vars['route'] = 'farewell'
"""


# ---- tree shaking: a code node carries only the functions its mode reaches ---------------------------------------

def _toplevel_index(src):
    tree = ast.parse(src)
    defs, others = {}, []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)): defs[node.name] = node
        else: others.append(node)
    return defs, others

_DEFS, _OTHERS = {}, []
for _src in (LIB_MIN, NODE_MIN):
    d, o = _toplevel_index(_src); _DEFS.update(d); _OTHERS.extend(o)

def _refs(node):
    out = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name): out.add(n.id)
    return out

def _closure(roots):
    seen, stack = set(), list(roots)
    while stack:
        name = stack.pop()
        if name in seen or name not in _DEFS: continue
        seen.add(name); stack.extend(_refs(_DEFS[name]))
    return seen

def _shaken_source(mode):
    keep = _closure(["_node_" + mode])
    body = [n for n in _OTHERS]                       # imports, constants, small classes: always kept
    body += [_DEFS[name] for name in _DEFS if name in keep]
    mod = ast.Module(body=body, type_ignores=[])
    return ast.unparse(mod)

_SHAKEN = {}

def code_source(mode, cfg, extra=None):
    if mode not in _SHAKEN: _SHAKEN[mode] = _shaken_source(mode)
    c = dict(cfg)
    if extra: c.update(extra)
    rendered = datefacts.render_cfg(c)
    src = (_SHAKEN[mode] + "\nMODE = " + repr(mode) + "\nCFG = json.loads(" + repr(rendered) + ")\n" +
           RUNNER.replace("_run_node(MODE, vars, CFG)", "_node_" + mode + "(vars, CFG)"))
    datefacts.assert_sandbox_safe(src)
    return src


# ---- hooks (self-contained: no library available inside a hook) -----------------------------------------------------

def verify_pre_hook(cfg):
    roles = cfg["roles"]; spec = cfg["spec"]
    qs = [{"field": q.get("field"), "fmt": q.get("answer_format") or "text", "n": int(q.get("digits_len") or 0), "order": q.get("numeric_order") or "dmy"}
          for q in (spec.get("identity") or {}).get("questions") or []]
    conf = {"field_param": roles["vi_field"], "answer_param": roles["vi_answer"], "questions": qs}
    return ("import re, json\n"
            "C = json.loads(" + repr(datefacts.render_cfg(conf)) + ")\n"
            "MONTHS = dict(jan=1, feb=2, mar=3, apr=4, may=5, jun=6, jul=7, aug=8, sep=9, oct=10, nov=11, dec=12)\n"
            "def _dob(s, order):\n"
            "    s = str(s or '').strip().lower()\n"
            "    m = re.search(r'(\\d{4})-(\\d{1,2})-(\\d{1,2})', s)\n"
            "    if m: return '%04d-%02d-%02d' % (int(m.group(1)), int(m.group(2)), int(m.group(3)))\n"
            "    m = re.search(r'(\\d{1,2})(?:st|nd|rd|th)?\\s+(?:of\\s+)?([a-z]+)\\.?,?\\s+(\\d{4})', s)\n"
            "    if m and m.group(2)[:3] in MONTHS: return '%04d-%02d-%02d' % (int(m.group(3)), MONTHS[m.group(2)[:3]], int(m.group(1)))\n"
            "    m = re.search(r'([a-z]+)\\.?\\s+(\\d{1,2})(?:st|nd|rd|th)?,?\\s+(\\d{4})', s)\n"
            "    if m and m.group(1)[:3] in MONTHS: return '%04d-%02d-%02d' % (int(m.group(3)), MONTHS[m.group(1)[:3]], int(m.group(2)))\n"
            "    m = re.search(r'(\\d{1,2})[./\\s-](\\d{1,2})[./\\s-](\\d{4})', s)\n"
            "    if m:\n"
            "        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))\n"
            "        d, mo = (a, b) if order != 'mdy' else (b, a)\n"
            "        return '%04d-%02d-%02d' % (y, mo, d)\n"
            "    m = re.search(r'(\\d{4})[./\\s-](\\d{1,2})[./\\s-](\\d{1,2})', s)\n"
            "    if m: return '%04d-%02d-%02d' % (int(m.group(1)), int(m.group(2)), int(m.group(3)))\n"
            "    return str(s)\n"
            "try:\n"
            "    body = config.get('body') if isinstance(config, dict) else None\n"
            "    if isinstance(body, dict):\n"
            "        fp = C['field_param']; ap = C['answer_param']\n"
            "        nxt = str(vars.get('id_next_field') or '')\n"
            "        if nxt: body[fp] = nxt\n"
            "        q = None\n"
            "        for x in C['questions']:\n"
            "            if x['field'] == body.get(fp): q = x\n"
            "        ans = str(body.get(ap) or '')\n"
            "        if q:\n"
            "            if q['fmt'] == 'date_ymd': ans = _dob(ans, q['order'])\n"
            "            elif q['fmt'] == 'digits':\n"
            "                digits = re.sub(r'\\D', '', ans)\n"
            "                if q['n'] and len(digits) >= q['n']: digits = digits[-q['n']:]\n"
            "                ans = digits or ans\n"
            "            elif q['fmt'] == 'year':\n"
            "                m = re.search(r'\\d{4}', ans); ans = m.group(0) if m else ans\n"
            "            elif q['fmt'] == 'alnum': ans = re.sub(r'[^A-Za-z0-9]', '', ans).upper()\n"
            "        body[ap] = ans\n"
            "        vars['id_last_answer'] = ans\n"
            "except Exception:\n"
            "    pass\n")


def verify_post_hook(cfg):
    spec = cfg["spec"]; ident = spec.get("identity") or {}
    qs = [{"field": q.get("field"), "ask": q.get("ask") or "the security answer"} for q in ident.get("questions") or []]
    hints = {}
    for q in ident.get("questions") or []:
        for hv, h in (q.get("hints") or {}).items(): hints[str(hv)] = {"say": (h or {}).get("say") or "Ask them to repeat the answer.", "wrong": bool((h or {}).get("counts_as_wrong"))}
    conf = {"questions": qs, "hints": hints, "max_wrong": int(ident.get("max_wrong_total") or 3), "failed_say": (ident.get("failed") or {}).get("say") or ""}
    return ("import json\n"
            "C = json.loads(" + repr(datefacts.render_cfg(conf)) + ")\n"
            "def _truthy(x): return str(x).lower() == 'true'\n"
            "try:\n"
            "    if isinstance(result, dict):\n"
            "        result.pop('header', None)\n"
            "        d = result.get('data') if isinstance(result.get('data'), dict) else None\n"
            "        qs = C['questions']; done = [x for x in str(vars.get('id_done') or '').split(',') if x]\n"
            "        cur = str(vars.get('id_next_field') or (qs[0]['field'] if qs else ''))\n"
            "        ask_cur = ''\n"
            "        for q in qs:\n"
            "            if q['field'] == cur: ask_cur = q['ask']\n"
            "        msg = ''; state = 'continue'\n"
            "        if d is None:\n"
            "            msg = 'The check service did not answer. Ask the same question again: ' + ask_cur + '.'\n"
            "        else:\n"
            "            hint = str(d.get('hint') or '')\n"
            "            if hint and hint in C['hints']:\n"
            "                msg = C['hints'][hint]['say'] + ' Then ask the question again: ' + ask_cur + '. This does not count as a wrong answer.'\n"
            "                if C['hints'][hint]['wrong']: vars['id_wrong'] = int(vars.get('id_wrong') or 0) + 1\n"
            "            elif not _truthy(d.get('ok')):\n"
            "                msg = 'The answer could not be read (' + str(d.get('error') or 'unreadable') + '). Ask the customer to repeat ' + ask_cur + ' clearly.'\n"
            "            elif _truthy(d.get('verified')):\n"
            "                if cur and cur not in done: done.append(cur)\n"
            "                vars['id_done'] = ','.join(done)\n"
            "                nxt = ''\n"
            "                for q in qs:\n"
            "                    if q['field'] not in done and not nxt: nxt = q['field']\n"
            "                if _truthy(d.get('all_verified')) or not nxt:\n"
            "                    state = 'verified'; vars['id_next_field'] = ''\n"
            "                    msg = 'All security answers are correct. Say thank you, that is verified. Do not ask anything else in this turn.'\n"
            "                else:\n"
            "                    vars['id_next_field'] = nxt\n"
            "                    nask = ''\n"
            "                    for q in qs:\n"
            "                        if q['field'] == nxt: nask = q['ask']\n"
            "                    msg = 'Correct. Now ask for ' + nask + '.'\n"
            "            else:\n"
            "                wrong = int(vars.get('id_wrong') or 0) + 1; vars['id_wrong'] = wrong\n"
            "                left = d.get('wrong_answers_left')\n"
            "                try: left = int(left)\n"
            "                except Exception: left = C['max_wrong'] - wrong\n"
            "                if left <= 0 or wrong >= C['max_wrong']:\n"
            "                    state = 'failed'\n"
            "                    msg = 'That is the last allowed wrong answer; the check has failed. Do not state any debt. Say: ' + C['failed_say'] + ' Then thank them and say goodbye.'\n"
            "                else:\n"
            "                    msg = 'Wrong answer (' + str(left) + ' attempts left). Say it does not match and ask the same question again: ' + ask_cur + '.'\n"
            "            d['what_to_do_next'] = msg\n"
            "        vars['id_state'] = state\n"
            "        vars['id_last_msg'] = msg\n"
            "except Exception:\n"
            "    pass\n")


def close_pre_hook(cfg):
    conf = {"reason_param": cfg["roles"]["reason"], "outcome_param": cfg["roles"]["outcome"], "allowed": cfg.get("close_reasons") or {}}
    return ("import json\n"
            "C = json.loads(" + repr(datefacts.render_cfg(conf)) + ")\n"
            "try:\n"
            "    b = config.get('body') if isinstance(config, dict) else None\n"
            "    if isinstance(b, dict):\n"
            "        rp = C['reason_param']; op = C['outcome_param']\n"
            "        allowed = C['allowed'].get(str(b.get(op) or ''), [])\n"
            "        r = str(b.get(rp) or '')\n"
            "        if not r or (allowed and r not in allowed) or (not allowed and str(b.get(op) or '') in C['allowed']):\n"
            "            b.pop(rp, None)\n"
            "except Exception:\n"
            "    pass\n")


def header_post_hook():
    return ("try:\n"
            "    if isinstance(result, dict):\n"
            "        result.pop('header', None)\n"
            "except Exception:\n"
            "    pass\n")


def drop_empty_pre_hook(fields):
    """Engine-run calls: drop optional body fields that are empty strings so the API does not reject them."""
    return ("try:\n"
            "    b = config.get('body') if isinstance(config, dict) else None\n"
            "    if isinstance(b, dict):\n"
            "        for f in " + repr(list(fields)) + ":\n"
            "            if f in b and (b[f] is None or str(b[f]).strip() == ''):\n"
            "                b.pop(f, None)\n"
            "except Exception:\n"
            "    pass\n")
