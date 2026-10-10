# Submission

Hackathon: Build the Builder (Freya × Y Combinator), 10–11 October 2026.

## The builder

One command, a brief in, a phone agent out:

```
python3 builder/build.py <brief_path> [<more brief paths>] <tool_api_path>
```

Example for the hidden briefs:

```
source env.sh
python3 builder/build.py briefs/hidden-1.md briefs/hidden-1.openapi.json 2>&1 | tee traces/hidden-1.stdout.log
python3 builder/build.py briefs/hidden-2.md briefs/hidden-2.openapi.json 2>&1 | tee traces/hidden-2.stdout.log
```

Each run:

1. makes one model call that turns the brief into a structured spec (`out/<slot>/spec.json`), plus at most one repair call
   when the spec disagrees with the tool API's allowed values;
2. compiles spec + tool API into the Freya workflow with plain Python (tools from the OpenAPI file, date maths and the
   negotiation state machine as code nodes, fixed sentences, routes on tool results);
3. validates it (lint, platform dry run), saves it in place (`freya.save_workflow(slot)`), exports it to
   `submission/<slot>.workflow.json`;
4. runs self-tests (offline code-node checks, chat scenarios, the practice cases when a case file matches the brief);
5. writes the trace `traces/<slot>.log`: start and end time, every model call, what was created on Freya, every test.

Needs Python 3.10+, `pip install claude-agent-sdk`, a Claude login or `ANTHROPIC_API_KEY`, and the keys in `env.sh`
(copy `env.example`). `BUILDER_MODEL` selects the extraction model (default `claude-opus-5-5`).

## Form (to the address in the kit email, before Sunday 20:00 UTC)

```json
{
  "team": "TEAM_NAME",
  "repo": "https://github.com/omerfcorekci/freya-hackathon",
  "commit": "COMMIT_SHA",
  "run_command": "python3 builder/build.py {brief_path} {tool_api_path}",
  "workflows": {
    "hidden-1": "submission/hidden-1.workflow.json",
    "hidden-2": "submission/hidden-2.workflow.json"
  },
  "traces": {
    "hidden-1": "traces/hidden-1.log",
    "hidden-2": "traces/hidden-2.log"
  }
}
```

## Sunday checklist (UTC)

- 16:45 `source env.sh`; `python3 -m unittest discover builder/tests`; `python3 builder/build.py builder/rehearsal/clean.md builder/rehearsal/clean.openapi.json --offline --spec out/clean/spec.json` (or without `--spec`) runs clean; platform reachable; support channel open.
- 17:00 read both hidden briefs for ten minutes. Touch no code.
- 17:10 run hidden-1; 17:45 run hidden-2 (one simulation at a time per workspace, so sequentially).
- 18:20 `python3 -c "import json; json.load(open('submission/hidden-1.workflow.json'))"` for both; node and tool counts in the
  export lines of the traces match the saved lines; `grep -n fak_ traces/*.log` finds nothing; commit `submission/`,
  `traces/`, `out/*/spec.json`; push.
- 18:30 send the form with the commit sha.
- Until 19:30: if a run crashed or its save failed, rerun the same command (new trace), commit, resend the form.
- After 17:00 only crash fixes, each in its own commit named after the crash, reviewed by both of us.
