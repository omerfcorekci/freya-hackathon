# Build the Builder — Freya × Y Combinator Hackathon

Sources: https://www.freyavoice.ai/hackathon (fetched 10 October 2026) and kit v3
(the files at the repo root; the kit that arrived by email, byte-identical to `build-the-builder-v3.zip` on the site).
This file is our single reference for the weekend. When the rules change (new kit version, email), update it here.

## 1. In one sentence

We write a **builder**: a program that reads a bank's debt-collection brief and automatically creates a **phone agent**
(a Freya workflow). We write the builder; the organisers put the phone agent it produces in front of simulated customers
and score it. Touching the phone agent by hand is forbidden.

Three terms (the page's definitions):

| Term | What |
|---|---|
| **Phone agent** | The software that talks to the customer. A workflow on Freya: steps (nodes), prompts, tools, conditional routes. |
| **Brief** | The bank's specification: who to ask for, how to check identity, which payment dates are allowed, how to close the call. |
| **Builder** | The program we write. It reads a brief and creates the phone agent. One command, brief in, agent out. |

## 2. Timeline

| What | UTC | Turkey (UTC+3) |
|---|---|---|
| Start, kit and keys | Sat 10 Oct 10:00 | 13:00 |
| Hidden briefs open | Sun 11 Oct 17:00 | 20:00 |
| Submission closes | Sun 11 Oct 20:00 | 23:00 |
| Results | after review, on the leaderboard | |

The last 3 hours are for running the builder and fixing bugs, not for tuning it to the hidden briefs.
Online, solo or teams of two. Registration: https://events.ycombinator.com/AI-FDE-Build-the-Builder26.
The Freya account and the support channel arrive by email at the start.

## 3. Prizes

| Place | Prize |
|---|---|
| First | YC interview |
| Second | AirPods |
| Top three | Final interview with Freya |
| Pool | $3,000 in Freya credits |

## 4. How the weekend goes (the page's 7 steps)

1. Download the kit: 2 briefs, the bank's tool API, 13 practice customers, the Freya workflow reference, a small working builder.
2. Run the sample builder; it creates a phone agent on Freya in your workspace.
3. Test that phone agent: simulated customers talk to it in text; you see which cases passed and why the others failed.
4. Write your own builder and repeat 2 and 3 as often as you like.
5. On Sunday, briefs we have never seen are published. Same kind of call, different rules: other identity questions, other
   limits and deadlines, another outcome table, another calendar. **The seven tool names stay the same; their fields and allowed values can change.**
6. Run your builder once on each new brief; submit the phone agents it created, your code and the builder's trace.
7. Those phone agents are tested on customers nobody has seen. The share handled correctly is the score.

## 5. Scoring

**score = cases passed / cases run.** No partial credit.

A case (= one simulated customer) passes only when all three checks pass:

| Check | Question | Read from |
|---|---|---|
| **Outcome** | Is the ledger in the right state? Right product, date and amount, promise recorded once; right outcome/reason; right notes, callbacks, transfers. | The mock bank's ledger (they host it). What was really recorded, not what the agent said. |
| **Policy** | Did it stay inside the brief? No debt read before the identity check, no date past the deadline, etc. | A judge model reads the transcript against the case's `checks` list. |
| **Honesty** | Did it tell the customer the truth? Never says "recorded" when the tool call failed. | Judge model, transcript. |

A correct refusal passes: when the customer disputes the debt, the right outcome is a recorded dispute and no promise; an agent
that pushes for a promise anyway fails. The mock bank does not enforce the brief: it records a promise on a holiday or below the
minimum without complaint. Keeping the rules is entirely the phone agent's job.

### The final benchmark

| Item | Value |
|---|---|
| Hidden briefs | 2. One is a clean specification. The other is **raw bank material**: a mail, a policy extract, a memo that changes it, a code list. |
| Customers per brief | 30; 1 to 3 products; **on several calendar days** (`now` varies) |
| How customers talk | Like people: a number in two parts ("463..." then "51"), corrections, talk about other things, a question back, amounts and dates in words |
| Repetitions | **3 per case; all 3 must pass** |
| Score | cases passed / 60 |
| 1st tie-break | Total promised amount recorded on the cases that passed |
| 2nd tie-break | Shorter total build time (read from the traces) |
| 3rd tie-break | Earlier submission |

### Verification (anti-cheating)

- Only the phone agents are scored; rank comes from their score.
- For the top ten teams the repository is cloned at the submitted commit, the builder is rerun on the same briefs and compared with the trace.
- Every trace is read by a reviewer agent that checks it against the submitted code and the phone agent it claims to have created.
- If their run scores clearly below ours, the entry is removed. The aim is to catch hand-edited phone agents.

## 6. Rules and limits

| Rule | Detail |
|---|---|
| The builder works alone | One command, brief (+ tool API file) in, phone agent out. No edits after it runs. A hand-built phone agent is not a valid entry. |
| Nothing from a hidden brief goes into the code | No rule, no value, no name. Fixing a crash on a table the parser did not expect is allowed. Adding the new brief's holidays or outcome names to code or prompts is not. A reviewer reads the commit for this. |
| Builder run time | **30 minutes per brief**, including any test the builder runs on its own agent. It may run more than once; one run's agent is submitted with that run's trace. |
| Phone agent model | `AGENT_LLM` in `freya.py` (`experimental-5`). The same for every team. **Do not change it.** |
| Builder model | Any. We pay for the builder's own model calls. |
| Services the phone agent may call | Only the tool API from the kit. A call to any other service fails the case. Code nodes and hooks inside the workflow are allowed and expected. |
| Workflows per workspace | 200. Do not create a new one per run; update the same one in place (`freya.save_workflow(slot, ...)`). |
| Simulations | 1 at a time per workspace. A 10-case run takes 3–11 min. One workspace and one Freya key per team. |
| Platform | No probing or load-testing. |
| Data | All synthetic. No real customer data. |
| Trace | 1 trace per hidden brief, mandatory. An entry without traces is not ranked. |
| Language | Calls are in English. The phone agent gets the call's date and time as the variable `now`; every date rule uses it, never the real clock. |

## 7. Submission (before Sunday 20:00 UTC)

At 17:00 UTC on Sunday every team receives 2 hidden briefs, each with its own tool API file. The flow:

```
python3 builder/build.py briefs/hidden-1.md briefs/hidden-1.openapi.json 2>&1 | tee traces/hidden-1.log
# the same for hidden-2
# export each phone agent with freya.export_workflow(workflow_id, path) and commit the files
```

This form goes to the address in the kit email:

```json
{
  "team": "your-team-name",
  "repo": "https://github.com/you/your-builder",
  "commit": "9f2c1ab",
  "run_command": "python3 builder/build.py {brief_path} {tool_api_path}",
  "workflows": { "hidden-1": "submission/hidden-1.workflow.json", "hidden-2": "submission/hidden-2.workflow.json" },
  "traces":    { "hidden-1": "traces/hidden-1.log",               "hidden-2": "traces/hidden-2.log" }
}
```

- The exported workflow file is what gets scored: they load it into their own workspace.
- We may run the builder more than once; one phone agent per brief is submitted with that run's trace.
- The phone agent is not touched after the run.

### What the trace must contain

| In the trace | Why |
|---|---|
| Start and end time of the run | Build time tie-break |
| Every model call the builder made: which model, what it was asked for in one line | Shows how the builder works |
| What it created on Freya: workflow id, agent id, number of steps and tools | Ties the submitted phone agent to this run |
| Every test it ran on its own phone agent, with the result | "A builder that checks its own work" is the point of the exercise |

Plain text is fine, no required format. **Remove API keys before committing.** Claude Code / Codex session logs may be
shared (optional); the top three teams talk their approach through, and a log is the easiest way to show it.

## 8. Kit contents (repo root, v3)

| File | What |
|---|---|
| `README.md` | Ten-minute start, scoring, the final, rules, troubleshooting. **Read this first.** |
| `briefs/brief-a.md` | Freya Bank, customer late on one product. 47 rules. |
| `briefs/brief-b.md` | Up to three products; 11 extra rules on top of Brief A. |
| `tools/openapi.json` | The bank's 7 tools: `verify_identity`, `get_account`, `create_promise`, `add_note`, `schedule_callback`, `transfer_to_agent`, `close_call`. Mock: `https://freya-bank-mock.freyavoice.workers.dev/v1`. |
| `public-test-set.json` | 13 practice cases: who the customer is, what they do, what the ledger must show, what the judge checks. |
| `docs/workflow-format.md` | What a phone agent is made of: nodes, prompts, variables, routes, extraction, end_call. |
| `docs/tools-and-code.md` | api_call tools, parameter baking, response_mapping, code nodes, pre/post hooks, lifecycle tools. |
| `docs/api.md` | The REST calls a builder needs (workflow create/update/publish, personas, simulations, call transcript, chat/message). |
| `freya.py` | Stdlib-only Freya client: `save_workflow`, `export_workflow`, `run_simulation`, `get_call`, `AGENT_LLM`. |
| `tools/run_cases.py` | Runs the practice cases, prints PASS/FAIL and the reason per case. `--reps 3`, `--style`, `--only`, `--out`. |
| `tools/score.py` | Ledger scorer (outcome, promises, notes, callbacks, transfers, close_call last, tools used before identity). |
| `examples/base-agent.json` | Example agent with 2 steps and 4 tools. The same one that is in the workspace. Passes 2 of 13. A pattern for the JSON, not the answer. |
| `examples/agent_builder.py` | Example builder on the Claude Agent SDK with one skill. **Per the README it built an agent that passed 10/10 on Brief A.** |
| `.claude/skills/build-phone-agent/SKILL.md` | That one skill. Short on purpose; improving it is left to us. |
| `env.example` | `FREYA_API_KEY`, `FREYA_API_URL` (staging-app.freyavoice.ai), `FREYA_BANK_TEAM_KEY` (16+ characters, we make it up, always the same). |

### The ten-minute start (README)

```bash
cp env.example env.sh   # put the keys in
source env.sh
python3 -c "import freya,json; print(freya.save_workflow('base', json.load(open('examples/base-agent.json'))))"
python3 tools/run_cases.py <agent_id> --brief A          # 3–11 min
pip install claude-agent-sdk
python3 examples/agent_builder.py briefs/brief-a.md
python3 examples/agent_builder.py briefs/brief-a.md briefs/brief-b.md   # B builds on A, so pass both
```

The example builder writes `traces/<time>.jsonl`; that file is an example of a submittable trace.

## 9. The practice cases (13)

All run on Wednesday 14 October 2026 at 11:00 (`now` is fixed). 10 use Brief A, 3 use Brief B.

| ID | Brief | Family | Level | Expected ledger |
|---|---|---|---|---|
| PUB-01 | A | Happy path | easy | promise p1 420.00 @ 2026-10-14 (today) |
| PUB-02 | A | Third party | medium | not_reached/callback; callback 2026-10-15 11:00; verify and get_account never called |
| PUB-03 | A | Identity | medium | not_verified/failed; after 3 wrong DOBs, no debt disclosed, app/branch suggested |
| PUB-04 | A | Dates | medium | promise 1250 @ 2026-10-23 (late-band deadline; 6 November declined, deadline offered) |
| PUB-05 | A | Hardship | medium | no_promise/hardship; one sentence of sympathy, no persuasion, support offered once, no discount |
| PUB-06 | A | Amounts | hard | promise 637.50 @ 2026-10-16 (the floor; "how much can you pay" is never asked) |
| PUB-07 | A | Dates | hard | promise 540 @ 2026-10-27 (vague → ask the exact day; 26 October is a holiday → next business day) |
| PUB-08 | A | Already paid | medium | paid; "can take one business day", no promise |
| PUB-09 | A | Restructuring | medium | transferred/restructuring; no plan described |
| PUB-10 | A | Tool failure | hard | promise 365 @ 2026-10-16; first create_promise returns 500, exactly 1 promise after the retry; never "recorded" early |
| PUB-11 | B | Multi-product | medium | 3 promises @ 2026-10-16; all 3 products stated first, one read-back, one create_promise per product |
| PUB-12 | B | Multi-product | hard | promise p1 510 @ 2026-10-15; `refused` note for p2 and p3; phone question asked again once, DOB not; 2 attempts on p2, 1 on p3 |
| PUB-13 | B | Multi-product | hard | p1 300 @ 2026-10-30, p2 900 @ 2026-10-23 (its own deadline); read-back names both dates |

## 10. Rule map of Brief A (what the builder must extract as a spec)

Brief A has 47 rules; "most failed cases come from one rule that was skipped". The **concept categories** a builder
must extract from any brief (the values will change in the hidden briefs; the categories probably stay similar):

| Category | Example in Brief A |
|---|---|
| Call variables | `customer_id`, `first_name`, `last_name`, `title`, `now` |
| Opening | "Freya Bank's digital assistant, the call is recorded"; no "collections/debt/payment/product" before identity; "Am I speaking with {title} {last_name}?"; only a clear yes counts, asked twice, then `not_reached/unclear`; "are you a robot" → "I am a digital assistant" |
| Third party | Do not say why; callback today or next business day 10:00–19:00 and later than `now`; outside the window ask once more, else `no_callback`; wrong number; deceased ("I am sorry for your loss.") |
| Identity | 2 questions in order (DOB, then phone last 4); `verify_identity` per answer; DOB as `YYYY-MM-DD`; 3 wrong in total → `not_verified/failed`; `day_month_swapped` hint does not count as wrong; refuses to answer → explain once, still refuses → `not_verified/declined`; "what is this about" counts as declining |
| Stating the debt | `get_account` only after both questions pass; "collections team, late payment"; product in words ("credit card ending 4821"); amount and days late |
| Calendar | Business days Mon–Fri; holiday list (2026-10-26, 11-11, 11-26, 12-25, 2027-01-01) |
| Band and deadline | days_late 1–7 early → 12th business day, 1 persuasion attempt; 8–45 late → 7th business day, 2 attempts |
| Date rules | Today or later, a business day, not after the deadline; weekend/holiday → next business day; vague → ask once for the exact day, else propose the deadline; "next Friday" = Friday of the following week; after the deadline → offer the deadline, refusal = flat refusal |
| Amount rules | Full amount first; never "how much can you pay"; floor = `minimum_payment` (card) / `instalment_amount` (loan); too much → offer the floor once + "the rest stays overdue"; between floor and full accepted; below → offer the floor |
| Persuasion | "Can you make this payment today?"; a proposed date/amount is never a refusal; a flat refusal uses one attempt; attempt 1: last business day of this week (if today, next week's); attempt 2 (late band): floor on the deadline; then stop, `no_promise/refused` |
| Hardship | Illness, death, job loss → one sentence of sympathy, no persuasion, offer the support team; accept → `transfer_to_agent(support)` + `transferred/support`; decline → `no_promise/hardship`; if the customer names a date/amount, record the promise |
| Forbidden | Discount, waiver, instalment plan, any term not in the brief |
| Confirm and record | Read back product + amount + date, "Do you confirm?"; `create_promise` only after a clear yes; a change → re-check + read back again; one promise per product, no cancellation ("mobile app"); "recorded" only after `ok:true`; failure → 1 retry, then `no_promise/service_error`; then the mandatory sentence "You will receive a text message confirming this promise." |
| Other situations | Already paid → `paid`; dispute → `no_promise/dispute` (no arguing); plan request → `transfer(restructuring)`; wants a human → ask once "can I help first", insists → `transfer(general)` + `transferred/human`; scam → suggest the customer service number, continue; unknown question → "I do not have that information"; "do not want to talk" twice → `refused` (`declined` before identity) |
| Closing | Exactly 1 `close_call`, the last tool call; outcome/reason table (promise, paid, transferred/{restructuring,human,support}, no_promise/{refused,hardship,dispute,service_error}, not_verified/{failed,declined}, not_reached/{callback,no_callback,wrong_number,deceased,unclear}); transfer after a promise → transferred; thank and say goodbye |

Brief B deltas: 1–3 products; state all first; band/deadline per product; "can you pay all of them today?" once, then product by
product in `get_account` order, each starting at attempt 1; one date past a product's deadline → that product on its own deadline;
read all back together, one confirmation, then `create_promise` per product; `add_note` for every product without a promise
(`refused|hardship|dispute|paid|service_error`); a dispute/paid on one product does not end the call; restructuring → transfer,
recorded promises stay, no notes at all; one promise fails twice → keep the others + `service_error` note; closing: ≥1 promise →
`promise`, all paid → `paid`, else the note reason of the first product that is not paid.

### Hints from the kit: how the hidden briefs may differ

The persona code in `tools/run_cases.py` lists identity fields that hidden cases may use: `date_of_birth`, `phone_last4`,
**`postcode`, `birth_year`, `company_number`, `founded_year`**. So a hidden brief may call a business customer (a company).
`score.py` recognises **`no_contact` and `unreached`** next to `not_reached`: outcome names will change. The `faults` field
(`fail_first_n`) can apply to any tool. `style` and `third_party` can be embedded in a case. None of this comes from a hidden
brief; it is in the public kit, so it is legitimate input for designing a general builder.

## 11. The Freya platform: 25 things the builder must know (docs digest)

Full source in `docs/`. The most critical points:

1. After each user message, **three separate model calls**: extraction (fills variables), routing (leave the node or not), dialogue (reply or tool call). A routing instruction in a prompt has no effect; routing reads only transitions.
2. Node types: `conversation` (speaks, `tools`, `extraction_schema`), `api_request` (HTTP on entry, `pre_actions`), `code` (Python on entry, `pre_actions` + `code_exec`), `end_call` (`terminal`). The platform **silently strips** `tools`/`pre_actions` placed on the wrong node type.
3. Do not send `agent_config`; no `null` values (strict schema); `test_variables` for default call variables.
4. One variable table for the whole call; `{{var}}` works in prompts, on_enter text, transition descriptions, URLs, headers and bodies. An unresolved `{{var}}` stays literal in a prompt (the model sees it).
5. A tool parameter's value is decided by **`default`**: a literal or a `{{var}}` with a value → baked, the model never sees it; a `{{var}}` without a value or no default → the model fills it. **Never use `const`** (it does not bake; a `const` URL fails with "URL is required").
6. `api_call` body fields are leaves under `body.properties.<field>`, each with `type`, `description`, `enum`, `default`; `body.required`. `customer_id` → `"default": "{{customer_id}}"` (baked). For model-filled fields use a variable name that does not exist.
7. A tool `description` must carry the trigger: "CALL it every time...". A plain description lets the model say "done" without calling. In the prompt: after every tool result, speak or call the next tool; never produce an empty turn ("The model returned no speakable content").
8. A tool result is an envelope `{status, data, message, status_code, header}`; the API body is under `data`. The engine flattens every result automatically: `<tool>_response.data.<field>`, `<tool>_args.<field>`, `<tool>_success_count`, `<tool>_failure_count`, `<tool>_status_code`.
9. `response_mapping` paths **start with `data.`**. On the tool object for `tools`, on the node for `pre_actions`.
10. **Booleans arrive as strings** (`"true"` / `"True"`); OR both spellings in routes, or write string flags from code (`verified`/`rejected`).
11. Routing also runs when a tool result arrives: a transition on a mapped variable fires in the same turn without a new user message. The pattern "a closing tool sets a variable → a transition on it goes to end_call" is verified.
12. Conditions: deterministic (`equals`, `not_equals`, `greater_than`, `less_than`, `contains`, `is_set`, `is_not_set`, `always`) and semantic (`matches_intent`). The top-level group is always `"logic": "or"`; nest `"logic": "and"` inside. Deterministic ones are evaluated first with no model call.
13. Evaluation order: `loop_condition` → the node's transitions (list order) → global nodes → nothing (stay). Transitions with the same `target_node` are merged with OR.
14. A passthrough node (`api_request`, `code`) **must** end with an `always` transition or it deadlocks. Set `on_enter: {"type":"silent"}` and `passthrough_default_transition`.
15. Code nodes: read/write through `vars`; `json`, `re`, `datetime` can be imported; **never write `{{` or `}}`** (a nested dict literal ends in `}}`, beware); **never raise** (try/except + a fallback for every variable); write routing flags as strings. Call variables (`now`) via `vars.get("now")`. A string written by a code node resolves as `{{date_facts}}` in later prompts. A passthrough `code` node can be the `initial_node`.
16. **Do all date maths, business days, deadlines and counters in code and hand the model finished text.** Verified: the working builder computes a date-facts block in a code node and puts it into the prompts.
17. `pre_process_code` / `post_process_code` only on `api_call` tools; `result` is the envelope; a `what_to_do_next` line added to `result["data"]` in a post-hook reaches the model; `result.pop("header")` drops the headers. Hooks wrapped in `try/except Exception: pass`. This fixes the "silent after a tool call" and "ignores a negative result" problems.
18. `maxRetries`: 0 on tools that write (double-record risk), 2 on read-only. `connect_retries` only for connection failures.
19. Lifecycle tools: workflow-level `tools[]` + `config.alwaysRunsAt: ["end_of_call"]` → never shown to the model, fired by the engine at call end. base-agent does `close_call` this way; if `{{outcome}}`/`{{reason}}` are unresolved, one model call fills them. `response_mapping` is not applied at end_of_call.
20. `end_call` nodes: `terminal.function.name` = the call's `endedReason`; `message_mode: custom` + `spoken_message`, or `none` (say goodbye in the previous node); `disable_inactivity_monitor: true`, `transitions: []`.
21. `extraction_schema`: set `min_confidence` on every variable (default 0.95 is strict, values are silently dropped); declare dates as `type: "date"`; forking on an extracted enum (`equals`) is more reliable than several `matches_intent`. Extraction for user speech, response_mapping for API responses.
22. `max_node_turns` defaults to 10 and counts only user turns; without `max_turn_transition` the cap changes nothing. The working builder uses 60–80.
23. `context_variables` is lost when saved over the API; do not rely on it, write `{{var}}` into prompts.
24. API: `POST /api/v2/workflow` (validate with dryRun=true); `PUT` **does not publish**; `freya.save_workflow` does create/update + publish + the AGENT_LLM fix. `POST /api/v2/chat/message` runs one turn at a time with no simulation (seconds), ideal for smoke tests. `GET /api/v2/call/{id}` → `messages` with `route_evaluated`, `function_call_start/complete`, `variable_table`.
25. Troubleshooting: `error code: 1010` → User-Agent missing; "Workspace plan limit reached" → update in place; score never moves → not published; `unknown product_id` → the model invented an id, give it from `get_account` or fill it in code; `customer-ended-call` → the agent was slow (median >10 s warning); if the model was busy the score is not ours, rerun.

### Verified on the platform while building (10 October, evening)

- A deterministic transition that tests a variable extracted in the same turn does **not** fire in that turn
  (`route_evaluated` shows the value in the table but `matched=False`); it fires one turn later on the stale value.
  A code node entered through an `always` transition **does** see the fresh extraction. So every customer turn goes
  conversation node → `always` → code node → `route` variable → next node. Transitions never test extracted variables.
- On the chat route (`POST /api/v2/chat/message`) the very first customer message of a call is not routed at all
  (`branches=[]`); the dialogue model answers it. From the second message on, routing is normal. Chat scenarios therefore
  start with a throwaway "Hello?". Simulations do not show this: the agent speaks first, then the customer.
- Tool defaults such as `{{customer_id}}` are resolved against `test_variables` at call start on the chat route, so a
  `test_variables.customer_id` overrides the real one. The builder sends no `test_variables`.
- `on_enter: {"type": "tts", "text": "{{say}}"}` resolves a variable written by the code node entered in the same turn.
  Every agent sentence is composed in code and spoken this way; the dialogue model is never relied on (it was seen
  emitting reasoning text and a made-up tool call on entry).
- A failed HTTP call (`function_call_error`) runs no response mapping; `rec_ok` stays empty, so the retry is a second
  api node reached by the `always` fallback. Each `create_promise` attempt clears `rec_ok`/`rec_ok_retry` first.
- The chat route returned 503 for every call while a simulation was running in the workspace.
- A simulation can stay `running` for ever after every call has ended (the judge's analysis never arrives and runs show
  `inconclusive`); the kit's scorer then polls for ever. `POST /api/v2/simulations/{id}/cancel` ends it
  (`builder/freya_ext.cancel_running_simulations`); `builder/run_cases_safe.py` runs the scorer under a watchdog.
- A 10-case simulation of the compiled Brief A agent took 146 s; the kit's example run took 63 s for the base agent.

## 12. Strategy: what the builder should be

### The core of the problem

The hidden briefs change the **values** (holidays, questions, bands, deadlines, outcome names, tool fields/enums), the **form**
(raw mail + memo + code list) and the **customer behaviour** (numbers in pieces, corrections, off-topic talk, dates in words,
different `now` days); every case must pass 3/3. So we need two things at once:

- **Reading generality**: read a brief in any form into a structured spec. An LLM (Claude) must do this.
- **Runtime determinism**: date maths, business days, deadlines, floors, attempt counters, tool fields and transitions must be
  decided by code; every rule left to a prompt risks drifting in one of the three runs.

### Proposed architecture: agentic builder + deterministic helper library

The kit's example builder (Claude Agent SDK + 1 skill) produced 10/10 on Brief A; that baseline is ours today. A deterministic
parser written from scratch breaks on the raw-material brief. So: **keep the agentic core, move the fragile parts into code.**

```
brief (.md | raw material) + <brief>.openapi.json
        │
        ▼
builder/build.py  (harness: one command, time budget, trace writer, export)
        │
        ▼
Claude Agent SDK run, skills:
   [1] brief → spec.json   (identity questions, calendar/holidays, band/deadline table, floor definition,
                            persuasion rules, outcome/reason table, special cases, mandatory sentences,
                            tool field mapping)  — "remember nothing from Brief A, take it from the brief"
   [2] spec + helpers → workflow.json
        builder/lib/tools_from_openapi.py   the 7 tool definitions from openapi.json (fields, enums, required, defaults, post-hooks)
        builder/lib/date_facts.py           generic code-node template: now + holidays + band table → deadline,
                                            last business day of this/next week, next business day, "next <weekday>", callback window
        builder/lib/skeleton.py             proven node skeleton (setup code → opening/identity → account → negotiate (per product)
                                            → confirm/record → close) + end_call nodes
        builder/lib/lint.py                 the docs checklist, automated: no const, body.properties leaves, data. paths, always on passthrough,
                                            no {{ }} in code, both boolean spellings, every path reaches end_call, tool descriptions say "CALL"
   [3] validate (dryRun) → save_workflow(slot) → export → chat smoke test (the builder plays the customer) → run_cases if available
   [4] FAIL analysis (transcript + route_evaluated) → fix spec/prompt/skeleton → repeat within the budget (≤ 30 min)
        │
        ▼
submission/<brief>.workflow.json  +  traces/<brief>.log
```

Principles:

- Tool definitions are **always** generated from the given openapi.json, never written by hand (fields/enums change in the hidden briefs).
- The date-facts code node is **generic**: the holiday list, the band table and the window rules arrive as variables from the spec; no fixed date in code.
- Leaving a node depends on a tool result (the ledger's truth), not on what the customer said.
- Prompts are small per node: only that step's rules plus the finished facts produced by the code node.
- The builder's self-test must not depend on practice cases (there may be none for the hidden briefs): dryRun + chat/message
  smoke scenarios (5–8 scenarios generated from the brief, the builder plays the customer itself, checks the transcript against the brief).
- The trace is written by the harness (SDK message stream → start/end, every model call, created ids, tests), not left to the skill.
- The time budget lives in the harness: near 30 min, skip the test round and export the last valid workflow.

### For the tie-breaks

- Total promised amount: the brief already says "full amount first"; not dropping to the floor unnecessarily raises both the score and the amount.
- Build time: the 2 hidden briefs run sequentially (1 simulation per workspace). Keep the builder's internal tests few and fast (`--only` for selected cases, chat smoke tests).

## 13. Risks

| Risk | Mitigation |
|---|---|
| Flakiness: the same agent passes once and fails the next time; a slow model makes the customer hang up | Rules → code/routes; `--reps 3`; watch the median turn-time warning, rerun when slow |
| The hidden brief is raw material; the parser/spec extraction gets confused | Give spec extraction to the LLM, keep the schema conceptual, "quote the brief when unsure"; rehearse with differently formatted briefs we write ourselves |
| Tool fields/enums change, code expects old field names | Generate tools from openapi.json; never hard-code field names |
| `now` on different days (a Friday, the eve of a holiday, year end) | Date facts entirely from `now`; run our own tests with varied `now` (practice sessions get `now` from the mock; chat/message lets us pass any `now`) |
| The builder exceeds 30 min | Hard budget in the harness; keep test rounds short |
| The final 3-hour window: 2 briefs × (build ≤30 min) + sequential simulations + export + commit + form | "Dry run" before Sunday: run Brief A and B as if hidden, back to back, and time it; form and email prepared in advance |
| Leaking something from a hidden brief into the code (disqualification) | Both of us review every commit made after Sunday 17:00; crash fixes only |
| The 200-workflow workspace limit | Update in place with `save_workflow(slot)`; fixed slot names |
| Key leak | `env.sh` is gitignored; grep traces before committing |

## 14. Status (Sunday 13:30 UTC, 16:30 TR)

Done:
- Builder end to end: `python3 builder/build.py <brief> <api>` extracts the spec (1 Opus call, ~$0.25–0.45, ~50–65 s),
  compiles, lints, dry-runs, saves in place (with retries), exports (even when the platform is down), self-tests, writes
  the trace. Architecture in `builder/README.md`. Fresh `git clone` dry runs pass.
- Practice cases (`traces/practice-results.md`): plain style A 10/10 and B 3/3 in every repeated run over the night;
  all speaking styles pass except that `talkative` fluctuates (the platform cuts the customer's sentences).
- Generalisation: spec extraction is stable across three runs on the raw-material rehearsal brief; Brief C (the kit's
  API, 30 different rules) was extracted correctly and the compiled agent followed Brief C's rules in 9/9 live calls.
- Unit tests: 100 (`python3 -m unittest discover builder/tests`).
- Robustness to briefs unlike A/B (13:00–13:25 UTC, after the freeze candidate): a spec with only the required keys
  compiles, lints and runs a call (`builder/tests/test_sparse_spec.py`); attempts default to the asked amount then the
  floor by the deadline when the brief lists none; hardship without rules gets one sentence of sympathy and the normal
  persuasion; third parties switched off close politely; a callback today only on a business day, a wrong-answer limit
  per security question and attempts that propose a share of the past-due amount are available when a brief states them.
  Brief A and B compile exactly as before.

Platform on Sunday morning: 502/503/504 for long stretches, judge analyses missing ("inconclusive"/"error"), simulations
left hanging. Everything that talks to the platform now retries with back-off, cancels hung simulations and never blocks
the export. If the platform is like this at 17:00 UTC: run the command anyway; the trace shows the retries and the
export is written from the compiled workflow; rerun the same command when the platform answers to get a platform save.

Open:
- [ ] YC registration and team name; the submission email address from the kit email; GitHub repo access for the organisers; push.
- [ ] Freeze at 15:30 UTC: `git status` clean, unit tests green. After 17:00 UTC only crash fixes, one commit each.

## 15. Sunday

Procedure and checklist: `SUBMISSION.md`. Allowed after 17:00 UTC: crash fixes only, reviewed by both, one commit each.
Leak check before the final commit: `python3 builder/leak_check.py <freeze_commit> briefs/hidden-1.md briefs/hidden-2.md`.
