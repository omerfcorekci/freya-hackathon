"""The spec: a fixed, brief-independent vocabulary that one model call fills from the bank's brief.

Everything the compiler needs is a key here. Values come from the brief; the compiler never holds a brief value.
`SPEC_SCHEMA` is a JSON Schema (used as the structured-output schema of the extraction call and for validation).
`validate_spec` cross-checks the spec against the tool API's enums. `apply_defaults` fills structural defaults only.
"""
import copy, json, re


def _s(desc, enum=None):
    d = {"type": "string", "description": desc}
    if enum: d["enum"] = enum
    return d
def _b(desc): return {"type": "boolean", "description": desc}
def _i(desc): return {"type": "integer", "description": desc}
def _n(desc): return {"type": "number", "description": desc}
def _a(items, desc): return {"type": "array", "items": items, "description": desc}
def _o(props, desc="", required=None):
    d = {"type": "object", "properties": props, "description": desc}
    if required: d["required"] = required
    return d


OUTCOME = _o({"outcome": _s("The close_call outcome value, exactly as the brief and the tool API spell it."),
              "reason": _s("The close_call reason value, or an empty string when the outcome takes no reason.")},
             "How the call is closed in this situation.")

SPEC_SCHEMA = _o({
    "meta": _o({
        "bank_name": _s("The bank's name as the agent must say it."),
        "currency_word": _s("The word for the currency when amounts are spoken, e.g. 'dollars'. Empty if the brief never names one."),
        "source_quotes": {"type": "object", "additionalProperties": {"type": "string"},
                          "description": "Map from a spec key path (e.g. 'bands', 'identity.max_wrong_total') to the verbatim sentence of the brief it came from. Fill for every non-trivial value."},
        "notes": _s("Rules in the brief that no key below can express, quoted verbatim, separated by newlines. Empty if none."),
    }, "About the brief."),
    "call_variables": _o({
        "customer_id": _s("Name of the call variable that identifies the customer for every tool call. Usually 'customer_id'."),
        "now": _s("Name of the call variable that holds the call's date and time. Usually 'now'."),
        "others": _a(_s(""), "Names of the other call variables the brief lists (e.g. first_name, last_name, title, company_name)."),
    }, "The variables every call starts with."),
    "customer_kind": _s("'person' for a private customer, 'business' for a company.", ["person", "business"]),
    "opening": _o({
        "sentence": _s("The first sentence the agent must say, verbatim or near-verbatim, with {{variable}} placeholders where the brief uses call variables."),
        "ask_for_customer": _s("The question that asks whether the right person is on the line, with {{variable}} placeholders, e.g. 'Am I speaking with {{title}} {{last_name}}?'"),
        "confirmation_counts_as": _a(_s(""), "Replies that count as confirmation of identity on the line."),
        "not_confirmation": _a(_s(""), "Replies that do not count."),
        "max_asks": _i("How many times the question may be asked in total before closing as unclear."),
        "unclear": OUTCOME,
        "forbidden_before_verification": _a(_s(""), "Words or topics that must not be said before identity is verified."),
        "robot_reply": _s("What to say when asked whether it is a robot or an AI."),
        "answer_questions_first": _b("Whether a customer question must be answered before the identity question is repeated."),
    }, "Opening of the call and finding out who is on the line."),
    "third_party": _o({
        "enabled": _b("Whether the brief has rules for someone else answering."),
        "say_only_opening": _b("Say nothing beyond the opening sentence to a third party."),
        "ask_when_reachable": _b("Ask when the customer can be reached."),
        "callback": _o({
            "enabled": _b(""),
            "days_kind": _s("Which days a callback may be booked on.", ["today_only", "today_or_next_business_day", "within_n_business_days", "within_n_calendar_days", "custom"]),
            "days_n": _i("N for the within_n kinds, else 0."),
            "days_text": _s("The brief's own words for the allowed days, used when days_kind is custom."),
            "window_start": _s("Earliest callback time, HH:MM."),
            "window_end": _s("Latest callback time, HH:MM."),
            "inclusive": _b("Whether the window ends are included."),
            "after_now": _b("Whether the callback must be later than the call's own time."),
            "retries_if_outside": _i("How many times to ask for another time when the offered one is outside the window."),
            "scheduled": OUTCOME,
            "not_scheduled": OUTCOME,
        }, "Booking a callback."),
        "wrong_number": _o({"enabled": _b(""), "outcome": OUTCOME}, "The number does not belong to the customer."),
        "deceased": _o({"enabled": _b(""), "sentence": _s("The exact sentence to say."), "ask_nothing_else": _b(""), "outcome": OUTCOME}, "The customer has died."),
        "relative_may_not_pay_or_answer": _b("A relative may not answer security questions or be told about the account."),
    }, "Someone else answers the phone."),
    "identity": _o({
        "questions": _a(_o({
            "field": _s("The verify_identity field value for this question, exactly as the tool API spells it."),
            "ask": _s("What to ask for, e.g. 'your date of birth'."),
            "answer_format": _s("How the answer must be sent to the tool.", ["date_ymd", "digits", "year", "alnum", "text"]),
            "digits_len": _i("Number of digits for the digits format, else 0."),
            "numeric_order": _s("How an all-numbers date is read: day-month-year, month-day-year or year-month-day.", ["dmy", "mdy", "ymd"]),
            "hints": {"type": "object", "additionalProperties": _o({"say": _s("What to say when the tool returns this hint."), "counts_as_wrong": _b("")}),
                      "description": "Map from a hint value the tool can return (e.g. 'day_month_swapped') to what to do."},
        }), "The security questions in the order they are asked."),
        "one_at_a_time": _b(""),
        "max_wrong_total": _i("Total wrong answers that end the check."),
        "retry_same_question": _b("A wrong answer may be asked again."),
        "failed": _o({"say": _s("What to tell the customer after the check failed."), "outcome": OUTCOME}, ""),
        "declined": _o({"explain_once": _s("The explanation given once when the customer does not want to answer."),
                        "also_counts": _a(_s(""), "Other behaviours that count as declining, e.g. asking what the call is about."),
                        "max_refusals": _i("How many refusals close the call."), "outcome": OUTCOME}, ""),
        "no_debt_before_verified": _b(""),
    }, "Identity check."),
    "debt_statement": _o({
        "intro": _s("What to say once verified, e.g. that the call is from the collections team about a late payment."),
        "product_wording": {"type": "object", "additionalProperties": {"type": "string"},
                            "description": "Map from product type value (as the tool API spells it) to how it is named in words, with {field} placeholders for product fields, e.g. 'credit card ending {card_last4}'."},
        "mention": _a(_s(""), "Product fields to state, e.g. past_due, days_late."),
        "one_sentence_each": _b(""),
        "state_all_before_asking": _b("With several products, state every one before asking for anything."),
    }, "Stating the debt."),
    "calendar": _o({
        "business_weekdays": _a(_i(""), "Weekdays that are business days, Monday=0 ... Sunday=6."),
        "holidays": _a(_s(""), "Bank holidays as YYYY-MM-DD."),
        "next_weekday_means": _s("What 'next Friday' means.", ["following_calendar_week", "next_occurrence"]),
    }, "Business days."),
    "bands": _a(_o({
        "name": _s("Band name as the brief calls it."),
        "days_late_min": _i(""), "days_late_max": _i(""),
        "deadline_kind": _s("", ["business_days_after_today", "calendar_days_after_today", "end_of_month", "fixed_date", "custom"]),
        "deadline_n": _i("N for the *_after_today kinds, else 0."),
        "deadline_text": _s("The ISO date for fixed_date, or the brief's words for custom."),
        "persuasion_attempts": _i("How many persuasion attempts this band allows."),
    }), "Lateness bands with their deadline and attempt count, in order."),
    "date_rules": _o({
        "earliest": _s("", ["today", "tomorrow", "next_business_day"]),
        "must_be_business_day": _b(""),
        "non_business_day": _s("What to do when the customer names a weekend or holiday.", ["offer_next_business_day", "offer_previous_business_day", "reject", "custom"]),
        "vague_ask_exact_once": _b("Ask once for the exact day when the customer gives a vague period."),
        "vague_then": _s("What to do when they still give none.", ["propose_deadline", "propose_next_business_day", "refuse"]),
        "after_deadline": _s("", ["offer_deadline", "refuse"]),
        "after_deadline_refusal_is_flat_refusal": _b(""),
    }, "Which payment dates are allowed."),
    "amount_rules": _o({
        "ask_full_first": _b(""),
        "never_ask_how_much": _b("The agent proposes every amount and never asks how much the customer can pay."),
        "floor_kind": _s("", ["by_product_type", "fraction_of_full", "fixed", "none", "custom"]),
        "floor_by_type": {"type": "object", "additionalProperties": {"type": "string"},
                          "description": "Map from product type to the product field that holds the minimum amount, e.g. credit_card -> minimum_payment."},
        "floor_fraction": _n("For fraction_of_full, the fraction (0.5 = half)."),
        "floor_fixed": _n("For fixed, the amount."),
        "too_much_offer_floor_once": _b(""),
        "too_much_say": _s("What to say when offering the floor, e.g. that the rest stays overdue."),
        "between_floor_and_full": _s("", ["accept", "reject"]),
        "below_floor_offer_floor_once": _b(""),
        "below_floor_say": _s("What to say when an amount below the floor cannot be recorded."),
        "refusing_floor_is_flat_refusal": _b(""),
    }, "Which amounts are allowed."),
    "persuasion": _o({
        "first_ask": _s("The first question about paying, e.g. 'Can you make this payment today?'"),
        "proposal_is_never_refusal": _b("A date or an amount the customer proposes is not a refusal."),
        "flat_refusal_definition": _s("The brief's words for what counts as a flat refusal."),
        "attempts": _a(_o({
            "n": _i("Attempt number, 1-based."),
            "amount": _s("", ["current_ask", "full", "floor"]),
            "date_kind": _s("", ["last_business_day_this_week_or_next", "next_business_day", "deadline", "today", "custom"]),
            "date_text": _s("The brief's words when date_kind is custom."),
            "bands": _a(_s(""), "Band names this attempt applies to; empty means all bands."),
        }), "What each persuasion attempt proposes."),
        "exhausted": OUTCOME,
        "never_repeat_refused_offer": _b(""),
    }, "Getting the promise."),
    "hardship": _o({
        "enabled": _b(""),
        "triggers": _a(_s(""), "What counts as hardship, e.g. illness, a death in the family, job loss."),
        "sympathy": _s("The one sentence of sympathy."),
        "no_persuasion": _b(""),
        "offer": _s("What to offer, e.g. to connect them with the customer support team."),
        "accept_queue": _s("transfer_to_agent queue when they accept."),
        "accept_outcome": OUTCOME,
        "decline_outcome": OUTCOME,
        "decline_note_reason": _s("add_note reason for a product without promise due to hardship, or empty."),
        "record_if_customer_names_date_or_amount": _b(""),
    }, "Illness, death in the family, job loss."),
    "forbidden_offers": _a(_s(""), "Things the agent must never offer, e.g. a discount, a waiver, an instalment plan."),
    "confirmation": _o({
        "read_back": _a(_s(""), "What to read back before recording, e.g. product, amount, date."),
        "question": _s("The confirmation question, e.g. 'Do you confirm?'"),
        "only_after_clear_yes": _b(""),
        "change_revalidate": _b("A change at this step is checked against the rules and read back again."),
        "one_promise_per_product": _b(""),
        "cannot_change_say": _s("What to say when the customer wants to change a recorded promise."),
        "recorded_only_after_ok": _b(""),
        "retries_on_failure": _i("How many extra attempts after a failed create_promise."),
        "failure_say": _s("What to say when the promise could not be recorded."),
        "failure_outcome": OUTCOME,
        "failure_note_reason": _s("add_note reason for a product whose promise failed, or empty."),
        "after_recorded_sentences": _a(_s(""), "Sentences that must be said after a promise is recorded, verbatim."),
        "read_all_together": _b("With several products, read all promises back together."),
        "one_confirmation": _b("One confirmation for all products."),
    }, "Confirming and recording."),
    "multi_product": _o({
        "max_products": _i("Maximum number of late products a customer can have."),
        "ask_all_today_first": _b("First ask whether they can pay all of them today."),
        "do_not_ask_today_again": _b(""),
        "attempts_per_product": _b("Persuasion attempts are counted per product."),
        "one_date_past_a_deadline": _s("", ["that_product_on_its_own_deadline", "ask_again", "reject"]),
        "notes_enabled": _b("Whether add_note is used for products without a promise."),
        "notes_reason_map": {"type": "object", "additionalProperties": {"type": "string"},
                             "description": "Map from situation (refused, hardship, dispute, paid, service_error) to the add_note reason value."},
        "notes_none_on_transfer": _b("No notes at all when the call is transferred."),
        "dispute_or_paid_does_not_end_call": _b(""),
        "restructuring_recorded_stay": _b("Promises recorded before a restructuring request stay."),
    }, "Customers with several products."),
    "situations": _o({
        "already_paid": _o({"say": _s(""), "outcome": OUTCOME, "note_reason": _s("")}, ""),
        "dispute": _o({"do_not_argue": _b(""), "includes": _a(_s(""), "What counts as a dispute."), "outcome": OUTCOME, "note_reason": _s("")}, ""),
        "plan_request": _o({"do_not_describe": _b(""), "queue": _s("transfer_to_agent queue."), "outcome": OUTCOME}, "A request for a new payment plan or lower instalments."),
        "human_request": _o({"ask_can_i_help_first": _i("How many times to ask whether you can help first."), "queue": _s(""), "outcome": OUTCOME}, "A request for a human."),
        "scam_question": _o({"say": _s("")}, ""),
        "unknown_question": _o({"say": _s("")}, "A question the tools cannot answer."),
        "dont_want_to_talk": _o({"times": _i("How many times they must say it."), "after_verified": OUTCOME, "before_verified": OUTCOME}, ""),
        "transfer_after_promise": _s("", ["transferred_with_that_reason", "promise"]),
    }, "Other things customers say."),
    "closing": _o({
        "outcomes": _a(_o({"outcome": _s(""), "reasons": _a(_s(""), "Allowed reasons for this outcome; empty when it takes none.")}), "The outcome table of the brief."),
        "any_promise_outcome": _s("Outcome when at least one promise was recorded."),
        "all_paid_outcome": _s("Outcome when every product was already paid and nothing was recorded."),
        "else_rule": _s("", ["first_non_paid_note_reason", "refused"]),
        "goodbye_before_close": _b("Thank the customer and say goodbye before close_call."),
        "farewell_text": _s("The farewell sentence if the brief gives one, else empty."),
    }, "Closing the call."),
    "mandatory_sentences": _a(_o({
        "when": _s("", ["after_promise_recorded", "deceased", "hardship", "already_paid", "opening", "closing", "custom"]),
        "when_text": _s("The situation in the brief's words when 'when' is custom."),
        "text": _s("The sentence, verbatim."),
    }), "Sentences the brief requires verbatim."),
}, "A bank's collections-call brief as structured data.")


# Keys that must be filled from the brief. Missing -> one repair call, then a warning in the trace.
REQUIRED = [
    "meta.bank_name", "opening.sentence", "opening.ask_for_customer", "opening.unclear.outcome", "opening.robot_reply",
    "identity.questions", "identity.max_wrong_total", "identity.failed.outcome", "identity.declined.outcome",
    "debt_statement.intro", "calendar.holidays", "bands", "persuasion.first_ask", "persuasion.exhausted.outcome",
    "confirmation.question", "confirmation.after_recorded_sentences", "closing.outcomes",
]

# Structural defaults. Brief-specific values are never defaulted silently; they go to the trace as warnings.
STRUCTURAL_DEFAULTS = {
    "call_variables.customer_id": "customer_id", "call_variables.now": "now", "customer_kind": "person",
    "opening.max_asks": 2, "opening.answer_questions_first": True,
    "third_party.callback.retries_if_outside": 1, "third_party.callback.inclusive": True, "third_party.callback.after_now": True,
    "identity.one_at_a_time": True, "identity.retry_same_question": True, "identity.declined.max_refusals": 2, "identity.no_debt_before_verified": True,
    "debt_statement.one_sentence_each": True, "debt_statement.state_all_before_asking": True,
    "calendar.business_weekdays": [0, 1, 2, 3, 4], "calendar.next_weekday_means": "following_calendar_week",
    "date_rules.earliest": "today", "date_rules.must_be_business_day": True, "date_rules.non_business_day": "offer_next_business_day",
    "date_rules.vague_ask_exact_once": True, "date_rules.vague_then": "propose_deadline", "date_rules.after_deadline": "offer_deadline",
    "date_rules.after_deadline_refusal_is_flat_refusal": True,
    "amount_rules.ask_full_first": True, "amount_rules.never_ask_how_much": True, "amount_rules.floor_kind": "by_product_type",
    "amount_rules.too_much_offer_floor_once": True, "amount_rules.between_floor_and_full": "accept", "amount_rules.below_floor_offer_floor_once": True,
    "amount_rules.refusing_floor_is_flat_refusal": True,
    "persuasion.proposal_is_never_refusal": True, "persuasion.never_repeat_refused_offer": True,
    "hardship.no_persuasion": True, "hardship.record_if_customer_names_date_or_amount": True,
    "confirmation.only_after_clear_yes": True, "confirmation.change_revalidate": True, "confirmation.one_promise_per_product": True,
    "confirmation.recorded_only_after_ok": True, "confirmation.retries_on_failure": 1, "confirmation.read_all_together": True, "confirmation.one_confirmation": True,
    "multi_product.max_products": 3, "multi_product.ask_all_today_first": True, "multi_product.do_not_ask_today_again": True,
    "multi_product.attempts_per_product": True, "multi_product.one_date_past_a_deadline": "that_product_on_its_own_deadline",
    "multi_product.notes_none_on_transfer": True, "multi_product.dispute_or_paid_does_not_end_call": True, "multi_product.restructuring_recorded_stay": True,
    "situations.human_request.ask_can_i_help_first": 1, "situations.dont_want_to_talk.times": 2, "situations.transfer_after_promise": "transferred_with_that_reason",
    "closing.else_rule": "first_non_paid_note_reason", "closing.goodbye_before_close": True,
}


def get(spec, path, default=None):
    cur = spec
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur: return default
        cur = cur[part]
    return cur


def put(spec, path, value):
    parts = path.split("."); cur = spec
    for part in parts[:-1]:
        if not isinstance(cur.get(part), dict): cur[part] = {}
        cur = cur[part]
    cur[parts[-1]] = value


def _empty(v):
    return v is None or v == "" or v == [] or v == {}


def apply_defaults(spec):
    """Fill structural defaults. Returns (spec, [paths that were defaulted])."""
    spec = copy.deepcopy(spec); done = []
    for path, val in STRUCTURAL_DEFAULTS.items():
        if _empty(get(spec, path)):
            put(spec, path, copy.deepcopy(val)); done.append(path)
    return spec, done


def missing_required(spec):
    return [p for p in REQUIRED if _empty(get(spec, p))]


def _outcome_pairs(spec):
    """Every (outcome, reason, where) the spec uses."""
    out = []
    def walk(node, path):
        if isinstance(node, dict):
            if set(node.keys()) >= {"outcome"} and isinstance(node.get("outcome"), str) and "reasons" not in node:
                if node.get("outcome"): out.append((node["outcome"], node.get("reason") or "", path))
            for k, v in node.items(): walk(v, f"{path}.{k}" if path else k)
        elif isinstance(node, list):
            for i, v in enumerate(node): walk(v, f"{path}[{i}]")
    walk(spec, "")
    return out


def validate_spec(spec, enums):
    """Cross-check the spec against the tool API. `enums` maps 'tool.field' -> allowed values (or absent when free)."""
    problems = []
    for p in missing_required(spec): problems.append(f"required key missing or empty: {p}")
    # identity fields
    allowed_fields = enums.get("verify_identity.field")
    for i, q in enumerate(get(spec, "identity.questions", []) or []):
        if allowed_fields and q.get("field") not in allowed_fields:
            problems.append(f"identity.questions[{i}].field '{q.get('field')}' not in verify_identity.field enum {allowed_fields}")
    # outcomes and reasons
    table = {o.get("outcome"): list(o.get("reasons") or []) for o in get(spec, "closing.outcomes", []) or []}
    allowed_outcomes = enums.get("close_call.outcome")
    for o in table:
        if allowed_outcomes and o not in allowed_outcomes:
            problems.append(f"closing.outcomes outcome '{o}' not in close_call.outcome enum {allowed_outcomes}")
    for outcome, reason, where in _outcome_pairs(spec):
        if where.startswith("closing.outcomes"): continue
        if outcome not in table: problems.append(f"{where}: outcome '{outcome}' is not in closing.outcomes")
        elif reason and reason not in table[outcome]: problems.append(f"{where}: reason '{reason}' not listed for outcome '{outcome}' in closing.outcomes")
        elif not reason and table[outcome]: problems.append(f"{where}: outcome '{outcome}' needs a reason, one of {table[outcome]}")
    # queues
    allowed_q = enums.get("transfer_to_agent.queue")
    for path in ("hardship.accept_queue", "situations.plan_request.queue", "situations.human_request.queue"):
        q = get(spec, path)
        if q and allowed_q and q not in allowed_q: problems.append(f"{path} '{q}' not in transfer_to_agent.queue enum {allowed_q}")
    # note reasons
    allowed_n = enums.get("add_note.reason")
    for path in ("hardship.decline_note_reason", "confirmation.failure_note_reason", "situations.already_paid.note_reason", "situations.dispute.note_reason"):
        r = get(spec, path)
        if r and allowed_n and r not in allowed_n: problems.append(f"{path} '{r}' not in add_note.reason enum {allowed_n}")
    for k, r in (get(spec, "multi_product.notes_reason_map", {}) or {}).items():
        if r and allowed_n and r not in allowed_n: problems.append(f"multi_product.notes_reason_map.{k} '{r}' not in add_note.reason enum {allowed_n}")
    # calendar and bands
    for h in get(spec, "calendar.holidays", []) or []:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(h)): problems.append(f"calendar.holidays entry '{h}' is not YYYY-MM-DD")
    bands = get(spec, "bands", []) or []
    for i, b in enumerate(bands):
        if b.get("deadline_kind") in ("business_days_after_today", "calendar_days_after_today") and not b.get("deadline_n"):
            problems.append(f"bands[{i}] deadline_n missing for {b.get('deadline_kind')}")
        if b.get("deadline_kind") == "fixed_date" and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(b.get("deadline_text", ""))):
            problems.append(f"bands[{i}] deadline_text must be an ISO date for fixed_date")
        if i and bands[i - 1].get("days_late_max", 0) >= b.get("days_late_min", 0):
            problems.append(f"bands[{i}] overlaps or is out of order with bands[{i-1}]")
    for i, a in enumerate(get(spec, "persuasion.attempts", []) or []):
        for bn in a.get("bands") or []:
            if bn not in [b.get("name") for b in bands]: problems.append(f"persuasion.attempts[{i}] names unknown band '{bn}'")
    for t in ("window_start", "window_end"):
        v = get(spec, f"third_party.callback.{t}")
        if get(spec, "third_party.callback.enabled") and v and not re.fullmatch(r"\d{1,2}:\d{2}", str(v)):
            problems.append(f"third_party.callback.{t} '{v}' is not HH:MM")
    return problems


def dumps(spec):
    return json.dumps(spec, indent=1, ensure_ascii=False)
