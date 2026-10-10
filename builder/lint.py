"""Static checks on a generated workflow: the checklist of docs/tools-and-code.md plus graph checks.

Returns (errors, warnings). Errors block a save; warnings go to the trace.
"""
import re

CALL_VARS = {"customer_id", "first_name", "last_name", "title", "now"}
SANDBOX_MODULES = {"json", "re", "datetime"}


def _walk(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items(): yield from _walk(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj): yield from _walk(v, f"{path}[{i}]")
    else:
        yield path, obj


def _tools_of(node):
    out = list(node.get("tools") or [])
    out += list(node.get("pre_actions") or [])
    if node.get("terminal"): out.append(node["terminal"])
    return out


def lint(workflow, known_vars=None):
    errors, warnings = [], []
    nodes = workflow.get("nodes") or {}
    initial = workflow.get("initial_node")
    if not initial or initial not in nodes: errors.append(f"initial_node '{initial}' is not a node")
    if workflow.get("agent_config"): warnings.append("agent_config present: the platform fills it in; leave it out")

    # null values anywhere
    for path, v in _walk(workflow):
        if v is None: errors.append(f"null value at {path}")

    written = set(known_vars or set()) | CALL_VARS
    written |= set((workflow.get("test_variables") or {}).keys())
    used = []   # (path, var)
    end_nodes = set()

    for key, node in nodes.items():
        nt = node.get("node_type")
        if node.get("name") != key: warnings.append(f"node '{key}': name '{node.get('name')}' differs from its key")
        if nt == "conversation":
            if node.get("pre_actions"): errors.append(f"node '{key}': pre_actions on a conversation node are stripped by the platform")
            if node.get("max_node_turns") and not node.get("max_turn_transition"): warnings.append(f"node '{key}': max_node_turns without max_turn_transition")
            for e in node.get("extraction_schema") or []:
                if "min_confidence" not in e: errors.append(f"node '{key}': extraction '{e.get('name')}' has no min_confidence")
                written.add(e.get("name"))
        elif nt in ("api_request", "code"):
            if node.get("tools"): errors.append(f"node '{key}': tools on a {nt} node are stripped by the platform")
            if not node.get("passthrough"): warnings.append(f"node '{key}': {nt} node is not passthrough")
            trans = node.get("transitions") or []
            if not trans or trans[-1].get("condition", {}).get("operator") != "always": errors.append(f"node '{key}': passthrough node must end with an always transition")
            for m in node.get("response_mapping") or []: written.add(m.get("variable"))
        elif nt == "end_call":
            end_nodes.add(key)
            if node.get("transitions"): errors.append(f"node '{key}': end_call node must have no transitions")
            if not node.get("terminal"): errors.append(f"node '{key}': end_call node needs a terminal")
        else:
            errors.append(f"node '{key}': unknown node_type {nt}")
        for tr in node.get("transitions") or []:
            tgt = tr.get("target_node")
            if tgt not in nodes and tgt != "__previous__": errors.append(f"node '{key}': transition to unknown node '{tgt}'")
            cond = tr.get("condition") or {}
            if cond.get("logic") == "and": errors.append(f"node '{key}': top-level condition uses logic=and; nest it inside an or group")
            for path, v in _walk(cond):
                if path.endswith("operand") and isinstance(v, bool): errors.append(f"node '{key}': boolean operand in a transition; use strings")
        for tool in _tools_of(node):
            fn = tool.get("function") or {}; name = fn.get("name", "?")
            params = (fn.get("parameters") or {}).get("properties") or {}
            for path, v in _walk(params):
                if path.endswith(".const") or path == "const": errors.append(f"node '{key}' tool '{name}': const is never baked; use default")
            if fn.get("handler") == "__function__:api_call":
                body = params.get("body") or {}
                if "default" in body and "properties" not in body: errors.append(f"node '{key}' tool '{name}': body given as one default object; declare leaves under body.properties")
                for f, leaf in (body.get("properties") or {}).items():
                    if "default" not in leaf: warnings.append(f"node '{key}' tool '{name}': body field '{f}' has no default (model fills it with no placeholder name)")
                if nt == "conversation" and "CALL" not in (fn.get("description") or ""): warnings.append(f"node '{key}' tool '{name}': description should say when to CALL it")
                if nt == "conversation":
                    for m in tool.get("response_mapping") or []: written.add(m.get("variable"))
                for m in (tool.get("response_mapping") or []) + (node.get("response_mapping") or [] if nt != "conversation" else []):
                    if not str(m.get("path", "")).startswith("data."): errors.append(f"node '{key}' tool '{name}': mapping path '{m.get('path')}' must start with data.")
                written.update({f"{name}_response", f"{name}_success_count", f"{name}_failure_count", f"{name}_status_code", f"{name}_args"})
                for hook in ("pre_process_code", "post_process_code"):
                    src = tool.get(hook) or ""
                    if "{{" in src or "}}" in src: errors.append(f"node '{key}' tool '{name}': {hook} contains {{{{ or }}}}")
                    _check_imports(src, f"node '{key}' tool '{name}' {hook}", errors)
                    written.update(_assigned_vars(src))
            elif fn.get("handler") == "__function__:code_exec":
                src = ((params.get("code") or {}).get("default")) or ""
                if "{{" in src or "}}" in src: errors.append(f"node '{key}': code contains {{{{ or }}}}")
                if "try" not in src: warnings.append(f"node '{key}': code has no try/except")
                _check_imports(src, f"node '{key}' code", errors)
                written.update(_assigned_vars(src))
                written.update({f"{key}_response", f"{key}_success_count", f"{key}_failure_count", f"{key}_status_code"})
        # variables used in prompts, on_enter text, tool defaults
        for path, v in _walk({"task_message": node.get("task_message"), "on_enter": node.get("on_enter"), "loop_prompt": node.get("loop_prompt"),
                              "tools": node.get("tools"), "pre_actions": node.get("pre_actions"), "terminal": node.get("terminal"), "transitions": node.get("transitions")}):
            if isinstance(v, str):
                for var in re.findall(r"{{\s*([A-Za-z_][\w.]*)\s*(?::json)?\s*}}", v): used.append((f"{key}.{path}", var))

    # reachability
    if initial in nodes:
        seen = set(); stack = [initial]
        while stack:
            k = stack.pop()
            if k in seen: continue
            seen.add(k)
            for tr in nodes[k].get("transitions") or []:
                if tr.get("target_node") in nodes: stack.append(tr["target_node"])
            if nodes[k].get("max_turn_transition") in nodes: stack.append(nodes[k]["max_turn_transition"])
            if nodes[k].get("passthrough_default_transition") in nodes: stack.append(nodes[k]["passthrough_default_transition"])
        for k in nodes:
            if k not in seen: warnings.append(f"node '{k}' is unreachable from initial_node")
        # every reachable node reaches an end_call
        rev = {k: set() for k in nodes}
        for k, n in nodes.items():
            for tr in n.get("transitions") or []:
                if tr.get("target_node") in nodes: rev[tr["target_node"]].add(k)
            if n.get("max_turn_transition") in nodes: rev[n["max_turn_transition"]].add(k)
        can_end = set(); stack = list(end_nodes)
        while stack:
            k = stack.pop()
            if k in can_end: continue
            can_end.add(k); stack.extend(rev[k])
        for k in seen:
            if k not in can_end: errors.append(f"node '{k}' cannot reach any end_call node")
    if not end_nodes: errors.append("no end_call node")

    # model-filled tool params are the fields the model is asked for; only flag true unknowns
    model_filled = set()
    for n in nodes.values():
        for tool in n.get("tools") or []:
            body = (((tool.get("function") or {}).get("parameters") or {}).get("properties") or {}).get("body") or {}
            for f, leaf in (body.get("properties") or {}).items():
                if str(leaf.get("default", "")) == "{{" + f + "}}": model_filled.add(f)
    for where, var in used:
        base = var.split(".")[0]
        if var in written or base in written or var in model_filled: continue
        if base.startswith("system") or base.startswith("call"): continue
        warnings.append(f"{where}: {{{{{var}}}}} is never written by a code node, mapping, extraction or call variable")
    return errors, warnings


def _check_imports(src, where, errors):
    for m in re.finditer(r"^\s*(?:import|from)\s+([A-Za-z_][\w]*)", src, flags=re.M):
        if m.group(1) not in SANDBOX_MODULES: errors.append(f"{where}: import of '{m.group(1)}' is not available in the sandbox")


def _assigned_vars(src):
    out = set(re.findall(r"vars\[\s*['\"]([A-Za-z_][\w]*)['\"]\s*\]\s*=", src))
    for m in re.finditer(r"#\s*lint-vars:\s*([\w ,]+)", src): out.update(x.strip() for x in m.group(1).split(",") if x.strip())
    return out


if __name__ == "__main__":
    import json, sys
    wf = json.load(open(sys.argv[1]))
    wf = wf.get("workflow", wf)
    e, w = lint(wf)
    for x in e: print("ERROR", x)
    for x in w: print("WARN ", x)
    print(f"{len(e)} errors, {len(w)} warnings"); sys.exit(1 if e else 0)
