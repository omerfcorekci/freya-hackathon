"""The workflow graph. Fixed structure, every value from the spec and the tool API.

Pattern: a conversation node speaks on entry from an instruction a code node computed, collects one customer turn
through extraction, and leaves on `always` into the next code node. Only verify_identity is a model-called tool; the
other bank tools run in api_request nodes with every field baked from variables.
"""
from builder import codegen, prompts
from builder.nodes import (api_node, code_node, conversation, end_node, ext, group, c_eq, c_neq, t, t_always, t_bool, t_eq, t_in, silent, tts)
from builder.spec_schema import get
from builder.toolapi import api_tool


def _route(pairs, default):
    """Transitions on the `route` variable written by a code node, then the mandatory always."""
    return [t_eq("route", val, target, f"route {val}") for val, target in pairs] + [t_always(default)]


def compile_workflow(spec, api, cfg):
    roles = cfg["roles"]; cid = "{{" + cfg["customer_id_var"] + "}}"
    baked_cid = {roles["customer_id"]: cid}
    nodes = {}

    # ---- opening ------------------------------------------------------------------------------------------------
    opening_line = (str(get(spec, "opening.sentence", "")) + " " + str(get(spec, "opening.ask_for_customer", ""))).strip()
    ack_ext = [ext("ack", prompts.ACK, enum=["customer", "third_party", "wrong_number", "deceased", "question", "refuses", "wants_human", "unclear"], min_confidence=0.5)]
    ack_routes = [t_eq("ack", "customer", "identity_prep", "the customer confirmed"), t_eq("ack", "third_party", "third_party", "someone else answered"),
                  t_always("opening_tally")]
    nodes["opening"] = conversation("opening", prompts.opening_task(spec), ack_routes, on_enter=tts(opening_line), first_entry_only=True,
                                    extraction=ack_ext, max_turns=3, max_turn_transition="opening_tally")
    nodes["opening_again"] = conversation("opening_again", prompts.opening_again_task(spec), ack_routes, extraction=ack_ext, max_turns=3, max_turn_transition="opening_tally")
    nodes["opening_tally"] = code_node("opening_tally", codegen.code_source("opening_tally", cfg), "opening_again",
                                       _route([("human", "human_ask"), ("close", "farewell")], "opening_again"))

    # ---- identity ----------------------------------------------------------------------------------------------
    vi = api_tool(api, "verify_identity", baked_cid, "CALL it every time the customer gives an answer to a security question, with the field of the question you asked and the answer.",
                  max_retries=0, pre_hook=codegen.verify_pre_hook(cfg), post_hook=codegen.verify_post_hook(cfg), model_fields=[roles["vi_field"], roles["vi_answer"]])
    nodes["identity_prep"] = code_node("identity_prep", codegen.code_source("identity_prep", cfg), "identity",
                                       _route([("identity", "identity")], "identity"))
    id_trans = [
        t("fetch_account", "all security answers verified", group(c_eq("id_state", "verified"), c_eq("verify_identity_response.data.all_verified", "true"), c_eq("verify_identity_response.data.all_verified", "True"))),
        t("say_failed", "the check failed", group(c_eq("id_state", "failed"), c_eq("verify_identity_response.data.wrong_answers_left", "0"))),
        t_in("id_stance", ["declines", "asks_what_about", "dont_want_to_talk", "wants_human"], "identity_tally", "the customer did not answer the question"),
    ]
    nodes["identity"] = conversation("identity", prompts.identity_task(spec, "verify_identity"), id_trans, tools=[vi],
                                     extraction=[ext("id_stance", prompts.ID_STANCE, enum=["answering", "declines", "asks_what_about", "dont_want_to_talk", "wants_human", "question", "other"], min_confidence=0.5)],
                                     max_turns=16, max_turn_transition="say_failed")
    nodes["identity_tally"] = code_node("identity_tally", codegen.code_source("identity_tally", cfg), "identity",
                                        _route([("human", "human_ask"), ("close", "farewell")], "identity"))
    nodes["say_failed"] = conversation("say_failed", prompts.say_failed_task(spec), [t_always("set_failed")], max_turns=2, max_turn_transition="set_failed")
    nodes["set_failed"] = code_node("set_failed", codegen.code_source("set", cfg, {"set": {"outcome": get(spec, "identity.failed.outcome", {}), "route": "close"}}), "close")

    # ---- third party -------------------------------------------------------------------------------------------
    nodes["third_party"] = conversation("third_party", prompts.third_party_task(spec), [t_always("tp_eval")],
                                        extraction=[ext("tp_stance", prompts.TP_STANCE, enum=["gives_time", "wrong_number", "deceased", "refuses", "other"], min_confidence=0.5),
                                                    ext("cb_date_text", prompts.CB_DATE, min_confidence=0.4), ext("cb_time_text", prompts.CB_TIME, min_confidence=0.4)],
                                        max_turns=4, max_turn_transition="tp_eval")
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
    prop_ext = [ext("prop_date_text", prompts.PROP_DATE, min_confidence=0.4), ext("prop_amount_text", prompts.PROP_AMOUNT, min_confidence=0.4),
                ext("prop_product_text", prompts.PROP_PRODUCT, min_confidence=0.4)]
    nodes["negotiate"] = conversation("negotiate", prompts.negotiate_task(spec), [t_always("eval")],
                                      extraction=[ext("stance", prompts.STANCE, enum=["agrees", "proposes", "too_much", "refuses", "vague", "hardship", "paid", "dispute", "plan", "human", "question", "dont_want_to_talk", "other"], min_confidence=0.4)] + prop_ext,
                                      max_turns=3, max_turn_transition="eval")
    nodes["eval"] = code_node("eval", codegen.code_source("eval", cfg), "negotiate",
                              _route([("confirm", "confirm"), ("hardship", "hardship_offer"), ("human", "human_ask"), ("transfer", "say_transfer"), ("close", "notes_plan")], "negotiate"))
    nodes["hardship_offer"] = conversation("hardship_offer", prompts.hardship_task(spec), [t_always("eval_hardship")],
                                           extraction=[ext("hs_stance", prompts.HS_STANCE, enum=["accepts", "declines", "proposes", "other"], min_confidence=0.4)] + prop_ext[:2],
                                           max_turns=3, max_turn_transition="eval_hardship")
    nodes["eval_hardship"] = code_node("eval_hardship", codegen.code_source("eval_hardship", cfg), "hardship_offer",
                                       _route([("transfer", "say_transfer"), ("eval", "eval"), ("confirm", "confirm"), ("negotiate", "negotiate"), ("close", "notes_plan")], "hardship_offer"))
    nodes["human_ask"] = conversation("human_ask", prompts.human_task(spec), [t_always("eval_human")],
                                      extraction=[ext("hum_stance", prompts.HUM_STANCE, enum=["insists", "continues", "other"], min_confidence=0.4)],
                                      max_turns=3, max_turn_transition="eval_human")
    nodes["eval_human"] = code_node("eval_human", codegen.code_source("eval_human", cfg), "negotiate",
                                    _route([("transfer", "say_transfer"), ("identity", "identity"), ("opening", "opening_again"), ("negotiate", "negotiate")], "negotiate"))

    # ---- confirmation and recording ------------------------------------------------------------------------------
    nodes["confirm"] = conversation("confirm", prompts.confirm_task(spec), [t_always("eval_confirm")],
                                    extraction=[ext("confirm_stance", prompts.CONFIRM_STANCE, enum=["yes", "no", "change", "question", "other"], min_confidence=0.4)] + prop_ext,
                                    max_turns=3, max_turn_transition="eval_confirm")
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
    if api.has("add_note"):
        for i in (1, 2, 3):
            baked = dict(baked_cid, **{roles["note_product"]: "{{note_%d_pid}}" % i, roles["note_reason"]: "{{note_%d_reason}}" % i})
            nt = api_tool(api, "add_note", baked, "Note why this product has no promise.", max_retries=0, post_hook=codegen.header_post_hook(),
                          pre_hook=codegen.drop_empty_pre_hook([roles["note_text"]] if roles.get("note_text") else []))
            nxt = "note_%d" % (i + 1) if i < 3 else "farewell"
            trans = [t(nxt, "another note is needed", group(c_neq("note_%d_reason" % (i + 1), "")))] if i < 3 else []
            nodes["note_%d" % i] = api_node("note_%d" % i, nt, "farewell", trans)
    else:
        for i in (1, 2, 3): nodes["note_%d" % i] = code_node("note_%d" % i, codegen.code_source("set", cfg, {"set": {"route": "farewell"}}), "farewell")
    if api.has("transfer_to_agent"):
        tt = api_tool(api, "transfer_to_agent", dict(baked_cid, **{roles["queue"]: "{{transfer_queue}}"}), "Hand the call over.", max_retries=0, post_hook=codegen.header_post_hook())
        nodes["transfer"] = api_node("transfer", tt, "close")
    else:
        nodes["transfer"] = code_node("transfer", codegen.code_source("set", cfg, {"set": {"route": "close"}}), "close")
    nodes["say_transfer"] = conversation("say_transfer", prompts.transfer_task(spec), [t_always("transfer")], max_turns=2, max_turn_transition="transfer")
    nodes["farewell"] = conversation("farewell", prompts.farewell_task(spec), [t_always("close")], max_turns=2, max_turn_transition="close")
    cc = api_tool(api, "close_call", dict(baked_cid, **{roles["outcome"]: "{{outcome}}", roles["reason"]: "{{reason}}"}), "Close the call.", max_retries=1,
                  pre_hook=codegen.close_pre_hook(cfg), post_hook=codegen.header_post_hook())
    nodes["close"] = api_node("close", cc, "hangup")
    nodes["hangup"] = end_node("hangup", "call_closed")

    call_vars = [cfg["customer_id_var"], cfg["now_var"]] + list(get(spec, "call_variables.others", []) or [])
    test_vars = {v: ("c_test" if v == cfg["customer_id_var"] else "2026-01-01T10:00" if v == cfg["now_var"] else "Test") for v in call_vars}
    return {"initial_node": "opening", "system_prompt": prompts.system_prompt(spec), "nodes": nodes, "global_nodes": {}, "test_variables": test_vars}


def counts(workflow):
    nodes = workflow.get("nodes") or {}
    tools = set()
    for n in nodes.values():
        for tl in (n.get("tools") or []) + (n.get("pre_actions") or []):
            fn = (tl.get("function") or {}).get("name")
            if fn and fn != "code_exec": tools.add(fn)
    return len(nodes), len(tools)
