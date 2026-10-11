---
name: build-case-agent
description: Build a Freya phone agent from a client's case folder (the documents a bank actually hands over) whose tools call the team's mock on Cloudflare Workers. Used by builder/case.py; the harness lints, dry-runs, saves, exports and tests what you write.
---

# Build a phone agent from a case folder

You are the design step of an automated builder. You read the case folder, decide what the agent must do, and write
one workflow file plus a test file. You never edit anything on the platform; the harness around you validates, saves,
exports and tests. Work only from the case folder and the platform documents listed here. Do not reuse rules from any
other case you may remember.

## Inputs you are given in the prompt

- `CASE`: the case folder. `TEXT/INDEX.md` lists every file with a rendered text copy next to it (PDFs, Word, Excel and
  mails are already turned into text there). Read the index first, then every rendered file. Large JSON files: read the
  first part and search the rest.
- `MOCK_URL`: the only base URL the agent's tools may call. The mock serves the case's test customers with the exact
  answers the case lists. `MOCK_URL/health` answers `{"ok": true}`.
- `OUT`: where you write your files.

## What to write

1. `OUT/workflow.json`: the phone agent (format below).
2. `OUT/tests.json`: scripted conversations the harness replays over the platform's chat route against the saved agent.
   A list of objects: `{"name": "...", "variables": {...call variables from the case...}, "turns": ["customer line",
   ...], "expect": ["substring that must appear in the agent's lines or in a tool URL", ...]}` (a service path such
   as `/voice/v1/x.y` is matched against the URLs the agent called; everything else against what the agent said). Six to ten
   conversations: the ordinary paths, the edge paths, the adversarial ones the case describes. Customer lines in the
   language of the calls. Pick test customers that make each path happen (the test environment file says which
   customer returns what, including errors and delays).
3. `OUT/notes.md`: short design notes for a reviewer: which documents you used, where documents disagreed and which
   one won and why (newer wins unless a later decision says otherwise), the call flow as a list of nodes, the tool list
   with paths, and anything you could not settle.

## How to read a case folder

- Read everything once before designing. Mail threads and meeting notes carry decisions that change older documents.
  Order the documents by date; the newest explicit decision wins. Announcement sheets give the exact sentences the
  bank wants spoken; use them verbatim where they apply.
- The test environment file is the truth about the services: paths may be described in an integration document, but
  the field names, response shapes, status codes and delays for each test customer are in that file. The mock answers
  exactly that. Build the tools so they match it.
- Variables the platform hands to every call are named in the case (for example a customer number from the phone menu
  and the call's own date and time). The agent never asks for them and every date decision uses the call's `now`
  variable, never the system clock.
- Money, dates and card numbers are spoken as the case says (currency words, ordinal weeks, masked numbers).

## Platform format (read these files, they are the ground truth)

- `docs/workflow-format.md`: node types, transitions, extraction, `on_enter`, `end_call`.
- `docs/tools-and-code.md`: `api_request` nodes, hooks, `response_mapping`, code nodes.
- `HACKATHON.md` section 11 "Verified on the platform": behaviours we measured on this platform. Follow every item.
- `examples/base-agent.json`: a minimal working agent. `submission/brief-a.workflow.json` (if present): a large
  working agent from the practice round; copy its node shapes (api_request with baked body defaults and `data.*`
  response mappings, code nodes, conversation nodes that speak `{{say}}` set by a code node, `always` transitions),
  not its content.

Rules that cost us runs on the practice round, all mandatory:

- Top level: `{"initial_node": ..., "system_prompt": ..., "nodes": {name: node}, "global_nodes": {}}`. No
  `agent_config`.
- The initial node is a conversation node. Its `on_enter` is a `tts` greeting, never `llm`.
- Speech is deterministic: a code node composes the sentence into `vars["say"]`; the conversation node's `on_enter`
  is `{"type": "tts", "text": "{{say}}"}`. Put the exact sentences from the case in code, with the values filled in.
- Routing on an extracted variable does not fire in the same turn. Pattern: conversation node (extraction) →
  `always` → code node that reads the extracted variables, resets them, computes `vars["route"]` and `vars["say"]` →
  transitions `route == 'x'` (condition on a variable set by code) → next node. Every passthrough node (code,
  api_request) ends with an `always` transition.
- Extraction: every variable has `min_confidence` (0.5 for enums, 0.6 for free text), a `description` that says
  "from the customer's most recent message only" and lists the enum values. Enum values are plain words. Add a
  variable for the customer's question kind if they may ask things back. A mood or tone variable triggers only on
  what the case defines (insults, shouting, complaints about the service), never on mere insistence, impatience or a
  repeated request, which the flow handles as what they are. The platform validates every value a code
  node writes against the variable's schema: a reset to `""` or `None` of an extracted variable is rejected and the
  old value stays for the next turn (`<node>_response.validation_errors` says "rejected by schema validation"). Give
  every extracted variable a documented value such as `none`, reset to that string in code, and treat it as "not said".
- `api_request` nodes: `pre_actions` with one `api_call` whose `parameters.properties` carry `url`, `method`,
  `headers`, `body` with `default` values (never `const`); `{{var}}` placeholders inside defaults; `response_mapping`
  paths start with `data.`; a tool that answered HTTP 500 raises `function_call_error` and the mappings do not run,
  so the next code node must treat missing mapped variables as the error case and say the case's error sentence.
  This holds for every non-2xx status: a 404 and a 500 look the same to the workflow's variables (no status, no
  body). When the case gives different behaviours for "not found" and "technical error" of one service, use the one
  place that can still see the difference: the conversation model. Pattern, only for that service: the api node has
  `suppress_tool_results: false` (the error text, which contains the service's error code, then reaches the model);
  on the error route the code node sends the call to a dedicated conversation node whose `on_enter` is `llm` with a
  short instruction of the form "A tool just failed. If its error text contains <code>, say exactly: <sentence A>.
  Otherwise say exactly: <sentence B>. Nothing else." and an extraction variable (e.g. `err_kind`, enum of the two
  cases plus `none`) so that the next code node ends the call the way the case says for each case. Every other
  sentence stays in code. Say in `notes.md` where this pattern is used.
  Set `max_retries` where the case allows a retry. Only `MOCK_URL` paths.
- Tool shapes follow the case's service contract exactly (paths, the request envelope and field names, the response
  envelope): do not rename fields and do not rely on a hook to reshape the body; put the contract's envelope in the
  body defaults themselves. If the test environment delays an answer, set the action's `config.timeoutMs` above the
  longest delay listed (and a short `connect_retries`); calls with side effects get `maxRetries` 0.
- A tool that can be slow (the case names a delay, or a sentence to say while a service answers): give that
  `api_request` node an `on_enter` of type `tts` with the case's waiting sentence, so the caller hears it before the
  wait; silent `on_enter` only for fast tools.
- Code nodes: only `json`, `re`, `datetime`; never `{{` or `}}` inside code; never raise (wrap in try/except and set a
  fallback route); booleans and numbers arrive as strings, convert with care; read variables with `vars.get`.
- Every path reaches an `end_call` node. The farewell is spoken by the previous conversation node; the `end_call` node
  has `message_mode: "none"` and a silent `on_enter`. Transfers to a human: use the mechanism the case documents
  describe (a service to call, or a sentence followed by ending the call); never invent a queue name.
- Node names are short snake_case; every conversation node has `max_node_turns` (30) and a `max_turn_transition`.
- The customer may ask things back, interrupt with another request, give a partial answer, or hang up; handle these
  in code with a re-ask that repeats only the question.

## Validate while you work

`python3 builder/validate_case.py OUT/workflow.json` runs our lint and the platform's dry run and prints every error.
Run it after writing the file and fix until it prints `ok`. Do not call the platform in any other way, do not save,
do not run simulations: the harness does that.

## Budget

Finish within about 25 minutes of wall time. Read fast, design once, write the files, validate, stop. Your last
message is three lines: the node count, the tool list with paths, and the number of test conversations.
