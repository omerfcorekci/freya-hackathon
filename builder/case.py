"""Case mode: build the phone agent from a client's case folder.

    python3 builder/build.py <case_folder> <mock_url> [--budget-seconds 1700] [--slot final] [--model ...] [--no-chat]

The design step is a Claude Code run (Claude Agent SDK) with the project skill `.claude/skills/build-case-agent`: it
reads the whole folder (every PDF, Word, Excel and mail rendered to text by `builder/casetext.py`) and writes the
workflow plus scripted test conversations. Everything around it is deterministic and reused from the practice builder:
lint, platform dry run, one repair turn on errors, save in place, export, chat-route self-tests, trace. Two traces are
written: `traces/<slot>.log` (plain text, keys masked) and `traces/<slot>.session.jsonl` (every message of the run).
"""
import asyncio, dataclasses, json, os, shutil, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path: sys.path.insert(0, ROOT)
from builder import casetext, freya_ext as fx, lint as lintmod  # noqa: E402
from builder.trace import Trace, Budget  # noqa: E402

SKILL = "build-case-agent"
DEFAULT_MODEL = os.environ.get("BUILDER_MODEL", "claude-opus-5-5")
TRANSIENT = (" 502", " 503", " 504", "timed out", "Connection reset", "RemoteDisconnected")


def _retry(fn, tr, what, tries=6, wait=10):
    for i in range(tries):
        try: return fn()
        except Exception as e:
            msg = str(e)
            if i < tries - 1 and any(t in msg for t in TRANSIENT):
                tr.warn(f"{what}: {msg[:140]} (retry {i + 1}/{tries - 1} in {wait}s)"); time.sleep(wait); wait = min(wait * 2, 60); continue
            raise


async def _run_agent(prompt, session_path, model, max_turns, tr, resume=None):
    from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, TextBlock, ToolUseBlock, query
    kw = dict(cwd=ROOT, model=model, skills=[SKILL], setting_sources=["project"],
              allowed_tools=["Read", "Write", "Edit", "Glob", "Grep", "Bash"], permission_mode="dontAsk", max_turns=max_turns,
              env={"BASH_DEFAULT_TIMEOUT_MS": "300000", "BASH_MAX_TIMEOUT_MS": "600000", "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1"})
    if resume: kw["resume"] = resume
    opts = ClaudeAgentOptions(**kw)
    info = {"session_id": None, "turns": 0, "cost": 0.0, "seconds": 0.0, "last_text": ""}
    t0 = time.time()
    with open(session_path, "a", encoding="utf-8") as out:
        out.write(json.dumps({"start": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "model": model, "resume": resume, "prompt": prompt}) + "\n")
        async for message in query(prompt=prompt, options=opts):
            try: out.write(json.dumps({"type": type(message).__name__, **dataclasses.asdict(message)}, default=str, ensure_ascii=False) + "\n")
            except Exception: out.write(json.dumps({"type": type(message).__name__, "repr": str(message)[:2000]}) + "\n")
            out.flush()
            sid = getattr(message, "session_id", None)
            if sid: info["session_id"] = sid
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock): info["last_text"] = block.text; print(block.text[:400], flush=True)
                    elif isinstance(block, ToolUseBlock): print(f"  [{block.name}] {str(block.input)[:100]}", flush=True)
            elif isinstance(message, ResultMessage):
                info["turns"] = getattr(message, "num_turns", 0) or 0; info["cost"] = getattr(message, "total_cost_usd", 0) or 0
    info["seconds"] = time.time() - t0
    return info


def _counts(wf):
    nodes = wf.get("nodes") or {}
    tools = 0
    for n in nodes.values():
        for act in n.get("pre_actions") or []:
            fn = act.get("function") or {}
            if fn.get("name") == "api_call" or "api_call" in str(fn.get("handler", "")) or "url" in ((fn.get("parameters") or {}).get("properties") or {}): tools += 1
        tools += len(n.get("tools") or [])
    return len(nodes), tools


def _problems(wf, mock_url=""):
    errors, warnings = lintmod.lint(wf)
    if mock_url:        # the final's rule: the phone agent calls only our mock
        import re
        for u in sorted(set(re.findall(r"https?://[^\s\"'<>]+", json.dumps(wf)))):
            if not u.startswith(mock_url): errors.append(f"tool url outside the mock: {u[:120]}")
    if errors: return errors, warnings
    import freya
    try: freya.validate_workflow("validate", wf)
    except Exception as e:
        msg = str(e)
        if any(t in msg for t in TRANSIENT): raise
        errors = ["dryrun: " + msg[:1500]]
    return errors, warnings


def _chat_tests(tests, workflow_id, tr, budget):
    for t in tests:
        if budget.remaining() < 120: tr.test("chat/" + t.get("name", "?"), "SKIP", "budget"); continue
        name = "chat/" + str(t.get("name", "?")); call_id = None; lines = []; status = "FAIL"; detail = ""
        try:
            for turn in list(t.get("turns") or [])[:12]:
                reply, call_id = fx.chat_turn(workflow_id, str(turn), call_id, t.get("variables") or None)
                lines.append(str(reply or ""))
            ev = fx.call_events(call_id) if call_id else {"tools": [], "transcript": [], "errors": []}
            urls = " ".join(str(x.get("url") or x.get("tool") or "") + " " + json.dumps(x.get("args") or {}, ensure_ascii=False) for x in ev.get("tools") or [])
            hay = (" ".join(lines) + " " + " ".join(str(m) for _, m in ev.get("transcript") or []) + " " + urls).lower()
            missing = [e for e in (t.get("expect") or []) if str(e).lower() not in hay]
            status = "PASS" if not missing else "FAIL"
            detail = f"tools={[str(x.get('url') or x.get('tool'))[-40:] for x in ev.get('tools') or []]}" + (f" missing={missing}" if missing else "") + (f" errors={ev.get('errors')[:2]}" if ev.get("errors") else "")
        except Exception as e:
            status = "INCONCLUSIVE" if any(x in str(e) for x in TRANSIENT) else "FAIL"; detail = str(e)[:200]
        finally:
            if call_id:
                try: fx.chat_end(call_id)
                except Exception: pass
        tr.test(name, status, detail[:400])


def run(folder, mock_url, slot="final", budget_seconds=1700, model=DEFAULT_MODEL, no_chat=False, max_turns=150):
    folder = os.path.abspath(folder); mock_url = mock_url.rstrip("/")
    out_dir = os.path.join(ROOT, "out", slot); text_dir = os.path.join(out_dir, "text")
    if os.path.isdir(out_dir): shutil.rmtree(out_dir)          # every run designs from the case folder alone, never from an earlier run's files
    os.makedirs(out_dir, exist_ok=True)
    tr = Trace(os.path.join(ROOT, "traces", f"{slot}.log")); budget = Budget(budget_seconds, tr)
    session_path = os.path.join(ROOT, "traces", f"{slot}.session.jsonl"); open(session_path, "w").close()
    tr.start(folder, mock_url, slot, int(budget_seconds), model)
    status = "error"; saved = None
    try:
        index = casetext.extract_folder(folder, text_dir)
        tr.info(f"case folder: {len(index)} files, {sum(e['chars'] for e in index)} chars of text -> {os.path.relpath(text_dir, ROOT)}/INDEX.md")
        for e in index: tr.info(f"  {e['file']} [{e['kind']}] {e['chars']} chars")
        try:
            import urllib.request
            req = urllib.request.Request(mock_url + "/health", headers={"user-agent": "freya-builder/1.0"})
            with urllib.request.urlopen(req, timeout=15) as r: tr.info(f"mock health {r.status}: {r.read().decode()[:120]}")
        except Exception as e: tr.warn(f"mock health check failed: {str(e)[:160]}")
        prompt = (f"Use the {SKILL} skill. CASE={folder} TEXT={text_dir} MOCK_URL={mock_url} OUT={out_dir}. "
                  f"Write {out_dir}/workflow.json, {out_dir}/tests.json and {out_dir}/notes.md as the skill says.")
        info = await_run(prompt, session_path, model, max_turns, tr)
        tr.model_call(model, f"design the agent from the case folder (Claude Code run, {info['turns']} turns, session {info['session_id']})", seconds=info["seconds"], cost_usd=info["cost"])
        wf_path = os.path.join(out_dir, "workflow.json")
        wf = json.load(open(wf_path, encoding="utf-8"))
        errors, warnings = _retry(lambda: _problems(wf, mock_url), tr, "validate")
        for rep in range(2):
            if not errors: break
            tr.warn(f"workflow has {len(errors)} problem(s): " + " | ".join(errors)[:600])
            if budget.remaining() < 300: tr.warn("no budget for a repair turn"); break
            fix = (f"The harness found problems in {wf_path}. Fix the file so that `python3 builder/validate_case.py {wf_path}` prints ok, "
                   f"then stop. Problems:\n" + "\n".join("- " + e for e in errors[:20]))
            info = await_run(fix, session_path, model, 40, tr, resume=info.get("session_id"))
            tr.model_call(model, f"repair {rep + 1} ({info['turns']} turns)", seconds=info["seconds"], cost_usd=info["cost"])
            wf = json.load(open(wf_path, encoding="utf-8")); errors, warnings = _retry(lambda: _problems(wf, mock_url), tr, "validate")
        n_nodes, n_tools = _counts(wf)
        tr.compile(n_nodes, n_tools, errors, len(warnings))
        for w in warnings[:10]: tr.warn("lint: " + w)
        if errors: raise RuntimeError("workflow still has problems: " + " | ".join(errors)[:400])
        import freya
        saved = _retry(lambda: freya.save_workflow(slot, wf), tr, "save")
        tr.created(slot, saved["workflow_id"], saved["agent_id"], saved.get("version", 1), n_nodes, n_tools)
        export_path = os.path.join(ROOT, "submission", f"{slot}.workflow.json"); os.makedirs(os.path.dirname(export_path), exist_ok=True)
        try:
            _retry(lambda: freya.export_workflow(saved["workflow_id"], export_path), tr, "export")
        except Exception as e:
            tr.warn(f"platform export failed ({str(e)[:120]}); writing the saved workflow locally")
            json.dump({"workflow_id": saved["workflow_id"], "agent_id": saved["agent_id"], "note": "exported locally: the platform did not answer", "workflow": wf}, open(export_path, "w"), ensure_ascii=False, indent=1)
        tr.export(os.path.relpath(export_path, ROOT), n_nodes, n_tools)
        tests_path = os.path.join(out_dir, "tests.json")
        if not no_chat and os.path.exists(tests_path):
            try: tests = json.load(open(tests_path, encoding="utf-8"))
            except Exception as e: tests = []; tr.warn(f"tests.json unreadable: {e}")
            _chat_tests(tests if isinstance(tests, list) else [], saved["workflow_id"], tr, budget)
        status = "ok"
    except Exception as e:
        tr.error(f"{type(e).__name__}: {str(e)[:400]}")
    tr.end(status, f"workflow_id={(saved or {}).get('workflow_id')} agent_id={(saved or {}).get('agent_id')}")
    print(json.dumps({"slot": slot, "workflow_id": (saved or {}).get("workflow_id"), "agent_id": (saved or {}).get("agent_id"),
                      "workflow_file": f"submission/{slot}.workflow.json", "trace": f"traces/{slot}.log", "session": f"traces/{slot}.session.jsonl"}, indent=1))
    return 0 if status == "ok" else 1


def await_run(prompt, session_path, model, max_turns, tr, resume=None):
    return asyncio.run(_run_agent(prompt, session_path, model, max_turns, tr, resume=resume))


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder"); ap.add_argument("mock_url")
    ap.add_argument("--budget-seconds", type=float, default=1700); ap.add_argument("--slot", default="final")
    ap.add_argument("--model", default=DEFAULT_MODEL); ap.add_argument("--no-chat", action="store_true"); ap.add_argument("--max-turns", type=int, default=150)
    a, _ = ap.parse_known_args(argv)
    return run(a.folder, a.mock_url, a.slot, a.budget_seconds, a.model, a.no_chat, a.max_turns)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
