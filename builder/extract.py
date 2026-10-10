"""Spec extraction: the one creative step. A model reads the brief (any form) and fills the spec schema.

Runs through the Claude Agent SDK with a JSON-schema structured output, so it authenticates like Claude Code does
(login or ANTHROPIC_API_KEY). No tools: the model sees only the brief text and the tool API summary we give it.
"""
import asyncio, json, os, re, time

from builder.spec_schema import SPEC_SCHEMA, dumps

DEFAULT_MODEL = os.environ.get("BUILDER_MODEL", "claude-opus-5-5")

SYSTEM = """You turn a bank's collections-call brief into structured data for a program that builds a phone agent.
The program knows nothing about this bank. Everything it needs must be in your output, taken from the brief you are given.

Rules:
- Take every value from the brief in front of you. If the brief does not say, leave the field empty ("" / [] / 0). Never fill
  a value from memory of another bank or another brief. A wrong confident value is worse than an empty one.
- The brief may be one clean specification or several raw documents (an email, a policy extract, a memo that changes the
  policy, a code list). A later document that changes a rule wins over the earlier one. A code list defines the exact
  outcome, reason, queue and note values.
- Outcome, reason, queue, note-reason and identity-field values must be spelled exactly as the tool API spells them.
  The tool API summary lists the allowed values where the API constrains them.
- Call variables are written as {{variable_name}} inside sentences (for example {{title}} {{last_name}}).
- Sentences the agent must say verbatim go in verbatim. Mandatory sentences, sympathy lines, explanations: copy the wording.
- Fill meta.source_quotes with the brief sentence behind every non-trivial value (bands, deadlines, holidays, attempts,
  outcomes, identity questions, callback window, sentences). Fill meta.notes with any rule you could not express in a field.
- Dates are YYYY-MM-DD. Times are HH:MM. Weekdays are numbers, Monday = 0.
- bands: one entry per lateness band, in order, with the deadline rule and the number of persuasion attempts.
- persuasion.attempts: one entry per attempt the brief describes, with what amount and what date it proposes; list the band
  names it applies to, or leave bands empty when it applies to every band.
- closing.outcomes: the full outcome table, every outcome with its allowed reasons (empty list when it takes none).
Return only the JSON object."""


def read_briefs(paths):
    parts = []
    for p in paths:
        with open(p, encoding="utf-8") as f: parts.append(f"===== FILE: {os.path.basename(p)} =====\n{f.read().strip()}\n")
    return "\n".join(parts)


def api_summary(api):
    lines = [f"Base URL: {api.base_url}"]
    for name in api.names():
        t = api.tool(name)
        lines.append(f"\n{name}: {t['summary']}")
        for fn, f in t["fields"].items():
            bits = [f["type"]]
            if f.get("enum"): bits.append("one of " + ", ".join(map(str, f["enum"])))
            if f.get("required"): bits.append("required")
            if f.get("description"): bits.append(f["description"])
            lines.append(f"  - {fn}: " + "; ".join(bits))
        if t.get("response_fields"): lines.append("  returns: " + ", ".join(t["response_fields"]))
    return "\n".join(lines)


def _extract_json(text):
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m: return None
    try: return json.loads(m.group(0))
    except Exception: return None


async def _query_json(prompt, model, trace, purpose, max_turns=4):
    from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, TextBlock, query
    opts = ClaudeAgentOptions(model=model, system_prompt=SYSTEM, allowed_tools=[], permission_mode="dontAsk", max_turns=max_turns,
                              setting_sources=[], output_format={"type": "json_schema", "schema": SPEC_SCHEMA}, cwd=os.getcwd())
    t0 = time.time(); text = ""; result = None; used_model = model
    async for m in query(prompt=prompt, options=opts):
        if isinstance(m, AssistantMessage):
            used_model = getattr(m, "model", None) or used_model
            for b in m.content:
                if isinstance(b, TextBlock): text += b.text
        elif isinstance(m, ResultMessage):
            result = m
    secs = time.time() - t0
    usage = (getattr(result, "usage", None) or {}) if result else {}
    tin = usage.get("input_tokens"); tout = usage.get("output_tokens")
    if usage.get("cache_read_input_tokens"): tin = (tin or 0) + usage["cache_read_input_tokens"]
    trace.model_call(used_model, purpose, secs, tin, tout, getattr(result, "total_cost_usd", None) if result else None)
    data = getattr(result, "structured_output", None) if result else None
    if isinstance(data, str):
        try: data = json.loads(data)
        except Exception: data = None
    if not isinstance(data, dict): data = _extract_json(text)
    if not isinstance(data, dict):
        trace.error(f"extraction returned no JSON (subtype={getattr(result, 'subtype', None)}, is_error={getattr(result, 'is_error', None)})")
    return data


def extract_spec(brief_paths, api, trace, model=DEFAULT_MODEL):
    prompt = ("TOOL API SUMMARY (the only tools the phone agent can call):\n" + api_summary(api) +
              "\n\nTHE BRIEF (one or more files; a later file that changes a rule wins):\n\n" + read_briefs(brief_paths) +
              "\n\nProduce the spec JSON for this brief.")
    return asyncio.run(_query_json(prompt, model, trace, f"extract spec from {', '.join(os.path.basename(p) for p in brief_paths)}"))


def repair_spec(spec, problems, brief_paths, api, trace, model=DEFAULT_MODEL):
    prompt = ("TOOL API SUMMARY:\n" + api_summary(api) + "\n\nTHE BRIEF:\n\n" + read_briefs(brief_paths) +
              "\n\nA first extraction produced this spec:\n" + dumps(spec) +
              "\n\nValidation found these problems:\n- " + "\n- ".join(problems) +
              "\n\nReturn the complete corrected spec JSON. Fix only what the brief supports; where the brief is silent, leave the field empty.")
    return asyncio.run(_query_json(prompt, model, trace, f"repair spec ({len(problems)} problems)"))


if __name__ == "__main__":
    import sys
    from builder.toolapi import load_openapi
    from builder.trace import Trace
    from builder.spec_schema import apply_defaults, validate_spec, missing_required
    api = load_openapi(sys.argv[1]); briefs = sys.argv[2:]
    tr = Trace(os.path.join(os.environ.get("TRACE_DIR", "out"), "extract-test.log"))
    spec = extract_spec(briefs, api, tr)
    if spec:
        os.makedirs("out", exist_ok=True)
        slot = os.path.splitext(os.path.basename(briefs[-1]))[0]
        open(f"out/{slot}.spec.json", "w").write(dumps(spec))
        spec2, defaulted = apply_defaults(spec)
        print("missing required:", missing_required(spec2)); print("defaulted:", defaulted)
        for p in validate_spec(spec2, api.enums()): print("PROBLEM", p)
    tr.end("ok")
