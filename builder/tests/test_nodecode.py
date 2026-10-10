"""Offline run of the generated node logic against the Brief A/B practice scenarios (no platform, no model)."""
import json, os, unittest

from builder import datefacts, nodecode
from builder.cfg import build_cfg
from builder.toolapi import load_openapi

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NODE_SRC = open(os.path.join(ROOT, "builder", "nodecode.py"), encoding="utf-8").read()
NOW = "2026-10-14T11:00"


def load_spec(name):
    p = os.path.join(ROOT, "builder", "tests", "fixtures", name)
    return json.load(open(p))


class Sim:
    """Drive the node functions the way the workflow would."""
    def __init__(self, spec, api, products, now=NOW):
        self.cfg = build_cfg(spec, api)
        self.ns = datefacts.lib_namespace(); exec(NODE_SRC, self.ns)
        self.vars = {"customer_id": "c_test", "first_name": "Dana", "last_name": "Reyes", "title": "Ms", "now": now, "products": products}
        self.run = self.ns["_run_node"]; self.promises = []; self.notes = []; self.log = []
    def node(self, mode):
        self.run(mode, self.vars, self.cfg); r = self.vars.get("route"); self.log.append((mode, r, self.vars.get("say", "")[:90])); return r
    def start(self):
        return self.node("product_facts")
    def say(self, stance, date="", amount="", product=""):
        self.vars.update({"stance": stance, "prop_date_text": date, "prop_amount_text": amount, "prop_product_text": product})
        return self.node("eval")
    def confirm(self, stance="yes", fail_first=0):
        self.vars["confirm_stance"] = stance
        r = self.node("eval_confirm")
        fails = fail_first
        while r == "record":
            k = self.vars["rec_k"]
            if fails > 0:
                fails -= 1; self.vars["rec_ok"] = ""; self.vars["rec_ok_retry"] = "true"   # first call 500, retry ok
            else:
                self.vars["rec_ok"] = "true"
            self.promises.append((self.vars["rec_pid"], round(float(self.vars["rec_amount"]), 2), self.vars["rec_date"]))
            r = self.node("after_record")
        return r
    def close(self):
        r = self.node("notes_plan")
        for i in (1, 2, 3):
            if self.vars.get(f"note_{i}_reason"): self.notes.append((self.vars[f"note_{i}_pid"], self.vars[f"note_{i}_reason"]))
        return (self.vars.get("outcome"), self.vars.get("reason") or None)


CC = lambda last4, due, late, mn: {"product_id": "p1", "type": "credit_card", "card_last4": last4, "past_due": due, "days_late": late, "minimum_payment": mn}
LOAN = lambda pid, typ, due, late, inst: {"product_id": pid, "type": typ, "past_due": due, "days_late": late, "instalment_amount": inst}


class BriefATests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = load_openapi(os.path.join(ROOT, "tools", "openapi.json")); cls.spec = load_spec("spec-brief-a.json")

    def sim(self, products): return Sim(self.spec, self.api, products)

    def test_pub01_full_today(self):
        s = self.sim([CC("4821", 420.0, 6, 126.0)]); self.assertEqual(s.start(), "negotiate")
        self.assertIn("Can you make this payment today?", s.vars["say"])
        self.assertEqual(s.say("agrees"), "confirm"); self.assertEqual(s.confirm("yes"), "close")
        self.assertEqual(s.close(), ("promise", None)); self.assertEqual(s.promises, [("p1", 420.0, "2026-10-14")])
        self.assertIn("text message", s.vars["say"])

    def test_pub04_after_deadline(self):
        s = self.sim([LOAN("p1", "car_loan", 1250.0, 14, 400.0)]); s.start()
        self.assertEqual(s.say("proposes", date="6 November"), "negotiate"); self.assertIn("23 October", s.vars["say"])
        self.assertEqual(s.say("agrees"), "confirm"); s.confirm(); self.assertEqual(s.close(), ("promise", None))
        self.assertEqual(s.promises, [("p1", 1250.0, "2026-10-23")])

    def test_pub05_hardship_declines(self):
        s = self.sim([LOAN("p1", "personal_loan", 780.0, 21, 260.0)]); s.start()
        self.assertEqual(s.say("hardship"), "hardship"); self.assertIn("sorry", s.vars["say"].lower())
        s.vars["hs_stance"] = "declines"; self.assertEqual(s.node("eval_hardship"), "close")
        self.assertEqual(s.close(), ("no_promise", "hardship")); self.assertEqual(s.promises, [])

    def test_pub06_too_much_then_friday(self):
        s = self.sim([CC("1903", 2125.1, 12, 637.5)]); s.start()
        self.assertEqual(s.say("too_much"), "negotiate"); self.assertIn("637.50", s.vars["say"]); self.assertIn("overdue", s.vars["say"])
        self.assertEqual(s.say("proposes", date="this Friday"), "confirm"); s.confirm()
        self.assertEqual(s.close(), ("promise", None)); self.assertEqual(s.promises, [("p1", 637.5, "2026-10-16")])

    def test_pub07_vague_then_holiday(self):
        s = self.sim([LOAN("p1", "personal_loan", 540.0, 5, 180.0)]); s.start()
        self.assertEqual(s.say("refuses"), "negotiate")            # cannot pay today -> attempt 1 (16 Oct)
        self.assertIn("16 October", s.vars["say"])
        self.assertEqual(s.say("vague", date="the week after next"), "negotiate"); self.assertIn("exact day", s.vars["say"])
        self.assertEqual(s.say("proposes", date="Monday the 26th"), "negotiate"); self.assertIn("27 October", s.vars["say"])
        self.assertEqual(s.say("agrees"), "confirm"); s.confirm()
        self.assertEqual(s.promises, [("p1", 540.0, "2026-10-27")]); self.assertEqual(s.close(), ("promise", None))

    def test_pub08_paid(self):
        s = self.sim([CC("5512", 180.0, 5, 54.0)]); s.start()
        self.assertEqual(s.say("paid"), "close"); self.assertEqual(s.close(), ("paid", None)); self.assertEqual(s.promises, [])
        self.assertIn("one business day", s.vars["say"])

    def test_pub09_plan(self):
        s = self.sim([LOAN("p1", "personal_loan", 2100.0, 28, 700.0)]); s.start()
        self.assertEqual(s.say("plan"), "transfer"); self.assertEqual(s.vars["transfer_queue"], "restructuring")
        self.assertEqual(s.close(), ("transferred", "restructuring"))

    def test_pub10_retry(self):
        s = self.sim([CC("7740", 365.0, 8, 109.5)]); s.start()
        s.say("refuses"); self.assertIn("16 October", s.vars["say"])
        self.assertEqual(s.say("agrees"), "confirm"); self.assertEqual(s.confirm("yes", fail_first=1), "close")
        self.assertEqual(s.promises, [("p1", 365.0, "2026-10-16")]); self.assertEqual(s.close(), ("promise", None))

    def test_flat_refusals_late_band(self):
        s = self.sim([CC("1111", 500.0, 20, 150.0)]); s.start()
        self.assertEqual(s.say("refuses"), "negotiate"); self.assertIn("16 October", s.vars["say"])
        self.assertEqual(s.say("refuses"), "negotiate"); self.assertIn("150", s.vars["say"]); self.assertIn("23 October", s.vars["say"])
        self.assertEqual(s.say("refuses"), "close"); self.assertEqual(s.close(), ("no_promise", "refused"))

    def test_flat_refusal_early_band(self):
        s = self.sim([CC("1111", 500.0, 3, 150.0)]); s.start()
        self.assertEqual(s.say("refuses"), "negotiate"); self.assertEqual(s.say("refuses"), "close")
        self.assertEqual(s.close(), ("no_promise", "refused"))

    def test_dispute(self):
        s = self.sim([CC("1111", 500.0, 3, 150.0)]); s.start()
        self.assertEqual(s.say("dispute"), "close"); self.assertEqual(s.close(), ("no_promise", "dispute"))

    def test_service_error_twice(self):
        s = self.sim([CC("1111", 500.0, 3, 150.0)]); s.start(); s.say("agrees")
        s.vars["confirm_stance"] = "yes"; r = s.node("eval_confirm"); self.assertEqual(r, "record")
        s.vars["rec_ok"] = ""; s.vars["rec_ok_retry"] = ""; self.assertEqual(s.node("after_record"), "close")
        self.assertEqual(s.close(), ("no_promise", "service_error")); self.assertIn("could not record", s.vars["say"])

    def test_below_floor_then_floor(self):
        s = self.sim([CC("1111", 500.0, 3, 150.0)]); s.start()
        self.assertEqual(s.say("proposes", date="tomorrow", amount="100"), "negotiate"); self.assertIn("150", s.vars["say"])
        self.assertEqual(s.say("agrees"), "confirm"); s.confirm(); self.assertEqual(s.promises, [("p1", 150.0, "2026-10-15")])

    def test_third_party_callback(self):
        s = self.sim([]); s.vars.update({"tp_stance": "gives_time", "cb_date_text": "tomorrow morning", "cb_time_text": "around eleven"})
        self.assertEqual(s.node("tp_eval"), "schedule"); self.assertEqual((s.vars["cb_date"], s.vars["cb_time"]), ("2026-10-15", "11:00"))
        s.vars.update({"tp_stance": "gives_time", "cb_date_text": "Saturday", "cb_time_text": "9 pm"}); s.vars["cb_tries"] = 0
        self.assertEqual(s.node("tp_eval"), "again"); s.vars.update({"tp_stance": "gives_time", "cb_date_text": "Sunday", "cb_time_text": "8 pm"})
        self.assertEqual(s.node("tp_eval"), "close"); self.assertEqual((s.vars["outcome"], s.vars["reason"]), ("not_reached", "no_callback"))

    def test_opening_routes(self):
        s = self.sim([]); s.vars["ack"] = "customer"; self.assertEqual(s.node("opening_tally"), "identity")
        s = self.sim([]); s.vars["ack"] = "third_party"; self.assertEqual(s.node("opening_tally"), "third_party")
        s = self.sim([]); s.vars.update({"ack": "question", "q_kind": "robot"}); self.assertEqual(s.node("opening_tally"), "again")
        self.assertIn("digital assistant", s.vars["say"]); self.assertIn("Am I speaking with", s.vars["say"])

    def test_opening_unclear_twice(self):
        s = self.sim([]); s.vars["ack"] = "unclear"; self.assertEqual(s.node("opening_tally"), "again")
        s.vars["ack"] = "unclear"; self.assertEqual(s.node("opening_tally"), "close"); self.assertEqual((s.vars["outcome"], s.vars["reason"]), ("not_reached", "unclear"))

    def test_identity_declines_twice(self):
        s = self.sim([]); s.node("identity_prep"); self.assertEqual(s.vars["id_next_field"], "date_of_birth"); self.assertIn("date of birth", s.vars["say"])
        s.vars["id_stance"] = "asks_what_about"; self.assertEqual(s.node("identity_eval"), "identity"); self.assertIn("protect", s.vars["say"])
        s.vars["id_stance"] = "declines"; self.assertEqual(s.node("identity_eval"), "close"); self.assertEqual((s.vars["outcome"], s.vars["reason"]), ("not_verified", "declined"))

    def test_identity_happy_and_pieces(self):
        s = self.sim([]); s.node("identity_prep")
        s.vars.update({"id_stance": "answering", "id_answer_text": "14 March"}); self.assertEqual(s.node("identity_eval"), "identity"); self.assertIn("go on", s.vars["say"].lower())
        s.vars.update({"id_stance": "answering", "id_answer_text": "1988"}); self.assertEqual(s.node("identity_eval"), "verify"); self.assertEqual(s.vars["id_answer"], "1988-03-14")
        s.vars.update({"vi_ok": "true", "vi_verified": "true", "vi_all": "false", "vi_left": "3"}); self.assertEqual(s.node("identity_after"), "identity")
        self.assertEqual(s.vars["id_next_field"], "phone_last4"); self.assertIn("last four digits", s.vars["say"])
        s.vars.update({"id_stance": "answering", "id_answer_text": "forty-four"}); self.assertEqual(s.node("identity_eval"), "identity")
        s.vars.update({"id_stance": "answering", "id_answer_text": "seventy-one"}); self.assertEqual(s.node("identity_eval"), "verify"); self.assertEqual(s.vars["id_answer"], "4471")
        s.vars.update({"vi_ok": "true", "vi_verified": "true", "vi_all": "true", "vi_left": "3"}); self.assertEqual(s.node("identity_after"), "fetch"); self.assertEqual(s.vars["verified"], 1)

    def test_identity_three_wrong(self):
        s = self.sim([]); s.node("identity_prep")
        for i, left in enumerate(("2", "1", "0")):
            s.vars.update({"id_stance": "answering", "id_answer_text": "12 July 1991"}); self.assertEqual(s.node("identity_eval"), "verify")
            s.vars.update({"vi_ok": "true", "vi_verified": "false", "vi_all": "false", "vi_left": left}); r = s.node("identity_after")
        self.assertEqual(r, "close"); self.assertEqual((s.vars["outcome"], s.vars["reason"]), ("not_verified", "failed")); self.assertIn("mobile app", s.vars["say"])

    def test_identity_swapped_hint(self):
        s = self.sim([]); s.node("identity_prep")
        s.vars.update({"id_stance": "answering", "id_answer_text": "03/14/1988"}); self.assertEqual(s.node("identity_eval"), "verify")
        s.vars.update({"vi_ok": "true", "vi_verified": "false", "vi_all": "false", "vi_left": "3", "vi_hint": "day_month_swapped"}); self.assertEqual(s.node("identity_after"), "identity")
        self.assertIn("month as a word", s.vars["say"]); self.assertEqual(s.vars["id_wrong"], 0)

    def test_question_with_proposal(self):
        s = self.sim([LOAN("p1", "car_loan", 1250.0, 14, 400.0)]); s.start()
        s.vars["q_kind"] = "robot"; self.assertEqual(s.say("proposes", date="6 November"), "negotiate")
        self.assertTrue(s.vars["say"].startswith("I am Freya Bank's digital assistant.")); self.assertIn("23 October", s.vars["say"])

    def test_question_then_repeat(self):
        s = self.sim([CC("1111", 500.0, 3, 150.0)]); s.start()
        s.vars["q_kind"] = "robot"; self.assertEqual(s.say("question"), "negotiate"); self.assertIn("digital assistant", s.vars["say"]); self.assertIn("today?", s.vars["say"])


class BriefBTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = load_openapi(os.path.join(ROOT, "tools", "openapi.json")); cls.spec = load_spec("spec-brief-ab.json")

    def sim(self, products): return Sim(self.spec, self.api, products)

    def test_pub11_three_one_date(self):
        s = self.sim([CC("2288", 220.0, 9, 66.0), LOAN("p2", "personal_loan", 640.0, 9, 213.0), LOAN("p3", "car_loan", 75.0, 3, 25.0)])
        self.assertEqual(s.start(), "negotiate"); self.assertEqual(s.vars["neg_phase"], "all"); self.assertIn("all of them today", s.vars["say"])
        self.assertEqual(s.say("proposes", date="this Friday"), "confirm"); self.assertEqual(s.vars["readback_text"].count("16 October"), 3)
        s.confirm(); self.assertEqual(sorted(s.promises), [("p1", 220.0, "2026-10-16"), ("p2", 640.0, "2026-10-16"), ("p3", 75.0, "2026-10-16")])
        self.assertEqual(s.close(), ("promise", None)); self.assertEqual(s.notes, [])

    def test_pub12_one_promise_two_refused(self):
        s = self.sim([CC("9015", 510.0, 16, 153.0), LOAN("p2", "personal_loan", 1320.0, 16, 440.0), LOAN("p3", "car_loan", 140.0, 7, 46.0)]); s.start()
        self.assertEqual(s.say("proposes", date="tomorrow", product="credit card"), "negotiate")   # p1 agreed, now p2 attempt 1
        self.assertEqual(s.vars["cur_k"], 2); self.assertIn("16 October", s.vars["say"])
        self.assertEqual(s.say("refuses"), "negotiate"); self.assertIn("440", s.vars["say"]); self.assertIn("23 October", s.vars["say"])  # attempt 2 late band
        self.assertEqual(s.say("refuses"), "negotiate"); self.assertEqual(s.vars["cur_k"], 3)   # p3 attempt 1
        self.assertEqual(s.say("refuses"), "confirm")                                             # p3 exhausted (early) -> confirm p1
        s.confirm(); self.assertEqual(s.promises, [("p1", 510.0, "2026-10-15")])
        self.assertEqual(s.close(), ("promise", None)); self.assertEqual(sorted(s.notes), [("p2", "refused"), ("p3", "refused")])

    def test_pub13_capped_deadline(self):
        s = self.sim([CC("6604", 300.0, 4, 90.0), LOAN("p2", "personal_loan", 900.0, 20, 300.0)]); s.start()
        self.assertEqual(s.say("proposes", date="30 October"), "confirm")
        self.assertIn("30 October", s.vars["readback_text"]); self.assertIn("23 October", s.vars["readback_text"])
        s.confirm(); self.assertEqual(sorted(s.promises), [("p1", 300.0, "2026-10-30"), ("p2", 900.0, "2026-10-23")]); self.assertEqual(s.close(), ("promise", None))

    def test_all_refused_notes_and_outcome(self):
        s = self.sim([CC("1", 100.0, 3, 30.0), LOAN("p2", "car_loan", 200.0, 20, 50.0)]); s.start()
        self.assertEqual(s.say("refuses"), "negotiate"); self.assertEqual(s.vars["cur_k"], 1)   # p1 attempt 1 (early)
        self.assertEqual(s.say("refuses"), "negotiate"); self.assertEqual(s.vars["cur_k"], 2)   # p2 attempt 1
        self.assertEqual(s.say("refuses"), "negotiate")                                           # p2 attempt 2
        self.assertEqual(s.say("refuses"), "close"); self.assertEqual(s.close(), ("no_promise", "refused"))
        self.assertEqual(sorted(s.notes), [("p1", "refused"), ("p2", "refused")])

    def test_paid_one_dispute_other(self):
        s = self.sim([CC("1", 100.0, 3, 30.0), LOAN("p2", "car_loan", 200.0, 20, 50.0)]); s.start()
        self.assertEqual(s.say("refuses"), "negotiate")           # not all today -> p1 attempt 1
        self.assertEqual(s.say("paid"), "negotiate"); self.assertEqual(s.vars["cur_k"], 2)
        self.assertEqual(s.say("dispute"), "close"); self.assertEqual(s.close(), ("no_promise", "dispute"))
        self.assertEqual(sorted(s.notes), [("p1", "paid"), ("p2", "dispute")])

    def test_restructuring_no_notes(self):
        s = self.sim([CC("1", 100.0, 3, 30.0), LOAN("p2", "car_loan", 200.0, 20, 50.0)]); s.start()
        self.assertEqual(s.say("plan"), "transfer"); self.assertEqual(s.close(), ("transferred", "restructuring")); self.assertEqual(s.notes, [])


if __name__ == "__main__":
    unittest.main()
