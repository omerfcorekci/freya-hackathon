"""Node and transition constructors in the shapes docs/workflow-format.md describes."""

# ---- conditions -------------------------------------------------------------------------------------------------

def c_eq(var, val): return {"variable": var, "operator": "equals", "operand": str(val)}
def c_neq(var, val): return {"variable": var, "operator": "not_equals", "operand": str(val)}
def c_gt(var, val): return {"variable": var, "operator": "greater_than", "operand": val}
def c_lt(var, val): return {"variable": var, "operator": "less_than", "operand": val}
def c_set(var): return {"variable": var, "operator": "is_set"}
def c_unset(var): return {"variable": var, "operator": "is_not_set"}

def group(*conds):
    """Top-level OR group. Variable conditions must live inside a group."""
    return {"logic": "or", "conditions": list(conds)}
def both(*conds):
    """AND, nested inside the top-level OR as the docs require."""
    return {"logic": "or", "conditions": [{"logic": "and", "conditions": list(conds)}]}
def bool_true(var):
    """A boolean from an API arrives as 'true' or 'True'. Test both."""
    return group(c_eq(var, "true"), c_eq(var, "True"))

# ---- transitions ------------------------------------------------------------------------------------------------

def t(target, description, condition, is_tool_call=False):
    d = {"target_node": target, "description": description, "condition": condition}
    if is_tool_call: d["is_tool_call"] = True
    return d
def t_always(target, description="always"): return t(target, description, {"operator": "always"})
def t_eq(var, val, target, description=None): return t(target, description or f"{var} is {val}", group(c_eq(var, val)))
def t_in(var, vals, target, description=None): return t(target, description or f"{var} in {list(vals)}", group(*[c_eq(var, v) for v in vals]))
def t_set(var, target, description=None): return t(target, description or f"{var} is set", group(c_set(var)))
def t_bool(var, target, description=None): return t(target, description or f"{var} is true", bool_true(var))
def t_gt(var, val, target, description=None): return t(target, description or f"{var} > {val}", group(c_gt(var, val)))
def t_intent(desc, target): return t(target, desc, {"operator": "matches_intent", "description": desc})

# ---- extraction -------------------------------------------------------------------------------------------------

def ext(name, description, typ="string", enum=None, min_confidence=0.6, pattern=None):
    d = {"name": name, "type": typ, "description": description, "min_confidence": min_confidence}
    if enum: d["enum_values"] = list(enum)
    if pattern: d["validation_pattern"] = pattern
    return d

# ---- nodes ------------------------------------------------------------------------------------------------------

def conversation(name, task, transitions, *, on_enter=None, first_entry_only=False, tools=None, extraction=None,
                 max_turns=30, max_turn_transition=None, suppress_tool_results=False, role=""):
    n = {"name": name, "node_type": "conversation", "task_message": task, "role_message": role,
         "on_enter": on_enter or {"type": "llm"}, "on_enter_first_entry_only": bool(first_entry_only),
         "tools": list(tools or []), "extraction_schema": list(extraction or []), "transitions": list(transitions),
         "max_node_turns": max_turns, "interruptible": True, "suppress_tool_results": bool(suppress_tool_results),
         "truncation_strategy": "keep_all", "disable_inactivity_monitor": False}
    if max_turn_transition: n["max_turn_transition"] = max_turn_transition
    return n

def tts(text): return {"type": "tts", "text": text}
def silent(): return {"type": "silent"}

def code_node(name, code, default_target, transitions=None, timeout_ms=10000):
    """A passthrough code node. `transitions` may add conditional routes before the mandatory `always`."""
    trans = list(transitions or [])
    if not trans or trans[-1]["condition"].get("operator") != "always": trans.append(t_always(default_target))
    return {"name": name, "node_type": "code", "passthrough": True, "passthrough_default_transition": default_target,
            "on_enter": silent(), "disable_inactivity_monitor": True,
            "pre_actions": [{"type": "function", "function": {"name": "code_exec", "handler": "__function__:code_exec",
                             "parameters": {"type": "object", "properties": {
                                 "code": {"type": "string", "default": code},
                                 "timeout_ms": {"type": "number", "default": timeout_ms}}}}}],
            "transitions": trans}

def api_node(name, tool, default_target, transitions=None, response_mapping=None, suppress=True):
    """A passthrough api_request node: the engine runs `tool` on entry, no model discretion."""
    trans = list(transitions or [])
    if not trans or trans[-1]["condition"].get("operator") != "always": trans.append(t_always(default_target))
    n = {"name": name, "node_type": "api_request", "passthrough": True, "passthrough_default_transition": default_target,
         "on_enter": silent(), "disable_inactivity_monitor": True, "suppress_tool_results": bool(suppress),
         "pre_actions": [tool], "transitions": trans}
    if response_mapping: n["response_mapping"] = list(response_mapping)
    return n

def end_node(name, function_name, spoken=None):
    params = {"message_mode": {"type": "string", "default": "custom" if spoken else "none"}}
    if spoken: params["spoken_message"] = {"type": "string", "default": spoken}
    return {"name": name, "node_type": "end_call", "on_enter": silent(), "disable_inactivity_monitor": True, "transitions": [],
            "terminal": {"type": "function", "function": {"name": function_name, "handler": "__function__:end_call",
                                                          "parameters": {"type": "object", "properties": params}}}}
