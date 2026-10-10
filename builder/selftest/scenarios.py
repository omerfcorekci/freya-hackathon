"""Chat scenarios generated from the spec: scripted customer lines against the agent's deterministic sentences.

A scenario is a list of customer turns plus checks on the tool calls, the ledger (when a practice session exists) and
the transcript. The first turn is a throwaway greeting: on the chat route the engine does not evaluate transitions on
the very first message of a call (observed on 10 October), so the real conversation starts at the second message.
"""
import datetime

from builder.spec_schema import get


def _next_bd(today, cal):
    d = today + datetime.timedelta(days=1)
    while d.weekday() not in cal["business_weekdays"] or d.isoformat() in cal["holidays"]: d += datetime.timedelta(days=1)
    return d


def generate(spec, cfg, session=None):
    """session: practice-case variables and identity answers {variables:{...}, identity:{field: answer}}, or None."""
    cal = cfg["calendar"]; out = []
    forbidden = [w for w in (get(spec, "opening.forbidden_before_verification", []) or []) if len(str(w)) > 3 and str(w) != "the product"]
    ident = (session or {}).get("identity") or {}
    answers = [str(ident.get(q.get("field"), "")) for q in (get(spec, "identity.questions", []) or [])]
    have_ident = bool(answers) and all(answers)
    now_default = ((session or {}).get("variables") or {}).get(cfg["now_var"]) or "2026-01-14T11:00"
    robot = str(get(spec, "opening.robot_reply", ""))[:25]

    if session and have_ident:
        out.append({"name": "happy_path_today", "turns": ["Hello?", "Yes, that's me.", *answers, "Yes, I can pay the full amount today.", "Yes, I confirm.", "Thank you, goodbye."],
                    "expect_tools": ["verify_identity"] * len(answers) + ["get_account", "create_promise", "close_call"],
                    "expect_ledger": {"outcome": get(spec, "closing.any_promise_outcome", "promise"), "promises": 1},
                    "forbid_before": {"tool": "get_account", "words": forbidden},
                    "must_say": [s for s in (get(spec, "confirmation.after_recorded_sentences", []) or [])]})
        out.append({"name": "robot_question_then_wrong_answers", "turns": ["Hello?", "Am I talking to a robot?", "Yes, speaking.", "1 January 1900", "1 January 1900", "1 January 1900", "Goodbye."],
                    "expect_tools": ["verify_identity", "verify_identity", "verify_identity", "close_call"],
                    "expect_ledger": {"outcome": get(spec, "identity.failed.outcome.outcome", "not_verified"), "reason": get(spec, "identity.failed.outcome.reason", "")},
                    "must_say": [robot, str(get(spec, "identity.failed.say", ""))[:30]], "forbid_before": {"tool": "close_call", "words": forbidden}})
    # third party: a time inside the window on the next business day
    cb = get(spec, "third_party.callback", {}) or {}
    if cb.get("enabled", True):
        today = datetime.date.fromisoformat(str(now_default)[:10]); nb = _next_bd(today, cal)
        ws = str(cb.get("window_start") or "10:00"); hh = int(ws.split(":")[0]) + 1
        out.append({"name": "third_party_callback", "turns": ["Hello?", "No, this is her husband. What is this about?", f"She will be back tomorrow around {hh} in the morning.", "Okay, goodbye."],
                    "expect_tools": ["schedule_callback", "close_call"],
                    "expect_ledger": {"outcome": get(spec, "third_party.callback.scheduled.outcome", "not_reached"), "reason": get(spec, "third_party.callback.scheduled.reason", ""),
                                      "callback": {"date": nb.isoformat(), "time": "%02d:00" % hh}},
                    "forbid_before": {"tool": "close_call", "words": forbidden + ["past due", "owe"]}})
    return out
