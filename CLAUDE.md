# CLAUDE.md

Project: **Build the Builder**, the Freya × Y Combinator hackathon (10–11 October 2026, online).
We write a *builder*: a program that reads a bank's collections brief and creates a phone agent
(a Freya workflow) with no manual step. Only the phone agents it produces are scored.

`HACKATHON.md` is the single source of truth for rules, scoring, timeline and strategy. Read it
before changing anything.

## Layout

- The organisers' kit (version 3, as it arrived by email) lives at the repo root, unchanged:
  `README.md` (ten-minute start), `briefs/`, `docs/` (workflow format, tools and code, API),
  `tools/run_cases.py` (scorer), `tools/openapi.json` (the bank's tool API), `freya.py` (API client),
  `examples/` (base agent, example builder), `public-test-set.json` (13 practice cases),
  `.claude/skills/build-phone-agent/` (the example skill), `VERSION`, `env.example`.
  Do not edit kit files in place; when a new kit version arrives by email, replace them in one commit and note the version.
- `builder/` is our code. `submission/` holds the exported workflows. `traces/` holds builder run traces.
- `env.sh` (gitignored) holds the keys. Copy it from `env.example`.

## Language

- Everything in the repo is in English: all Markdown documents (`HACKATHON.md`, READMEs, notes), code, comments,
  commit messages and file names. Reviewers and organisers read the repo.

## Git workflow (mandatory)

We keep a clean, honest git history. Reviewers clone the repo at the submitted commit and read it.

- Commit early and often. Every meaningful milestone gets its own commit: a working step, a fixed bug,
  a doc update, a kit import. Never pile a day of work into one commit.
- One logical change per commit. Do not mix a refactor with a feature or a doc change with code.
- Conventional Commits format: `type(scope): subject`. Types: `feat`, `fix`, `docs`, `chore`, `test`,
  `refactor`. Scope is optional (`builder`, `kit`, `trace`, `submission`).
- Subject in the imperative mood, no trailing period, at most 72 characters.
  Body explains *why*, not what, when the diff does not make it obvious.
- Commit messages end with the attribution line given by the harness
  (`Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`).
- Work on `main`. Do not rewrite or force-push history that has been pushed.
- Never commit secrets: `env.sh`, `.env`, API keys, team keys. Check `git diff --cached` before every commit.
  Traces must have keys removed before they are committed.
- Commit the things the submission needs: builder code, `submission/*.workflow.json`, `traces/*.log`.

## Hackathon hard rules (violations disqualify)

- The builder is one command: brief path + tool API path in, phone agent out. No manual edit of a
  phone agent after the run, on the platform or in the exported file.
- Nothing from a hidden brief may be written into the builder: no rule, no value, no holiday, no outcome
  name. Fixing a crash on unexpected input is allowed. A reviewer reads the commit for this.
- Do not change `AGENT_LLM` in `freya.py`. The phone agent runs on Freya's model for every team.
- The phone agent calls only the tool API from the kit. Code nodes and hooks inside the workflow are fine.
- One Freya API key per team. Do not probe or load-test the platform.
- Update the workflow in place (`freya.save_workflow(slot, ...)`), never create one per run.
  A workspace holds 200 workflows.
- A builder run on one brief may take 30 minutes at most, tests included.
- Every builder run writes a trace: start/end time, every model call (model + one-line purpose),
  what it created on Freya (workflow id, agent id, steps, tools), and every self-test with its result.

## Working conventions

- Python 3.10+. Standard library where possible; `claude-agent-sdk` / `anthropic` for the builder's own model calls.
- Build the phone agent from the brief and the tool API file. Whatever can be taken from the brief must be
  taken from the brief, never hard-coded from Brief A/B.
- Prefer rules in routes and code over rules in prompts: date math, business days, deadlines, floors and
  counters belong in code nodes. The judge runs each case three times and all three must pass.
- Test with `python3 tools/run_cases.py <agent_id> --brief A|B`. One run is a hint, `--reps 3` is proof.
  Only one simulation runs at a time per workspace, so never start two.
- Remove `header` from tool results in post-hooks and add a `what_to_do_next` line; mapping paths start with
  `data.`; booleans arrive as strings; never write `{{` or `}}` inside code nodes. See `docs/tools-and-code.md`.
