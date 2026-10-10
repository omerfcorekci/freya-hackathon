"""Build the Builder: one command, a brief in, a phone agent out.

    python3 builder/build.py <brief_path> [<more brief paths>...] <tool_api_path> [--budget-seconds 1500] [--slot NAME]
                             [--cases FILE] [--no-sim] [--no-chat] [--offline] [--spec FILE] [--model MODEL]

Steps: extract spec (one model call, plus at most one repair) -> validate -> compile -> lint -> dryRun -> save (in place)
-> export -> self-tests (offline, chat, practice cases when a case file for this brief exists). Writes traces/<slot>.log.
"""
import argparse, json, os, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path: sys.path.insert(0, ROOT)
os.chdir(ROOT)

from builder import extract, lint as lintmod, skeleton
from builder.cfg import build_cfg
from builder.spec_schema import apply_defaults, missing_required, validate_spec, dumps
from builder.toolapi import load_openapi
from builder.trace import Budget, Trace


def parse_args(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", help="brief file(s) followed by the tool API json")
    ap.add_argument("--budget-seconds", type=float, default=1500)
    ap.add_argument("--slot", default=None, help="workflow slot (default: stem of the last brief file)")
    ap.add_argument("--cases", default=None, help="practice cases json for this brief (default: auto-detect)")
    ap.add_argument("--brief-letter", default=None, help="which cases to run from the cases file (A or B); default from the brief file name")
    ap.add_argument("--no-sim", action="store_true"); ap.add_argument("--no-chat", action="store_true")
    ap.add_argument("--offline", action="store_true", help="compile and lint only; no platform, no model when --spec is given")
    ap.add_argument("--spec", default=None, help="reuse an extracted spec file instead of calling the model")
    ap.add_argument("--model", default=extract.DEFAULT_MODEL)
    a = ap.parse_args(argv)
    briefs = [p for p in a.paths if not p.endswith(".json")]; apis = [p for p in a.paths if p.endswith(".json")]
    if not briefs or len(apis) != 1: ap.error("give one or more brief files and exactly one tool API json")
    a.briefs = briefs; a.api_path = apis[0]
    a.slot = a.slot or os.path.splitext(os.path.basename(briefs[-1]))[0]
    return a


def main(argv=None):
    a = parse_args(argv if argv is not None else sys.argv[1:])
    out_dir = os.path.join(ROOT, "out", a.slot); os.makedirs(out_dir, exist_ok=True)
    os.makedirs(os.path.join(ROOT, "submission"), exist_ok=True)
    tr = Trace(os.path.join(ROOT, "traces", a.slot + ".log")); budget = Budget(a.budget_seconds, tr)
    tr.start(" ".join(a.briefs), a.api_path, a.slot, int(a.budget_seconds), a.model)
    status = "ok"; state = {"workflow_id": None, "agent_id": None}
    try:
        api = load_openapi(a.api_path)
        tr.info(f"tool api: {len(api.names())} tools {api.names()} base={api.base_url}")
        # 1. spec
        if a.spec:
            spec = json.load(open(a.spec)); tr.info(f"spec loaded from {a.spec} (no model call)")
        else:
            spec = extract.extract_spec(a.briefs, api, tr, a.model)
            if not spec: raise RuntimeError("spec extraction returned nothing")
            json.dump(spec, open(os.path.join(out_dir, "spec.raw.json"), "w"), indent=1)
        spec, defaulted = apply_defaults(spec)
        problems = validate_spec(spec, api.enums())
        if problems and not a.spec and budget.allows(120, "spec repair"):
            tr.spec("problems: " + " | ".join(problems)[:1500])
            fixed = extract.repair_spec(spec, problems, a.briefs, api, tr, a.model)
            if fixed:
                spec, defaulted = apply_defaults(fixed); problems = validate_spec(spec, api.enums())
        missing = missing_required(spec)
        tr.spec(f"{'ok' if not problems else 'with problems'} required_missing={missing} defaulted={len(defaulted)} problems={len(problems)}")
        for p in problems: tr.warn("spec: " + p)
        open(os.path.join(out_dir, "spec.json"), "w").write(dumps(spec))
        # 2. compile
        cfg = build_cfg(spec, api)
        wf = skeleton.compile_workflow(spec, api, cfg)
        n_nodes, n_tools = skeleton.counts(wf)
        errors, warnings = lintmod.lint(wf, known_vars=set(wf.get("test_variables") or {}))
        tr.compile(n_nodes, n_tools, errors, len(warnings))
        for w in warnings[:30]: tr.warn("lint: " + w)
        for e in errors: tr.error("lint: " + e)
        wf_path = os.path.join(out_dir, "workflow.json"); json.dump(wf, open(wf_path, "w"), indent=1)
        tr.info(f"workflow written {wf_path} size={os.path.getsize(wf_path)} bytes")
        if errors: raise RuntimeError(f"lint found {len(errors)} errors")
        if a.offline:
            tr.info("offline mode: stopping before the platform")
        else:
            import freya
            # 3. dry run, save, export
            t0 = time.time(); freya.validate_workflow(a.slot, wf); tr.freya(f"dryrun ok {time.time() - t0:.1f}s")
            t0 = time.time(); saved = freya.save_workflow(a.slot, wf); tr.created(a.slot, saved["workflow_id"], saved["agent_id"], saved.get("version", 1), n_nodes, n_tools)
            state.update(saved); json.dump(state, open(os.path.join(out_dir, "state.json"), "w"), indent=1)
            export_path = os.path.join(ROOT, "submission", a.slot + ".workflow.json")
            freya.export_workflow(saved["workflow_id"], export_path)
            exported = json.load(open(export_path)); en, et = skeleton.counts(exported.get("workflow") or {})
            tr.export(os.path.relpath(export_path, ROOT), en, et)
            # 4. self-tests
            from builder.selftest import offline as st_offline, chat as st_chat, cases as st_cases
            st_offline.run(spec, cfg, tr)
            if not a.no_chat: st_chat.run(spec, cfg, api, saved["workflow_id"], tr, budget)
            if not a.no_sim: st_cases.run(a, spec, saved["agent_id"], tr, budget)
    except Exception as e:
        status = "error"; tr.error(f"{type(e).__name__}: {str(e)[:800]}")
    finally:
        extra = f"workflow_id={state.get('workflow_id')} agent_id={state.get('agent_id')}"
        tr.end(status, extra)
        if state.get("workflow_id"):
            print(json.dumps({"slot": a.slot, "workflow_id": state["workflow_id"], "agent_id": state["agent_id"],
                              "workflow_file": f"submission/{a.slot}.workflow.json", "trace": f"traces/{a.slot}.log"}, indent=1))
    return 0 if status == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
