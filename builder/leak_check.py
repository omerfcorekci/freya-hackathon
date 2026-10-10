"""Leak check for the final window: nothing from a hidden brief may be written into the builder.

    python3 builder/leak_check.py <base_commit> briefs/hidden-1.md briefs/hidden-2.md

Takes every distinctive token of the hidden briefs (dates, numbers with units, snake_case codes, quoted sentences) and
reports any that appears in the code changed since <base_commit>. Brief files, out/, submission/ and traces/ are not code.
"""
import os, re, subprocess, sys

CODE_DIRS = ("builder/", ".claude/", "README.md", "CLAUDE.md", "SUBMISSION.md", "HACKATHON.md")


def tokens(text):
    out = set()
    out |= set(re.findall(r"\b\d{4}-\d{2}-\d{2}\b", text))
    out |= set(re.findall(r"\b[a-z]+_[a-z_]+\b", text))
    out |= set(m.strip() for m in re.findall(r'"([^"]{12,})"', text))
    out |= set(re.findall(r"\b\d{1,3}(?:[.,]\d{1,2})?\s*(?:dollars|euros|pounds|%|percent)\b", text, flags=re.I))
    return {t for t in out if t and t.lower() not in COMMON}


COMMON = {"customer_id", "first_name", "last_name", "product_id", "verify_identity", "get_account", "create_promise", "add_note",
          "schedule_callback", "transfer_to_agent", "close_call", "days_late", "past_due", "card_last4", "date_of_birth", "phone_last4",
          "minimum_payment", "instalment_amount", "all_verified", "wrong_answers_left", "promise_id", "credit_card", "personal_loan", "car_loan",
          "service_error", "not_reached", "not_verified", "no_promise", "day_month_swapped", "business_days_after_today", "calendar_days_after_today"}


def main():
    base = sys.argv[1]; briefs = sys.argv[2:]
    text = "\n".join(open(b, encoding="utf-8").read() for b in briefs)
    toks = tokens(text)
    diff = subprocess.run(["git", "diff", base, "--", *CODE_DIRS], capture_output=True, text=True).stdout
    added = "\n".join(l[1:] for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++"))
    hits = sorted(t for t in toks if t in added)
    print(f"{len(toks)} distinctive tokens from {len(briefs)} brief(s); {len(added.splitlines())} added code lines since {base}")
    for h in hits: print("LEAK?", h)
    print("clean" if not hits else f"{len(hits)} suspicious tokens, review each")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
