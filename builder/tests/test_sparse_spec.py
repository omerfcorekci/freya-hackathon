"""A spec with only the required keys must still compile, lint and run through a call offline.

Hidden briefs may leave out whole sections (no third party, no hardship, no multi-product rules). The extraction
then returns the required keys and little else, and the compiler must never crash on a missing block.
"""
import json, os, unittest

from builder import codegen, datefacts, lint as lintmod, skeleton
from builder.cfg import build_cfg
from builder.selftest import offline
from builder.spec_schema import apply_defaults, validate_spec
from builder.tests.test_nodecode import Sim, CC, ROOT
from builder.toolapi import load_openapi

SPARSE = {
    "meta": {"bank_name": "Sparse Bank"},
    "opening": {"sentence": "Hello, this is Sparse Bank. Am I speaking with {{first_name}} {{last_name}}?",
                "ask_for_customer": "Am I speaking with {{first_name}} {{last_name}}?",
                "unclear": {"outcome": "not_reached", "reason": "unclear"}, "robot_reply": "I am an automated assistant from Sparse Bank."},
    "identity": {"questions": [{"field": "date_of_birth", "ask": "your date of birth", "answer_format": "date_ymd"}],
                 "max_wrong_total": 2, "failed": {"outcome": "not_verified", "reason": "failed"}, "declined": {"outcome": "not_verified", "reason": "declined"}},
    "debt_statement": {"intro": "I am calling about a late payment."},
    "calendar": {"holidays": ["2026-12-25"]},
    "bands": [{"name": "all", "days_late_min": 1, "days_late_max": 999, "deadline_kind": "business_days_after_today", "deadline_n": 5, "persuasion_attempts": 1}],
    "persuasion": {"first_ask": "Can you pay today?", "exhausted": {"outcome": "no_promise", "reason": "refused"}},
    "confirmation": {"question": "Shall I record that?", "after_recorded_sentences": ["Thank you, that is recorded."]},
    "closing": {"outcomes": [{"outcome": "promise", "reasons": []}, {"outcome": "no_promise", "reasons": ["refused", "hardship"]},
                             {"outcome": "not_reached", "reasons": ["unclear", "callback", "no_callback", "wrong_number", "deceased"]},
                             {"outcome": "not_verified", "reasons": ["failed", "declined"]}, {"outcome": "paid", "reasons": []},
                             {"outcome": "transferred", "reasons": ["restructuring", "support"]}]},
}


class _Trace:
    def __init__(self): self.tests = []
    def test(self, name, result, detail=""): self.tests.append((name, result, detail))
    def warn(self, text): pass


class SparseSpec(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = load_openapi(os.path.join(ROOT, "tools", "openapi.json"))
        cls.spec, _ = apply_defaults(json.loads(json.dumps(SPARSE)))
        cls.cfg = build_cfg(cls.spec, cls.api)

    def test_validates_against_tool_api(self):
        self.assertEqual(validate_spec(self.spec, self.api.enums()), [])

    def test_compiles_and_lints(self):
        wf = skeleton.compile_workflow(self.spec, self.api, self.cfg)
        errors, warnings = lintmod.lint(wf, known_vars=skeleton.call_variables(self.spec, self.cfg))
        self.assertEqual(errors, [])
        for node in wf["nodes"].values():
            for act in node.get("pre_actions") or []:
                code = (((act.get("function") or {}).get("parameters") or {}).get("properties") or {}).get("code")
                if code: datefacts.assert_sandbox_safe(code["default"])
        self.assertTrue(any(n.get("node_type") == "end_call" for n in wf["nodes"].values()))

    def test_offline_selftest_passes(self):
        tr = _Trace(); self.assertTrue(offline.run(self.spec, self.cfg, tr), tr.tests)

    def test_call_without_optional_blocks(self):
        s = Sim(self.spec, self.api, [CC("1111", 300.0, 10, 90.0)])
        self.assertEqual(s.start(), "negotiate"); self.assertIn("Can you pay today?", s.vars["say"])
        self.assertEqual(s.say("refuses"), "negotiate"); self.assertIn("21 October", s.vars["say"])   # one attempt: the deadline
        self.assertEqual(s.say("refuses"), "close"); self.assertEqual(s.close(), ("no_promise", "refused"))

    def test_hardship_without_hardship_rules(self):
        # no hardship block at all: one sentence of sympathy, then the normal persuasion (no transfer the brief never mentioned)
        s = Sim(self.spec, self.api, [CC("1111", 300.0, 10, 90.0)]); s.start()
        self.assertEqual(s.say("hardship"), "negotiate"); self.assertIn("sorry", s.vars["say"].lower()); self.assertIn("21 October", s.vars["say"])
        self.assertEqual(s.say("refuses"), "close"); self.assertEqual(s.close(), ("no_promise", "refused"))

    def test_third_party_rules_switched_off(self):
        spec = json.loads(json.dumps(self.spec)); spec["third_party"] = {"enabled": False}
        s = Sim(spec, self.api, [CC("1111", 300.0, 10, 90.0)])
        s.vars["ack"] = "third_party"; self.assertEqual(s.node("opening_tally"), "close")
        self.assertIn("Reyes", s.vars["say"]); self.assertEqual(s.vars["outcome"], "not_reached"); self.assertEqual(s.vars["reason"], "unclear")

    def test_opening_and_identity_nodes(self):
        s = Sim(self.spec, self.api, [CC("1111", 300.0, 10, 90.0)])
        s.vars["ack"] = "customer"; self.assertEqual(s.node("opening_tally"), "identity")
        self.assertEqual(s.node("identity_prep"), "identity"); self.assertIn("date of birth", s.vars["say"])
        s.vars.update({"id_stance": "answering", "id_answer_text": "14 March 1988"}); self.assertEqual(s.node("identity_eval"), "verify")
        self.assertEqual(s.vars["id_answer"], "1988-03-14")
        s.vars.update({"vi_ok": "true", "vi_verified": "true", "vi_all": "true"}); self.assertEqual(s.node("identity_after"), "fetch")

    def test_third_party_without_callback_rules(self):
        s = Sim(self.spec, self.api, [CC("1111", 300.0, 10, 90.0)])
        s.vars["ack"] = "third_party"; self.assertEqual(s.node("opening_tally"), "third_party")
        self.assertEqual(s.node("tp_prep"), "third_party")
        s.vars.update({"tp_stance": "other", "cb_date_text": "tomorrow", "cb_time_text": "11:00"})
        r = s.node("tp_eval"); self.assertIn(r, ("schedule", "close", "again"))
        self.assertTrue(s.vars["say"])


if __name__ == "__main__":
    unittest.main()
