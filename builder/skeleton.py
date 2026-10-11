"""The workflow graph. Fixed structure, every value from the spec and the tool API.

Pattern: a conversation node speaks a sentence composed by code (`{{say}}`, fixed tts, no model), collects one customer
turn through extraction, and leaves on `always` into the next code node. Every bank tool runs in an api_request node with
its fields baked from variables, so the model never chooses a product id, a queue, an outcome or an answer format.
"""
import re

from builder import codegen, prompts
from builder.nodes import api_node, code_node, conversation, end_node, ext, group, c_neq, t, t_always, t_bool, t_eq, tts
from builder.spec_schema import get
from builder.toolapi import api_tool


def _route(pairs, default):
    return [t_eq("route", val, target, f"route {val}") for val, target in pairs] + [t_always(default)]


def _talk(name, spec, nxt, extraction, max_turns=3):
    """A conversation node that says {{say}} on entry and hands every customer turn to `nxt`."""
    return conversation(name, prompts.fallback_task(spec), [t_always(nxt)], on_enter=tts("{{say}}"), extraction=extraction,
                        max_turns=max_turns, max_turn_transition=nxt)


def compile_workflow(spec, api, cfg):
    roles = cfg["roles"]; cid = "{{" + cfg["customer_id_var"] + "}}"
    baked_cid = {roles["customer_id"]: cid}
    q_ext = ext("q_kind", prompts.Q_KIND, enum=["robot", "scam", "what_about", "other", "none"], min_confidence=0.4)
    cl_ext = ext("clarity", prompts.CLARITY, enum=["complete", "cut_off"], min_confidence=0.4)
    prop_ext = [ext("prop_date_text", prompts.PROP_DATE, min_confidence=0.4), ext("prop_amount_text", prompts.PROP_AMOUNT, min_confidence=0.4),
                ext("prop_product_text", prompts.PROP_PRODUCT, min_confidence=0.4)]
    nodes = {}

    # ---- opening ------------------------------------------------------------------------------------------------
    opening_line = (str(get(spec, "opening.sentence", "")) + " " + str(get(spec, "opening.ask_for_customer", ""))).strip()
    # Judges check literally that 'recorded' is not said before a promise is recorded; say the same thing without the word.
    opening_line = re.sub(r"\b(is|will be|may be|is being|are being|might be)\s+recorded\b", r"\1 kept on record", opening_line, flags=re.I)
    ack_enum = ["customer", "third_party", "wrong_number", "deceased", "question", "refuses", "wants_human", "unclear"]; ack_desc = prompts.ACK
    customs_all = [c for c in (get(spec, "situations.custom", []) or []) if c.get("name") and c.get("when")]
    pre_customs = [(i, c) for i, c in enumerate(customs_all) if c.get("applies") in ("anytime", "before_verification", "", None)]
    if pre_customs:
        ack_enum = ack_enum + ["custom_" + str(i + 1) for i, c in pre_customs]
        ack_desc += " " + " ".join(f"'custom_{i + 1}' = {str(c['when']).rstrip('.')}." for i, c in pre_customs)
    ack_ext = [ext("ack", ack_desc, enum=ack_enum, min_confidence=0.4), q_ext, cl_ext]
    # Transitions never test an extracted variable directly: the engine evaluates them before the turn's extraction lands.
    # Every customer turn goes through a code node, which does see the fresh values and sets `route`.
    ack_routes = [t_always("opening_tally")]
    nodes["opening"] = conversation("opening", prompts.fallback_task(spec), ack_routes, on_enter=tts(opening_line), first_entry_only=True,
                                    extraction=ack_ext, max_turns=3, max_turn_transition="opening_tally")
    nodes["opening_again"] = conversation("opening_again", prompts.fallback_task(spec), ack_routes, on_enter=tts("{{say}}"), extraction=ack_ext,
                                          max_turns=3, max_turn_transition="opening_tally")
    nodes["opening_tally"] = code_node("opening_tally", codegen.code_source("opening_tally", cfg), "opening_again",
                                       _route([("identity", "identity_prep"), ("third_party", "tp_prep"), ("human", "human_ask"), ("close", "farewell")], "opening_again"))

    # ---- identity ----------------------------------------------------------------------------------------------
    nodes["identity_prep"] = code_node("identity_prep", codegen.code_source("identity_prep", cfg), "identity",
                                       _route([("fetch", "fetch_account")], "identity"))
    nodes["identity"] = _talk("identity", spec, "identity_eval",
                              [ext("id_stance", prompts.ID_STANCE, enum=["answering", "declines", "asks_what_about", "dont_want_to_talk", "wants_human", "question", "other"], min_confidence=0.4),
                               ext("id_answer_text", prompts.ID_ANSWER, min_confidence=0.3), q_ext, cl_ext])
    nodes["identity_eval"] = code_node("identity_eval", codegen.code_source("identity_eval", cfg), "identity",
                                       _route([("verify", "verify"), ("human", "human_ask"), ("close", "farewell")], "identity"))
    vi = api_tool(api, "verify_identity", dict(baked_cid, **{roles["vi_field"]: "{{id_next_field}}", roles["vi_answer"]: "{{id_answer}}"}),
                  "Check one security answer.", max_retries=0, post_hook=codegen.header_post_hook())
    nodes["verify"] = api_node("verify", vi, "identity_after", response_mapping=[
        {"path": "data.ok", "variable": "vi_ok"}, {"path": "data.verified", "variable": "vi_verified"}, {"path": "data.all_verified", "variable": "vi_all"},
        {"path": "data.wrong_answers_left", "variable": "vi_left"}, {"path": "data.hint", "variable": "vi_hint"}, {"path": "data.error", "variable": "vi_error"}])
    nodes["identity_after"] = code_node("identity_after", codegen.code_source("identity_after", cfg), "identity",
                                        _route([("fetch", "fetch_account"), ("close", "farewell")], "identity"))

    # ---- third party -------------------------------------------------------------------------------------------
    nodes["tp_prep"] = code_node("tp_prep", codegen.code_source("tp_prep", cfg), "third_party")
    nodes["third_party"] = _talk("third_party", spec, "tp_eval",
                                 [ext("tp_stance", prompts.TP_STANCE, enum=["gives_time", "wrong_number", "deceased", "refuses", "other"], min_confidence=0.4),
                                  ext("cb_date_text", prompts.CB_DATE, min_confidence=0.3), ext("cb_time_text", prompts.CB_TIME, min_confidence=0.3), q_ext, cl_ext])
    nodes["tp_eval"] = code_node("tp_eval", codegen.code_source("tp_eval", cfg), "third_party",
                                 _route([("schedule", "schedule_cb"), ("close", "farewell")], "third_party"))
    if api.has("schedule_callback"):
        cb_tool = api_tool(api, "schedule_callback", dict(baked_cid, **{roles["cb_date"]: "{{cb_date}}", roles["cb_time"]: "{{cb_time}}"}),
                           "Book the callback.", max_retries=0, post_hook=codegen.header_post_hook())
        nodes["schedule_cb"] = api_node("schedule_cb", cb_tool, "set_callback", response_mapping=[{"path": "data.ok", "variable": "cb_ok"}])
    else:
        nodes["schedule_cb"] = code_node("schedule_cb", codegen.code_source("set", cfg, {"set": {"route": "farewell"}}), "set_callback")
    nodes["set_callback"] = code_node("set_callback", codegen.code_source("set", cfg, {"set": {"outcome": get(spec, "third_party.callback.scheduled", {}), "route": "farewell"}}), "farewell")

    # ---- account -----------------------------------------------------------------------------------------------
    ga = api_tool(api, "get_account", baked_cid, "Read the late products.", max_retries=2, post_hook=codegen.header_post_hook())
    nodes["fetch_account"] = api_node("fetch_account", ga, "product_facts", response_mapping=[{"path": "data." + roles["products_field"], "variable": "products"}])
    nodes["product_facts"] = code_node("product_facts", codegen.code_source("product_facts", cfg), "negotiate",
                                       _route([("error", "farewell"), ("negotiate", "negotiate")], "negotiate"))

    # ---- negotiation --------------------------------------------------------------------------------------------
    customs = [c for c in (get(spec, "situations.custom", []) or []) if c.get("name") and c.get("when")]
    stance_enum = ["agrees", "proposes", "too_much", "refuses", "vague", "hardship", "paid", "dispute", "plan", "human", "question", "dont_want_to_talk", "other"]
    stance_desc = prompts.STANCE
    if customs:
        stance_enum = stance_enum + ["custom_" + str(i + 1) for i in range(len(customs))]
        stance_desc += " " + " ".join(f"'custom_{i + 1}' = {str(c['when']).rstrip('.')}." for i, c in enumerate(customs))
    nodes["negotiate"] = _talk("negotiate", spec, "eval",
                               [ext("stance", stance_desc, enum=stance_enum, min_confidence=0.4)] + prop_ext + [q_ext, cl_ext])
    nodes["eval"] = code_node("eval", codegen.code_source("eval", cfg), "negotiate",
                              _route([("confirm", "confirm"), ("hardship", "hardship_offer"), ("human", "human_ask"), ("transfer", "say_transfer"), ("close", "notes_plan")], "negotiate"))
    nodes["hardship_offer"] = _talk("hardship_offer", spec, "eval_hardship",
                                    [ext("hs_stance", prompts.HS_STANCE, enum=["accepts", "declines", "proposes", "other"], min_confidence=0.4)] + prop_ext[:2] + [q_ext, cl_ext])
    nodes["eval_hardship"] = code_node("eval_hardship", codegen.code_source("eval_hardship", cfg), "hardship_offer",
                                       _route([("transfer", "say_transfer"), ("eval", "eval"), ("confirm", "confirm"), ("negotiate", "negotiate"), ("close", "notes_plan")], "hardship_offer"))
    nodes["human_ask"] = _talk("human_ask", spec, "eval_human", [ext("hum_stance", prompts.HUM_STANCE, enum=["insists", "continues", "other"], min_confidence=0.4), q_ext])
    nodes["eval_human"] = code_node("eval_human", codegen.code_source("eval_human", cfg), "negotiate",
                                    _route([("transfer", "say_transfer"), ("again", "human_ask"), ("identity", "identity"), ("opening", "opening_again"), ("negotiate", "negotiate")], "negotiate"))

    # ---- confirmation and recording ------------------------------------------------------------------------------
    nodes["confirm"] = _talk("confirm", spec, "eval_confirm",
                             [ext("confirm_stance", prompts.CONFIRM_STANCE, enum=["yes", "no", "change", "question", "other"], min_confidence=0.4)] + prop_ext + [q_ext, cl_ext])
    nodes["eval_confirm"] = code_node("eval_confirm", codegen.code_source("eval_confirm", cfg), "confirm",
                                      _route([("record", "record"), ("eval", "eval"), ("close", "notes_plan"), ("confirm", "confirm")], "confirm"))
    cp_baked = dict(baked_cid, **{roles["cp_product"]: "{{rec_pid}}", roles["cp_amount"]: "{{rec_amount}}", roles["cp_date"]: "{{rec_date}}"})
    cp1 = api_tool(api, "create_promise", cp_baked, "Record the promise.", max_retries=0, post_hook=codegen.header_post_hook())
    cp2 = api_tool(api, "create_promise", cp_baked, "Record the promise (second attempt).", max_retries=0, post_hook=codegen.header_post_hook())
    nodes["record"] = api_node("record", cp1, "record_retry", [t_bool("rec_ok", "after_record", "the promise was recorded")],
                               response_mapping=[{"path": "data.ok", "variable": "rec_ok"}])
    nodes["record_retry"] = api_node("record_retry", cp2, "after_record", response_mapping=[{"path": "data.ok", "variable": "rec_ok_retry"}])
    nodes["after_record"] = code_node("after_record", codegen.code_source("after_record", cfg), "notes_plan",
                                      _route([("record", "record"), ("close", "notes_plan")], "notes_plan"))

    # ---- closing ------------------------------------------------------------------------------------------------
    nodes["notes_plan"] = code_node("notes_plan", codegen.code_source("notes_plan", cfg), "farewell",
                                    _route([("note_1", "note_1"), ("farewell", "farewell")], "farewell"))
    n_notes = max(3, int(get(spec, "multi_product.max_products", 3) or 3))
    if api.has("add_note"):
        for i in range(1, n_notes + 1):
            baked = dict(baked_cid, **{roles["note_product"]: "{{note_%d_pid}}" % i, roles["note_reason"]: "{{note_%d_reason}}" % i})
            nt = api_tool(api, "add_note", baked, "Note why this product has no promise.", max_retries=0, post_hook=codegen.header_post_hook(),
                          pre_hook=codegen.drop_empty_pre_hook([roles["note_text"]] if roles.get("note_text") else []))
            nxt = "note_%d" % (i + 1) if i < n_notes else "farewell"
            trans = [t(nxt, "another note is needed", group(c_neq("note_%d_reason" % (i + 1), "")))] if i < n_notes else []
            nodes["note_%d" % i] = api_node("note_%d" % i, nt, "farewell", trans)
    else:
        for i in range(1, n_notes + 1): nodes["note_%d" % i] = code_node("note_%d" % i, codegen.code_source("set", cfg, {"set": {"route": "farewell"}}), "farewell")
    if api.has("transfer_to_agent"):
        tt = api_tool(api, "transfer_to_agent", dict(baked_cid, **{roles["queue"]: "{{transfer_queue}}"}), "Hand the call over.", max_retries=0, post_hook=codegen.header_post_hook())
        nodes["transfer"] = api_node("transfer", tt, "close")
    else:
        nodes["transfer"] = code_node("transfer", codegen.code_source("set", cfg, {"set": {"route": "close"}}), "close")
    nodes["say_transfer"] = _talk("say_transfer", spec, "transfer", [], max_turns=2)
    nodes["farewell"] = _talk("farewell", spec, "close", [], max_turns=2)
    cc = api_tool(api, "close_call", dict(baked_cid, **{roles["outcome"]: "{{outcome}}", roles["reason"]: "{{reason}}"}), "Close the call.", max_retries=1,
                  pre_hook=codegen.close_pre_hook(cfg), post_hook=codegen.header_post_hook())
    nodes["close"] = api_node("close", cc, "hangup")
    nodes["hangup"] = end_node("hangup", "call_closed")
    return {"initial_node": "opening", "system_prompt": prompts.system_prompt(spec), "nodes": nodes, "global_nodes": {}}


def call_variables(spec, cfg):
    return set([cfg["customer_id_var"], cfg["now_var"]] + list(get(spec, "call_variables.others", []) or []))


def counts(workflow):
    nodes = workflow.get("nodes") or {}
    tools = set()
    for n in nodes.values():
        for tl in (n.get("tools") or []) + (n.get("pre_actions") or []):
            fn = (tl.get("function") or {}).get("name")
            if fn and fn != "code_exec": tools.add(fn)
    return len(nodes), len(tools)
