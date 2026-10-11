# Practice results (public cases, kit v3)

Runs of the compiled phone agents against the kit's 13 practice customers, through `tools/run_cases.py`
(bank ledger + judge). One line per batch; the builder's own traces are `traces/brief-a.log` and `traces/brief-b.log`.

| When (UTC) | Agent version | Brief | Style | Reps | Result |
|---|---|---|---|---|---|
| 10 Oct 22:57 | A v1 (dialogue model in the identity step) | A | plain | 1 | 10/10 |
| 10 Oct 23:11 | A v2 (every sentence from code; spoken dates not yet parsed) | A | plain | 1 | 3/10, loops on spoken dates |
| 10 Oct 23:42 | A v4 | A | plain | 1 | 8/10 (side question ignored; judge read "recorded" in the opening) |
| 10 Oct 23:47 | A v5 | A | plain | 1 | 10/10, median turn 2 s |
| 10 Oct 23:52 | B v3 | B | plain | 1 | 3/3 |
| 10 Oct 23:58 | A v5 | A | plain | 3 | 10/10 in all three runs |
| 11 Oct 00:05 | B v3 | B | plain | 3 | 3/3 in all three runs |
| 11 Oct 00:12 | A v6 | A | pieces, corrects | 1 | 10/10, 10/10 |
| 11 Oct 00:15 | A v6 | A | talkative, asks_back, in_words | 1 | 5/10, 6/10, 5/10 |
| 11 Oct 00:27 | B v4 | B | plain, pieces, corrects, talkative, asks_back, in_words | 1 | 3/3, 2/3, 3/3, 2/3, 1/3, 3/3 |
| 11 Oct 00:40 | A v7 | A | talkative, asks_back, in_words | 1 | 8/10, 10/10, 10/10 |
| 11 Oct 00:47 | B v5 | B | pieces, talkative, asks_back | 1 | 1/3, 2/3, 2/3 |
| 11 Oct 00:57 | A v8, B v6 | A, B | talkative; pieces, talkative, asks_back | 1 | A 8/10; B 3/3, 2/3, 3/3 |
| 11 Oct 01:05 | A v9, B v7 | A, B | talkative | 1 | 10/10; 2/3 |
| 11 Oct 01:11 | A v10, B v8 | A, B | plain | 3 | **10/10 and 3/3 in every run** (regression check after all style fixes) |
| 11 Oct 01:20 | A v10, B v8 | A, B | talkative | 2 | A: run killed after a simulation hung 20 min (watchdog); B: run 1 0/3 (two judge analyses never arrived, one agent loop), run 2 3/3 |
| 11 Oct 01:57 | A v11, B v9 | B, A | plain; talkative | 1 | B plain 2/3 (a count of products read as an amount); B talkative killed after a hung simulation; A talkative 9/10 |
| 11 Oct 02:19 | A v12, B v10 | B, A | plain ×2, plain, talkative | 2, 1, 1 | **B 3/3 in both runs, A 10/10, B talkative 3/3**, A talkative 9/10 (an offer repeated after a cut-off turn) |

What the style runs taught the builder (all fixed in code, not in prompts): dates and years said in words or digit by
digit; a question asked back during the security check; small talk that the platform cuts mid-sentence (treated as a
non-answer to ask again, not as a refusal); a day said alone ("30") or in two parts; a self-correction ("the 21st,
sorry, the 20th"); re-asks that repeat only the question so an offer is never made twice.

## Generalisation checks (Sunday morning)

- Spec extraction run three times on the raw-material rehearsal brief (mail + policy + memo + code list): holidays, bands,
  persuasion attempts, identity questions, callback window, floor rule, outcome table, hardship/plan/human/paid rules and
  the mandatory sentences were identical in all three; only the name of the custom situation varied.
- Brief C (`builder/rehearsal/brief-c.md`: Harbor Trust Bank, the kit's tool API, 48 rules, 30 values that differ from
  Brief A: three bands including a calendar-day deadline, weekend dates moved to the previous business day, a fraction
  floor for cards, "next Monday" as the next occurrence, a two-business-day callback window 08:00–18:00 with two retries,
  two "can I help first" asks, other sentences, an "abroad" situation): every value extracted correctly; compiled,
  dry-run and saved on the platform.
- Brief C live (11 Oct 12:00–12:20 UTC, platform degraded, judge analyses mostly missing): the ten public personas
  talked to the Brief C agent; the nine calls that completed followed Brief C's rules, not Brief A's: deadline 22 October
  for a 14-day case (A: 23 October), 26 October accepted as a business day (A moves it to 27 October), a credit-card floor
  of half the past-due amount (1062.55), Brief C's opening, intro, first question, letter sentence, "two business days"
  paid sentence, callback within the 08:00–18:00 window, notes on products without a promise. One wording slip
  ("to to connect them") fixed afterwards.
- Freeze candidate (11 Oct 12:22 UTC saves, run 12:51–12:55 UTC): Brief A **10/10**, Brief B **3/3** (plain style) on the
  final code; the platform's judge answered normally for these runs.
- Robustness pass (11 Oct 13:21 UTC saves, A v16 and B v14, same specs; runs 13:22–13:40 UTC): Brief A **10/10**. Brief B
  1/3, then 2/3, then PUB-13 alone 1/1: every failure was a call with no events at all after the customer's first answer
  ("Yes, this is …"), no `variable_extracted`, no code node, 61 s of silence, `customer-ended-call`. The platform was slow
  (median slowest agent turn 25 s against 4–6 s earlier) and the three B calls start at the same instant. The workflow on
  the platform was compared with the local compile (identical apart from the platform's default fields) and with the
  freeze candidate (opening node, system prompt and every non-code part byte-identical; only the code strings changed,
  and no code node ran in the stalled calls). Each of PUB-11, PUB-12 and PUB-13 passed on the new code with the expected
  tool path once its first turn went through. A fourth run at 13:38–13:42 UTC, once the platform had recovered (median
  slowest turn 3 s): Brief B **3/3** in one simulation. Plain-style result on the frozen code: A 10/10, B 3/3.
- Varied openers (saves 14:09 UTC; run 14:10–14:20 UTC): A 7/10, B 3/3. All three A failures were the platform's code
  sandbox: PUB-07 shows `function_call_error: Failed to reach snekbox: Connection reset by peer`; in PUB-01 the
  `identity_prep` code node reported success but wrote no variable (the agent then spoke the literal `{{say}}` and
  `verify_identity` was called without a field until the call hit its maximum duration); in PUB-09 the judge passed the
  call but the `close` node's API call never started after the transfer. The same code runs in the local sandbox in
  milliseconds. The variation itself had not reached the platform yet (it hung on the test runner, not on the shipped
  code string); fixed in `cf17cf3`, saved 14:24 UTC and run again below.
