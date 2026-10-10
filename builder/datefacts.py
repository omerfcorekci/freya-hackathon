"""Date, amount and product helpers shared by the builder and the generated code nodes.

`LIB_SOURCE` is the Python source of a small library that the builder prepends to every
code node it generates. Code nodes run on Freya's server in a sandbox where only `json`,
`re` and `datetime` can be imported, the input is a dict named `vars`, and the source text
must never contain a double opening or closing curly brace (the platform reads them as
template placeholders). The library therefore:

- imports only json, re and datetime;
- defines only constants, functions and one tiny dict subclass, all named with a leading `_`;
- never raises: bad input gives None, '' or an empty list;
- is checked by `assert_sandbox_safe` when this module is imported.

The same source is executed locally by `lib_namespace()` and `sandbox_exec()` so the
offline tests exercise exactly the code that runs on the platform.

The library reads its settings from a config dict `cfg`:
    business_weekdays   list of ints, Monday=0 (default [0, 1, 2, 3, 4])
    holidays            list of ISO dates 'YYYY-MM-DD'
    next_weekday_means  'following_calendar_week' or 'next_occurrence'
    currency_word       e.g. 'dollars', may be ''
    band_fallback       'last' or 'none'
Every value comes from the brief; nothing here is specific to one bank.
"""

import builtins
import json
import re
import datetime

LIB_SOURCE = r'''
import json
import re
import datetime

# ---------------------------------------------------------------- constants

_CFG_DEFAULTS = dict(
    business_weekdays=[0, 1, 2, 3, 4],
    holidays=[],
    next_weekday_means='following_calendar_week',
    currency_word='',
    band_fallback='last',
)

_WEEKDAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
_WEEKDAY_SHORT = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
_MONTHS = ['january', 'february', 'march', 'april', 'may', 'june', 'july',
           'august', 'september', 'october', 'november', 'december']
_MONTH_SHORT = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
_MONTH_ALIASES = dict(sept=9, jan=1, feb=2, mar=3, apr=4, jun=6, jul=7,
                      aug=8, sep=9, oct=10, nov=11, dec=12)

_WD_RE = r'(monday|tuesday|wednesday|thursday|friday|saturday|sunday)'
_MONTH_RE = (r'(january|february|march|april|may|june|july|august|september|october'
             r'|november|december|sept|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)')

_UNITS = dict(zero=0, oh=0, one=1, two=2, three=3, four=4, five=5, six=6, seven=7,
              eight=8, nine=9, ten=10, eleven=11, twelve=12, thirteen=13,
              fourteen=14, fifteen=15, sixteen=16, seventeen=17, eighteen=18,
              nineteen=19)
_TENS = dict(twenty=20, thirty=30, forty=40, fourty=40, fifty=50, sixty=60,
             seventy=70, eighty=80, ninety=90)
_ORDINALS = dict(first=1, second=2, third=3, fourth=4, fifth=5, sixth=6, seventh=7,
                 eighth=8, ninth=9, tenth=10, eleventh=11, twelfth=12,
                 thirteenth=13, fourteenth=14, fifteenth=15, sixteenth=16,
                 seventeenth=17, eighteenth=18, nineteenth=19, twentieth=20,
                 thirtieth=30)
_ORD_RE = (r'(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth'
           r'|eleventh|twelfth|thirteenth|fourteenth|fifteenth|sixteenth'
           r'|seventeenth|eighteenth|nineteenth|twentieth|thirtieth)')
_CARD_RE = (r'(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve'
            r'|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen'
            r'|twenty|thirty)')

# A number directly followed by one of these words is not a day of the month.
_NOT_A_DAY = (r'(?!\s*(?:am|pm|a m|p m|oclock|o clock|hours?|days?|weeks?|months?|years?'
              r'|minutes?|mins?|dollars?|euros?|pounds?|bucks|percent|cents?)\b)(?!:)')

_VAGUE_PATTERNS = [
    r'\bend of (?:the |this |next )?(?:month|week)\b',
    r'\bweek after next\b',
    r'\b(?:this|next|coming) (?:week|month)\b',
    r'\b(?:beginning|start|middle|mid|end) of\b',
    r'\bmid ?' + _MONTH_RE + r'\b',
    r'\bsalary\b',
    r'\bpay ?check\b',
    r'\bpay ?day\b',
    r'\bget(?:s|ting)? paid\b',
    r'\blater\b',
    r'\bsoon\b',
    r'\b(?:few|couple)(?: of)? (?:days|weeks)\b',
    r'\bsome ?time\b',
    r'\bweekend\b',
    r'\bin a (?:month|while)\b',
    r'\b(?:january|february|march|april|june|july|august|september|october|november|december)\b',
]


class _Blank(dict):
    # str.format_map helper: unknown template keys become ''.
    def __missing__(self, key):
        return ''


# ---------------------------------------------------------------- config and parsing

def _c(cfg, key):
    try:
        if isinstance(cfg, dict) and cfg.get(key) is not None:
            return cfg.get(key)
    except Exception:
        pass
    return _CFG_DEFAULTS.get(key)


def _parse_now(s):
    # 'YYYY-MM-DDTHH:MM[:SS]' or with a space, optional 'Z' or '+HH:MM' (ignored),
    # or a bare 'YYYY-MM-DD' (midnight). Returns a naive datetime or None.
    try:
        if isinstance(s, datetime.datetime):
            return s.replace(tzinfo=None)
        if isinstance(s, datetime.date):
            return datetime.datetime(s.year, s.month, s.day)
        m = re.match(r'^\s*(\d{4})-(\d{1,2})-(\d{1,2})'
                     r'(?:[T ](\d{1,2}):(\d{2})(?::(\d{2}))?(?:\.\d+)?)?'
                     r'\s*(?:Z|[+-]\d{2}:?\d{2})?\s*$', str(s))
        if not m:
            return None
        parts = [int(g) if g else 0 for g in m.groups()]
        return datetime.datetime(parts[0], parts[1], parts[2], parts[3], parts[4], parts[5])
    except Exception:
        return None


def _to_date(x):
    try:
        if isinstance(x, datetime.datetime):
            return x.date()
        if isinstance(x, datetime.date):
            return x
        m = re.match(r'^\s*(\d{4})-(\d{1,2})-(\d{1,2})', str(x))
        if not m:
            return None
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except Exception:
        return None


def _iso(d):
    d = _to_date(d)
    return d.isoformat() if d else None


# ---------------------------------------------------------------- business days

def _holiday_set(cfg):
    out = set()
    try:
        for h in _c(cfg, 'holidays') or []:
            d = _to_date(h)
            if d:
                out.add(d)
    except Exception:
        pass
    return out


def _weekday_set(cfg):
    try:
        return set(int(w) for w in (_c(cfg, 'business_weekdays') or []))
    except Exception:
        return set([0, 1, 2, 3, 4])


def _is_business_day(d, cfg):
    try:
        d = _to_date(d)
        if d is None:
            return False
        return d.weekday() in _weekday_set(cfg) and d not in _holiday_set(cfg)
    except Exception:
        return False


def _next_business_day(d, cfg, include_today=False):
    # The first business day after d (or d itself when include_today and d qualifies).
    try:
        d = _to_date(d)
        if d is None:
            return None
        if include_today and _is_business_day(d, cfg):
            return d
        for i in range(1, 400):
            c = d + datetime.timedelta(days=i)
            if _is_business_day(c, cfg):
                return c
    except Exception:
        pass
    return None


def _add_business_days(d, n, cfg):
    # The n-th business day strictly after d; n=0 gives d itself.
    try:
        d = _to_date(d)
        n = int(n)
        if d is None or n < 0:
            return None
        for _ in range(n):
            d = _next_business_day(d, cfg)
            if d is None:
                return None
        return d
    except Exception:
        return None


def _last_business_day_of_week(d, cfg, weeks_ahead=0):
    # Last business day of the Monday-to-Sunday week containing d, moved by weeks_ahead
    # weeks. A holiday Friday gives the Thursday.
    try:
        d = _to_date(d)
        if d is None:
            return None
        monday = d - datetime.timedelta(days=d.weekday()) + datetime.timedelta(weeks=int(weeks_ahead))
        for i in range(6, -1, -1):
            c = monday + datetime.timedelta(days=i)
            if _is_business_day(c, cfg):
                return c
    except Exception:
        pass
    return None


# ---------------------------------------------------------------- bands and deadlines

def _to_int(x):
    try:
        return int(float(str(x).strip()))
    except Exception:
        return None


def _band_for(days_late, bands, cfg=None):
    # The band with days_late_min <= days_late <= days_late_max. Otherwise the last band
    # when band_fallback is 'last' (the default), else None.
    try:
        if isinstance(bands, str):
            bands = json.loads(bands)
        bands = [b for b in (bands or []) if isinstance(b, dict)]
        if not bands:
            return None
        n = _to_int(days_late)
        if n is not None:
            for b in bands:
                lo = _to_int(b.get('days_late_min'))
                hi = _to_int(b.get('days_late_max'))
                if lo is not None and hi is not None and lo <= n <= hi:
                    return b
        if _c(cfg, 'band_fallback') == 'last':
            return bands[-1]
    except Exception:
        pass
    return None


def _deadline_for(today, band, cfg):
    try:
        today = _to_date(today)
        if today is None or not isinstance(band, dict):
            return None
        kind = band.get('deadline_kind')
        n = _to_int(band.get('deadline_n'))
        if kind == 'business_days_after_today' and n is not None:
            return _iso(_add_business_days(today, n, cfg))
        if kind == 'calendar_days_after_today' and n is not None:
            return _iso(_next_business_day(today + datetime.timedelta(days=n), cfg, True))
        if kind == 'end_of_month':
            first_next = (today.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
            d = first_next - datetime.timedelta(days=1)
            while d >= today.replace(day=1):
                if _is_business_day(d, cfg):
                    return d.isoformat()
                d = d - datetime.timedelta(days=1)
            return None
        if kind == 'fixed_date':
            return _iso(band.get('deadline_text'))
    except Exception:
        pass
    return None


def _resolve_offer_date(kind, today, deadline_iso, cfg):
    try:
        today = _to_date(today)
        if today is None:
            return None
        if kind == 'today':
            return today.isoformat()
        if kind == 'next_business_day':
            return _iso(_next_business_day(today, cfg))
        if kind == 'deadline':
            return _iso(deadline_iso)
        if kind == 'last_business_day_this_week_or_next':
            d = _last_business_day_of_week(today, cfg)
            if d is None or d <= today:
                d = _last_business_day_of_week(today, cfg, 1)
            return _iso(d)
    except Exception:
        pass
    return None


# ---------------------------------------------------------------- date expressions

def _month_num(word):
    try:
        w = str(word).lower()
        if w in _MONTHS:
            return _MONTHS.index(w) + 1
        return _MONTH_ALIASES.get(w)
    except Exception:
        return None


def _date_words_to_digits(t):
    # 'the twenty-sixth' -> 'the 26th', 'in two weeks' -> 'in 2 weeks'. A plain ordinal
    # word is converted only next to 'the', 'on', 'of', a weekday or a month, so that
    # 'just a second' does not become a day of the month.
    t = re.sub(r'\bfirst thing\b', 'early', t)
    t = re.sub(r'\b(twenty|thirty) ' + _ORD_RE + r'\b',
               lambda m: str(_TENS[m.group(1)] + _ORDINALS[m.group(2)]) + 'th', t)
    t = re.sub(r'\b(the|on|' + _WD_RE[1:-1] + '|' + _MONTH_RE[1:-1] + r') ' + _ORD_RE + r'\b',
               lambda m: m.group(1) + ' ' + str(_ORDINALS[m.group(2)]) + 'th', t)
    t = re.sub(r'\b' + _ORD_RE + r' (of|' + _MONTH_RE[1:-1] + r')\b',
               lambda m: str(_ORDINALS[m.group(1)]) + 'th ' + m.group(2), t)
    t = re.sub(r'\b(twenty|thirty) (one|two|three|four|five|six|seven|eight|nine)\b',
               lambda m: str(_TENS[m.group(1)] + _UNITS[m.group(2)]), t)
    t = re.sub(r'\b' + _CARD_RE + r'\b',
               lambda m: str(_UNITS.get(m.group(1), _TENS.get(m.group(1)))), t)
    return t


def _make_date(y, m, d):
    try:
        return datetime.date(int(y), int(m), int(d))
    except Exception:
        return None


def _day_of_month(day, weekday, today):
    # 'the 26th': this month if not already past, else the next month that has that day.
    # When a weekday is named too ('Monday the 26th'), prefer the month where it matches.
    cands = []
    y, m = today.year, today.month
    for _ in range(3):
        d = _make_date(y, m, day)
        if d is not None and d >= today:
            cands.append(d)
        m += 1
        if m > 12:
            m, y = 1, y + 1
    if not cands:
        return None
    if weekday is not None:
        for d in cands:
            if d.weekday() == weekday:
                return d
    return cands[0]


def _resolve_date_expr(text, now, cfg):
    # Returns ('date', 'YYYY-MM-DD'), ('vague', normalised text) or ('none', '').
    # An explicit date anywhere in the sentence wins over a vague phrase.
    try:
        now = _parse_now(now)
        if now is None or text is None:
            return ('none', '')
        today = now.date()
        raw = str(text).lower()
        m = re.search(r'\b(\d{4})-(\d{1,2})-(\d{1,2})\b', raw)
        if m:
            d = _make_date(m.group(1), m.group(2), m.group(3))
            if d is not None:
                return ('date', d.isoformat())
        t = re.sub(r'(?<=[a-z])-(?=[a-z])', ' ', raw)
        t = t.replace("o'clock", 'oclock')
        t = re.sub(r'[^a-z0-9: ]', ' ', t)
        t = re.sub(r'\s+', ' ', t).strip()
        norm = t
        t = ' ' + _date_words_to_digits(t) + ' '

        # 1. Day and month: '26 October', '26th of October 2026', 'October 26th', 'Oct 26'.
        best = None
        for pat, di, mi, yi in (
            (r'\b(\d{1,2})(?:st|nd|rd|th)?(?: of)? ' + _MONTH_RE + r'\b(?: (\d{4})\b)?', 1, 2, 3),
            (r'\b' + _MONTH_RE + r' (?:the )?(\d{1,2})(?:st|nd|rd|th)?\b' + _NOT_A_DAY
             + r'(?: (\d{4})\b)?', 2, 1, 3),
        ):
            m = re.search(pat, t)
            if m and (best is None or m.start() < best[0].start()):
                best = (m, di, mi, yi)
        if best:
            m, di, mi, yi = best
            month = _month_num(m.group(mi))
            day = int(m.group(di))
            if m.group(yi):
                d = _make_date(m.group(yi), month, day)
            else:
                d = _make_date(today.year, month, day)
                if d is not None and d < today:
                    d = _make_date(today.year + 1, month, day)
            if d is not None:
                return ('date', d.isoformat())

        # 2. Day of the month: 'the 26th', '23rd', 'Monday the 26th', 'Friday 16'.
        for pat in (r'\b(?:' + _WD_RE + r' )?(?:the )?(\d{1,2})(?:st|nd|rd|th)\b',
                    r'\b' + _WD_RE + r' (?:the )?(\d{1,2})\b' + _NOT_A_DAY + r'(?! \d)',
                    r'\b()the (\d{1,2})\b' + _NOT_A_DAY + r'(?! \d)'):
            m = re.search(pat, t)
            if m:
                wd = _WEEKDAYS.index(m.group(1)) if m.group(1) else None
                d = _day_of_month(int(m.group(2)), wd, today)
                if d is not None:
                    return ('date', d.isoformat())

        # 3. Relative days.
        if re.search(r'\bday after tomorrow\b', t):
            return ('date', (today + datetime.timedelta(days=2)).isoformat())
        if re.search(r'\btomorrow\b', t):
            return ('date', (today + datetime.timedelta(days=1)).isoformat())
        if re.search(r'\b(?:today|tonight)\b', t):
            return ('date', today.isoformat())
        m = re.search(r'\bin (\d+|a|an) (days?|weeks?|fortnight)\b', t)
        if m:
            n = 1 if m.group(1) in ('a', 'an') else int(m.group(1))
            unit = m.group(2)
            days = n * 14 if unit == 'fortnight' else (n * 7 if unit.startswith('week') else n)
            return ('date', (today + datetime.timedelta(days=days)).isoformat())

        # 4. Weekday names.
        monday = today - datetime.timedelta(days=today.weekday())
        m = (re.search(r'\b' + _WD_RE + r' (?:of |in )?(?:the )?next week\b', t)
             or re.search(r'\bnext week (?:on )?' + _WD_RE + r'\b', t))
        if m:
            wd = _WEEKDAYS.index(m.group(1))
            return ('date', (monday + datetime.timedelta(days=7 + wd)).isoformat())
        m = re.search(r'\b(this coming|coming|this|next)? ?' + _WD_RE + r'\b(?: (?:of )?this week\b)?', t)
        if m:
            wd = _WEEKDAYS.index(m.group(2))
            qual = m.group(1) or ''
            this_week = monday + datetime.timedelta(days=wd)
            ahead = (wd - today.weekday() - 1) % 7 + 1
            next_occ = today + datetime.timedelta(days=ahead)
            if qual == 'this' or re.search(r'\bthis week\b', m.group(0)):
                if this_week < today:
                    return ('none', '')
                return ('date', this_week.isoformat())
            if qual == 'next' and _c(cfg, 'next_weekday_means') != 'next_occurrence':
                return ('date', (this_week + datetime.timedelta(days=7)).isoformat())
            return ('date', next_occ.isoformat())

        # 5. Vague periods.
        for pat in _VAGUE_PATTERNS:
            if re.search(pat, t):
                return ('vague', norm)
    except Exception:
        pass
    return ('none', '')


# ---------------------------------------------------------------- amounts

def _words_value(tokens):
    # Value of a run of English number words, or None when it is ambiguous.
    # 'six hundred thirty seven fifty' -> 637.5 (a trailing 10..99 group after a
    # hundreds or thousands value is read as cents); 'four twenty' -> None.
    total = 0
    current = 0
    last = None          # 'unit', 'teen', 'tens', 'hundred', 'thousand'
    big = False          # saw hundred or thousand
    i = 0
    while i < len(tokens):
        w = tokens[i]
        if w == 'point':
            digits = ''
            for x in tokens[i + 1:]:
                if x in _UNITS and _UNITS[x] < 10:
                    digits += str(_UNITS[x])
                elif x in _TENS and not digits:
                    digits += str(_TENS[x])
                elif x in _UNITS and not digits:
                    digits += str(_UNITS[x])
                else:
                    return None
            if not digits or last is None:
                return None
            return float(total + current) + float('0.' + digits)
        if w in ('hundred', 'thousand'):
            if w == 'hundred':
                if last in ('hundred', 'thousand') and current == 0:
                    return None
                current = (current or 1) * 100
            else:
                total += (current or 1) * 1000
                current = 0
            last, big = w, True
            i += 1
            continue
        if w in _TENS:
            kind, val = 'tens', _TENS[w]
        elif w in _UNITS:
            kind, val = ('teen' if _UNITS[w] >= 10 else 'unit'), _UNITS[w]
        else:
            return None
        ok = (last is None or last in ('hundred', 'thousand')
              or (last == 'tens' and kind == 'unit'))
        if not ok:
            # Possible cents: the rest of the run is a 10..99 group after a big number.
            rest = tokens[i:]
            cents = None
            if big and len(rest) == 1 and kind in ('tens', 'teen'):
                cents = val
            elif big and len(rest) == 2 and kind == 'tens' and rest[1] in _UNITS and _UNITS[rest[1]] < 10:
                cents = val + _UNITS[rest[1]]
            if cents is None:
                return None
            return float(total + current) + cents / 100.0
        current += val
        last = kind
        i += 1
    if last is None:
        return None
    return float(total + current)


def _parse_amount(text):
    # First amount in the text, from digits ('1,250', '$637.50') or words
    # ('four hundred and twenty'). Ambiguous word runs give None.
    try:
        if isinstance(text, bool) or text is None:
            return None
        if isinstance(text, (int, float)):
            return float(text)
        s = str(text).lower()
        # Skip ordinals such as '23rd' (a date, not an amount).
        digit = re.search(r'(?<![\d.])(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?(?!\d)(?!\s*(?:st|nd|rd|th)\b)'
                          r'(?:\s*(k|thousand)\b)?', s)
        dval = None
        if digit:
            dval = float(digit.group(1).replace(',', ''))
            if digit.group(2):
                dval = float(digit.group(1).replace(',', '') + '.' + digit.group(2))
            if digit.group(3):
                dval = dval * 1000
        t = re.sub(r'(?<=[a-z])-(?=[a-z])', ' ', s)
        toks = [(m.group(0), m.start()) for m in re.finditer(r'[a-z]+', t)]
        words = [w for w, _ in toks]
        vocab = set(_UNITS) | set(_TENS) | set(['hundred', 'thousand'])
        vocab.discard('oh')
        wval = None
        wpos = None
        for i, w in enumerate(words):
            lead_a = w == 'a' and i + 1 < len(words) and words[i + 1] in ('hundred', 'thousand')
            if w not in vocab and not lead_a:
                continue
            run = ['one'] if lead_a else [w]
            for j in range(i + 1, len(words)):
                x = words[j]
                nxt = words[j + 1] if j + 1 < len(words) else ''
                if x in vocab or x == 'point' or (x == 'oh' and run[-1] == 'point'):
                    run.append(x)
                elif x == 'and' and nxt in vocab:
                    continue
                else:
                    break
            wval = _words_value(run)
            wpos = toks[i][1]
            break
        if digit and (wpos is None or digit.start() <= wpos):
            val = dval
        elif wpos is not None:
            val = wval
        else:
            val = dval
        # '... dollars and fifty cents'
        m = re.search(r'\b(?:dollars?|euros?|pounds?|bucks) and ([a-z ]+?|\d{1,2}) cents?\b', t)
        if val is not None and m and val == int(val):
            c = m.group(1)
            cents = int(c) if c.isdigit() else _words_value(c.split())
            if cents is not None and 0 <= cents < 100:
                val = val + cents / 100.0
        return val
    except Exception:
        return None


# ---------------------------------------------------------------- times

def _parse_time(text):
    # Returns 'HH:MM' or None.
    # Rule for a bare hour without am/pm or a part of the day: hours 8..23 are read as
    # given (8 is 08:00, 18 is 18:00) and 12 is noon; hours 1..7 are ambiguous (07:00 or
    # 19:00) and give None. 'morning'/'am' and 'afternoon'/'evening'/'night'/'pm' decide.
    try:
        s = str(text).lower()
        if re.search(r'\b(?:noon|midday|mid day)\b', s):
            return '12:00'
        if re.search(r'\bmidnight\b', s):
            return '00:00'
        s = re.sub(r'(?<=[a-z])-(?=[a-z])', ' ', s)
        s = s.replace("o'clock", ' oclock')
        # 'am' only counts right after an hour, so that 'I am free' is not a time of day.
        hour_tok = r'(?:\d|\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve))\s*'
        am = re.search(hour_tok + r'(?:am|a\.\s?m)(?![a-z])|\bmorning\b', s) is not None
        pm = re.search(hour_tok + r'(?:pm|p\.\s?m)(?![a-z])|\b(?:afternoon|evening|night|tonight)\b', s) is not None
        hour = None
        minute = 0
        explicit_24h = False
        m = re.search(r'(?<![\d-])(\d{1,2})[:.h](\d{2})(?!\d)', s)
        if m:
            hour, minute = int(m.group(1)), int(m.group(2))
            explicit_24h = m.group(1).startswith('0') or hour >= 13 or hour == 0
        if hour is None:
            for m in re.finditer(r'(?<![\d.:,-])(\d{1,2})(?![\d:.,-])(?!\s*(?:st|nd|rd|th)\b)', s):
                hour = int(m.group(1))
                break
        if hour is None:
            hw = (r'(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)')
            m = re.search(r'\b(half|quarter) (past|to) ' + hw + r'\b', s)
            if m:
                h = _UNITS[m.group(3)]
                if m.group(1) == 'half':
                    hour, minute = h, 30
                elif m.group(2) == 'past':
                    hour, minute = h, 15
                else:
                    hour, minute = h, 0
                    # 'quarter to ten': decide am/pm on the spoken hour, then step back.
                    minute = -15
            else:
                m = re.search(r'\b' + hw + r'(?: (fifteen|thirty|forty five|fourty five|forty|fifty|twenty|ten|oh five|o five))?\b', s)
                if m:
                    hour = _UNITS[m.group(1)]
                    mw = m.group(2)
                    mins = {'fifteen': 15, 'thirty': 30, 'forty five': 45, 'fourty five': 45,
                            'forty': 40, 'fifty': 50, 'twenty': 20, 'ten': 10,
                            'oh five': 5, 'o five': 5}
                    minute = mins.get(mw, 0) if mw else 0
        if hour is None or hour > 23 or minute > 59:
            return None
        if pm and not am:
            if hour < 12:
                hour += 12
        elif am and not pm:
            if hour == 12:
                hour = 0
            elif hour > 12:
                return None
        elif not explicit_24h and 1 <= hour <= 7:
            return None
        if minute < 0:
            hour, minute = (hour - 1) % 24, 60 + minute
        return '%02d:%02d' % (hour, minute)
    except Exception:
        return None


# ---------------------------------------------------------------- speaking

def _speak_date(iso):
    # '2026-10-16' -> 'Friday 16 October'.
    try:
        d = _to_date(iso)
        if d is None:
            return None
        return '%s %d %s' % (_WEEKDAYS[d.weekday()].capitalize(), d.day,
                             _MONTHS[d.month - 1].capitalize())
    except Exception:
        return None


def _speak_money(x, cfg):
    # 420 -> '420 dollars', 637.5 -> '637.50 dollars'.
    try:
        v = float(str(x).replace(',', '').strip())
        num = str(int(round(v))) if abs(v - round(v)) < 0.005 else '%.2f' % v
        word = _c(cfg, 'currency_word') or ''
        return (num + ' ' + str(word)).strip()
    except Exception:
        return ''


def _calendar_table(today, cfg, days=45):
    # One line per day from today: 'Thu 15 Oct 2026: business day'.
    try:
        today = _to_date(today)
        if today is None:
            return ''
        lines = []
        for i in range(int(days)):
            d = today + datetime.timedelta(days=i)
            if i == 0:
                label = 'today'
            elif d.weekday() not in _weekday_set(cfg):
                label = 'weekend'
            elif d in _holiday_set(cfg):
                label = 'bank holiday'
            else:
                label = 'business day'
            lines.append('%s %d %s %d: %s' % (_WEEKDAY_SHORT[d.weekday()], d.day,
                                              _MONTH_SHORT[d.month - 1], d.year, label))
        return '\n'.join(lines)
    except Exception:
        return ''


# ---------------------------------------------------------------- products

def _num(x):
    try:
        if isinstance(x, bool) or x is None:
            return None
        return float(str(x).replace(',', '').strip())
    except Exception:
        return None


def _product_floor(product, floor_cfg):
    # Lowest amount the agent may accept for one product. A floor above the full
    # past-due amount is capped at the past-due amount.
    try:
        if not isinstance(product, dict) or not isinstance(floor_cfg, dict):
            return None
        kind = floor_cfg.get('floor_kind')
        full = _num(product.get('past_due'))
        val = None
        if kind == 'by_product_type':
            field = (floor_cfg.get('floor_by_type') or dict()).get(product.get('type'))
            if field:
                val = _num(product.get(field))
        elif kind == 'fraction_of_full':
            frac = _num(floor_cfg.get('floor_fraction'))
            if frac is not None and full is not None:
                val = round(full * frac, 2)
        elif kind == 'fixed':
            val = _num(floor_cfg.get('floor_fixed'))
        if val is None:
            return None
        if full is not None and val > full:
            val = full
        return val
    except Exception:
        return None


def _product_name(product, wording):
    # Spoken name of a product from a template map, e.g. 'credit card ending {card_last4}'.
    try:
        if not isinstance(product, dict):
            return ''
        ptype = str(product.get('type') or '')
        fallback = ptype.replace('_', ' ').strip()
        tpl = wording.get(ptype) if isinstance(wording, dict) else None
        if not tpl:
            return fallback
        values = _Blank()
        for k, v in product.items():
            values[str(k)] = '' if v is None else str(v)
        out = str(tpl).format_map(values)
        return re.sub(r'\s+', ' ', out).strip() or fallback
    except Exception:
        try:
            return str(product.get('type') or '').replace('_', ' ')
        except Exception:
            return ''


def _products_from_vars(vars):
    # Products from vars['products'] (a list or a JSON string), from any '...products'
    # key holding one, or from flattened keys like
    # 'get_account_response.data.products.0.product_id' (indices 0..9).
    try:
        if not isinstance(vars, dict):
            return []
        keys = ['products'] + [k for k in vars if str(k).endswith('.products')]
        for k in keys:
            v = vars.get(k)
            if isinstance(v, str):
                try:
                    v = json.loads(v)
                except Exception:
                    v = None
            if isinstance(v, dict) and isinstance(v.get('products'), list):
                v = v.get('products')
            if isinstance(v, list):
                items = [p for p in v if isinstance(p, dict)]
                if items:
                    return items
        found = dict()
        for k, v in vars.items():
            m = re.search(r'(?:^|\.)products\.(\d)\.([A-Za-z0-9_]+)$', str(k))
            if m:
                idx = int(m.group(1))
                if idx not in found:
                    found[idx] = dict()
                found[idx][m.group(2)] = v
        return [found[i] for i in range(10) if i in found]
    except Exception:
        return []


def _num_products(vars):
    try:
        return len(_products_from_vars(vars))
    except Exception:
        return 0
'''


_ALLOWED_IMPORTS = ('json', 're', 'datetime')


def render_cfg(obj) -> str:
    """JSON text of `obj` that never contains a double curly brace."""
    text = json.dumps(obj, indent=1, ensure_ascii=True)
    while '}}' in text or '{{' in text:
        text = text.replace('}}', '} }').replace('{{', '{ {')
    return text


def assert_sandbox_safe(src: str) -> None:
    """Raise ValueError if `src` cannot run in a Freya code node."""
    for no, line in enumerate(src.splitlines(), 1):
        if '{{' in line or '}}' in line:
            raise ValueError('line %d contains a double curly brace: %r' % (no, line))
        m = re.match(r'\s*import\s+(.+)$', line)
        if m:
            names = [n.strip().split(' ')[0].split('.')[0] for n in m.group(1).split(',')]
        else:
            m = re.match(r'\s*from\s+(\S+)\s+import\b', line)
            names = [m.group(1).split('.')[0]] if m else []
        for name in names:
            if name not in _ALLOWED_IMPORTS:
                raise ValueError('line %d imports %r, only %s are allowed: %r'
                                 % (no, name, ', '.join(_ALLOWED_IMPORTS), line))
    # A brace pair split across a line break is still a placeholder.
    if '{{' in src or '}}' in src:
        raise ValueError('source contains a double curly brace across lines')


def _restricted_builtins() -> dict:
    allowed = {'json': json, 're': re, 'datetime': datetime}
    real_import = builtins.__import__

    def _import(name, globals=None, locals=None, fromlist=(), level=0):
        if name.split('.')[0] not in allowed:
            raise ImportError('module %r is not available in the code sandbox' % name)
        return real_import(name, globals, locals, fromlist, level)

    table = dict(vars(builtins))
    table['__import__'] = _import
    return table


def sandbox_exec(src: str, vars: dict) -> dict:
    """Run `src` like a Freya code node (only json, re, datetime) and return `vars`."""
    ns = {'__builtins__': _restricted_builtins(), '__name__': 'code_node',
          'json': json, 're': re, 'datetime': datetime, 'vars': vars}
    exec(compile(src, '<code_node>', 'exec'), ns)
    return ns['vars']


def lib_namespace(cfg=None) -> dict:
    """Execute LIB_SOURCE and return its namespace; `cfg` is stored under 'cfg'."""
    ns = {'__builtins__': _restricted_builtins(), '__name__': 'datefacts_lib'}
    exec(compile(LIB_SOURCE, '<datefacts_lib>', 'exec'), ns)
    if cfg is not None:
        ns['cfg'] = cfg
    return ns


assert_sandbox_safe(LIB_SOURCE)
