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

What the style runs taught the builder (all fixed in code, not in prompts): dates and years said in words or digit by
digit; a question asked back during the security check; small talk that the platform cuts mid-sentence (treated as a
non-answer to ask again, not as a refusal); a day said alone ("30") or in two parts; a self-correction ("the 21st,
sorry, the 20th"); re-asks that repeat only the question so an offer is never made twice.
