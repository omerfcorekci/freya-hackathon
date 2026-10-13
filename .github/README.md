# Build the Builder: our entry and what we learned

Our entry to **Build the Builder**, the Freya × Y Combinator hackathon (10–11 October 2026). The task was to write a
*builder*: a program that reads a bank's documents and produces a phone agent (a Freya workflow) with no manual step.
Only the phone agents it produces are scored. The organisers' starter kit sits at the repository root, unchanged; its
own README is [`README.md`](https://github.com/omerfcorekci/freya-hackathon/blob/main/README.md).

## Result

**11th** on the [final leaderboard](https://www.freyavoice.ai/hackathon/leaderboard), with **63.4 / 100**.

| | Us | 1st place |
|---|---|---|
| Workflow quality (reviewed by the organisers) | **40 / 60**, the highest score, shared with 1st | 40 / 60 |
| Hidden simulated calls passed | 74 / 120 (61.7%) | 84 / 120 (70.0%) |
| Happy path | 10 / 13 | 11 / 13 |
| Edge cases | **38 / 51**, the best of all teams | 37 / 51 |
| Adversarial | 30 / 46 | 34 / 46 |
| Critical | 8 / 10 | 8 / 10 |

The design held up. The ranking was lost in the simulated calls.

## How the builder works

- **Practice round (collections calls in English):** one structured model call turns the brief into a `spec.json`.
  Deterministic Python then compiles it into the workflow: every rule (dates, business days, deadlines, floors,
  attempt counters) runs in code nodes, and every sentence the agent says is composed in code. Brief A passed 10/10 and
  Brief B 3/3 in repeated runs. See [`HACKATHON.md`](https://github.com/omerfcorekci/freya-hackathon/blob/main/HACKATHON.md).
- **Final (statement-debt calls in Turkish):** the input was a folder of bank documents written months apart, not a
  brief. A case mode renders every file to text, and a Claude Code run with a project skill designs the workflow.
  The same deterministic harness then lints, dry-runs, saves, exports and replays scripted calls. We also wrote the
  bank's mock services as a Cloudflare Worker that answers all 617 test responses of the pack exactly. See
  [`SUBMISSION.md`](https://github.com/omerfcorekci/freya-hackathon/blob/main/SUBMISSION.md) and
  [`HACKATHON.md`](https://github.com/omerfcorekci/freya-hackathon/blob/main/HACKATHON.md) section 17.

## What worked

- **Rules in code, not in prompts.** The reviewers summed up the agent as "a code-driven state machine where brain
  owns all logic and the model only extracts fields and speaks fixed sentences". It got the top quality score and the
  best edge-case result.
- **Reading conflicting sources by date.** The design step wrote down which document won each conflict and why, in
  [`traces/final.notes.md`](https://github.com/omerfcorekci/freya-hackathon/blob/main/traces/final.notes.md). The
  newest decisions (meeting transcripts, the last recap mail) overruled the older analysis wherever they disagreed.
- **Testing against real transcripts.** We replayed the case's example scenarios and 25 more of its rules against the
  saved agent, then compared what it said with what the documents asked for. Two later builder runs that looked
  better on paper failed this check, so we kept the earlier one.

## What did not

- **The goodbye waited for the caller.** The agent said "Sizi ana menüye yönlendiriyorum" but only hung up on the
  caller's next turn. Our scripted tests always had one more customer line, so they never showed it. A simulated
  caller who stays silent leaves the call hanging, which most likely cost easy calls.
- **No platform silence setting.** The case's "end after three silences" rule was written in code. Without the
  platform's inactivity timer it never fired on a silent caller.
- **We tested on the chat route only.** Both problems above show up only in a real voice simulation. One full voice
  run of the example scenarios before submitting would probably have caught them.
- **Free-text extraction fields.** The reviewers noted that the fields were free strings rather than enums. Our
  results also depended on which model ran the agent: the organisers re-scored it on a second model.
- **A "no card" answer looked like a technical error.** The platform passes neither the status code nor the body of
  a failed tool call to the workflow. Our agent could not tell the bank's "no eligible card" 404 from a 500, and it
  used the technical-error sentence for both.

## If we did it again

1. Run the agent in the platform's own voice simulation at least once, with callers who go silent and callers who
   hang up.
2. Have the closing step end the call itself right after the goodbye, and configure the platform's silence handling.
3. Use enums for every extracted field.
4. Spend the last hour on what the reviewers would hear, not only on what our probes check.

## Repository map

| Path | What it is |
|---|---|
| `builder/` | the builder: practice compiler, case mode (`case.py`), text extraction, lint, harness |
| `.claude/skills/build-case-agent/` | the skill the final's design step runs with |
| `mock/` | the bank's services as a Cloudflare Worker, generated from the case's test customers |
| `submission/final.workflow.json` | the submitted phone agent |
| `traces/` | builder traces, the Claude Code session log of the final run, design notes, probe transcripts |
| `probes/` | scripted calls used to check the final agent |
