# The builder

`python3 builder/build.py <brief.md> [<more briefs>] <tool_api.json>` reads a bank's collections brief and creates a
phone agent on Freya. One command, no manual step. The trace of a run is `traces/<slot>.log`.

## How it works

```
brief + tool API ──(1 model call)──► spec.json ──(Python)──► workflow.json ──► lint ──► dryRun ──► save (in place) ──► export
                                                                                                        └──► self-tests ──► trace
```

1. **Spec extraction** (`extract.py`, `spec_schema.py`). One structured-output call to Claude turns the brief, in whatever
   form (a clean specification or a mail + policy + memo + code list), into a fixed-vocabulary JSON spec: identity
   questions, calendar and holidays, lateness bands with deadlines and persuasion attempts, amount floors, date rules,
   the outcome table, the sentences the agent must say. The spec is validated against the tool API's enums (identity
   fields, outcomes, reasons, queues, note reasons); one repair call fixes disagreements. Nothing is defaulted from
   another brief: structural defaults only, every missing bank value is a warning in the trace.
2. **Compilation** (`skeleton.py`, `nodes.py`, `codegen.py`, `nodecode.py`, `datefacts.py`, `toolapi.py`, `prompts.py`).
   Plain Python builds the workflow:
   - the seven tools are generated from the OpenAPI file (fields, enums, required lists, URL), never written by hand;
   - every bank tool runs in an `api_request` node with its fields baked from variables, so the model never chooses a
     product id, a queue, an outcome or an answer format; `create_promise` is retried by a second node;
   - every sentence the agent says is composed in a code node and spoken as a fixed line (`{{say}}`); the dialogue model
     is never relied on. The extraction model classifies what the customer said (stance, dates and amounts as said,
     side questions);
   - date maths (business days, holidays, deadlines per band, "next Friday", callback windows), floors, persuasion
     attempt counters, multi-product negotiation, read-back, notes and the close_call outcome are all computed in code
     from `now` and the spec; the code library is unit-tested offline and shipped verbatim into the code nodes;
   - every customer turn goes conversation node → `always` → code node → `route`, because the engine does not see a
     turn's extracted variables in that turn's transitions (observed), but a code node does.
3. **Checks** (`lint.py`, `selftest/`). A linter enforces the platform's documented rules (no `const`, body leaves with
   `default`, `data.` mapping paths, `always` on passthrough nodes, no `{{` in code, every path reaches `end_call`).
   The platform's dry run validates the schema. Self-tests: the generated code nodes run locally for several call dates
   and spoken-answer formats; scripted chat scenarios play customers through `/api/v2/chat/message` when the platform
   answers; the kit's practice cases run when a case file matches the brief.
4. **Trace** (`trace.py`). Start and end, every model call with purpose and cost, what was created on Freya (workflow id,
   agent id, node and tool counts), every test with its verdict. Secrets are masked.

## Layout

| File | Role |
|---|---|
| `build.py` | the one command: orchestration, budget, trace, export |
| `extract.py`, `spec_schema.py` | model call with JSON-schema output; the spec vocabulary, validation, defaults |
| `toolapi.py`, `cfg.py` | tool definitions from the OpenAPI file; field roles; CFG for the code nodes |
| `skeleton.py`, `nodes.py`, `prompts.py` | the node graph, transition helpers, extraction descriptions |
| `datefacts.py`, `nodecode.py`, `codegen.py` | the sandbox date library, the node logic, and the sources shipped into code nodes and hooks |
| `lint.py` | static checks on the generated workflow |
| `selftest/` | offline, chat and practice-case self-tests |
| `freya_ext.py`, `run_cases_safe.py`, `batch_tests.py` | chat and call helpers, simulation cancel, watchdogged scorer runs |
| `rehearsal/` | two briefs for another bank (business customers, three identity questions, four bands, other outcome names; one as raw mail + policy + memo + code list) with modified tool APIs |
| `tests/` | unit tests: `python3 -m unittest discover builder/tests` |
