"""Edge cases of the node logic beyond the practice cases: multi-product mixes, transfers mid-call, callback windows."""
import json, os, unittest

from builder.tests.test_nodecode import Sim, CC, LOAN, load_spec, ROOT
from builder.toolapi import load_openapi


class MultiProductEdges(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = load_openapi(os.path.join(ROOT, "tools", "openapi.json")); cls.spec = load_spec("spec-brief-ab.json")

    def two(self): return Sim(self.spec, self.api, [CC("1111", 400.0, 3, 120.0), LOAN("p2", "personal_loan", 900.0, 20, 300.0)])

    def test_hardship_on_second_product_after_first_agreed(self):
        s = self.two(); s.start()
        self.assertEqual(s.say("refuses"), "negotiate")                       # not all today -> p1 attempt 1
        self.assertEqual(s.say("agrees"), "negotiate"); self.assertEqual(s.vars["cur_k"], 2)
        self.assertEqual(s.say("hardship"), "hardship"); self.assertIn("sorry", s.vars["say"].lower())
        s.vars["hs_stance"] = "declines"; self.assertEqual(s.node("eval_hardship"), "confirm")   # p1 still agreed
        self.assertIn("400", s.vars["readback_text"]); self.assertNotIn("900", s.vars["readback_text"])
        s.confirm(); self.assertEqual(s.promises, [("p1", 400.0, "2026-10-16")])
        self.assertEqual(s.close(), ("promise", None)); self.assertEqual(s.notes, [("p2", "hardship")])

    def test_dispute_first_then_promise(self):
        s = self.two(); s.start(); s.say("refuses")
        self.assertEqual(s.say("dispute"), "negotiate"); self.assertEqual(s.vars["cur_k"], 2); self.assertIn("dispute", s.vars["say"].lower())
        self.assertEqual(s.say("agrees"), "confirm"); s.confirm(); self.assertEqual(s.promises, [("p2", 900.0, "2026-10-16")])
        self.assertEqual(s.close(), ("promise", None)); self.assertEqual(s.notes, [("p1", "dispute")])

    def test_service_error_on_one_of_two(self):
        s = self.two(); s.start()
        self.assertEqual(s.say("proposes", date="this Friday"), "confirm")
        s.vars["confirm_stance"] = "yes"; self.assertEqual(s.node("eval_confirm"), "record"); self.assertEqual(s.vars["rec_pid"], "p1")
        s.vars["rec_ok"] = ""; s.vars["rec_ok_retry"] = ""; self.assertEqual(s.node("after_record"), "record"); self.assertEqual(s.vars["rec_pid"], "p2")
        s.vars["rec_ok"] = "true"; self.assertEqual(s.node("after_record"), "close")
        self.assertEqual(s.close(), ("promise", None)); self.assertEqual(s.notes, [("p1", "service_error")])
        self.assertIn("could not record", s.vars["say"]); self.assertIn("900", s.vars["say"]); self.assertIn("text message", s.vars["say"])

    def test_human_request_mid_negotiation(self):
        s = self.two(); s.start(); s.say("refuses")
        self.assertEqual(s.say("human"), "human"); self.assertIn("help you", s.vars["say"])
        s.vars["hum_stance"] = "continues"; self.assertEqual(s.node("eval_human"), "negotiate"); self.assertIn("Can you pay 400", s.vars["say"])
        self.assertEqual(s.say("human"), "human"); s.vars["hum_stance"] = "insists"; self.assertEqual(s.node("eval_human"), "transfer")
        self.assertEqual(s.vars["transfer_queue"], "general"); self.assertEqual(s.close(), ("transferred", "human")); self.assertEqual(s.notes, [])

    def test_plan_request_after_first_agreed(self):
        s = self.two(); s.start(); s.say("refuses"); s.say("agrees")
        self.assertEqual(s.say("plan"), "transfer"); self.assertEqual(s.close(), ("transferred", "restructuring")); self.assertEqual(s.notes, []); self.assertEqual(s.promises, [])

    def test_dont_want_to_talk_twice_with_two_products(self):
        s = self.two(); s.start(); s.say("refuses")
        self.assertEqual(s.say("dont_want_to_talk"), "negotiate"); self.assertEqual(s.say("dont_want_to_talk"), "close")
        self.assertEqual(s.close(), ("no_promise", "refused")); self.assertEqual(sorted(s.notes), [("p1", "refused"), ("p2", "refused")])

    def test_too_much_in_all_phase_then_floors(self):
        s = self.two(); s.start()
        self.assertEqual(s.say("too_much"), "negotiate"); self.assertEqual(s.vars["cur_k"], 1); self.assertIn("120", s.vars["say"])   # p1 attempt 1 at the floor
        self.assertEqual(s.say("agrees"), "negotiate"); self.assertEqual(s.vars["cur_k"], 2); self.assertIn("300", s.vars["say"])
        self.assertEqual(s.say("agrees"), "confirm"); s.confirm(); self.assertEqual(sorted(s.promises), [("p1", 120.0, "2026-10-16"), ("p2", 300.0, "2026-10-16")])

    def test_all_paid_closes_paid(self):
        s = self.two(); s.start()
        self.assertEqual(s.say("paid"), "close"); self.assertEqual(s.close(), ("paid", None)); self.assertEqual(sorted(s.notes), [("p1", "paid"), ("p2", "paid")])


class CallbackAndOpeningEdges(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = load_openapi(os.path.join(ROOT, "tools", "openapi.json")); cls.spec = load_spec("spec-brief-a.json")

    def test_friday_evening_callback_next_business_day(self):
        s = Sim(self.spec, self.api, [], now="2026-10-23T18:30")      # Friday evening; Monday 26 Oct is a holiday
        s.vars.update({"tp_stance": "gives_time", "cb_date_text": "Monday", "cb_time_text": "9 in the morning"}); s.node("tp_prep")
        self.assertEqual(s.node("tp_eval"), "again"); self.assertIn("between 10:00 and 19:00", s.vars["say"])      # 09:00 is outside the window
        s.vars.update({"tp_stance": "gives_time", "cb_date_text": "Tuesday", "cb_time_text": "11"}); self.assertEqual(s.node("tp_eval"), "schedule")
        self.assertEqual((s.vars["cb_date"], s.vars["cb_time"]), ("2026-10-27", "11:00"))

    def test_callback_window_inclusive_end(self):
        s = Sim(self.spec, self.api, []); s.node("tp_prep")
        s.vars.update({"tp_stance": "gives_time", "cb_date_text": "tomorrow", "cb_time_text": "7 pm"}); self.assertEqual(s.node("tp_eval"), "schedule"); self.assertEqual(s.vars["cb_time"], "19:00")

    def test_callback_today_must_be_after_now(self):
        s = Sim(self.spec, self.api, []); s.node("tp_prep")
        s.vars.update({"tp_stance": "gives_time", "cb_date_text": "today", "cb_time_text": "10 am"}); self.assertEqual(s.node("tp_eval"), "again")   # now is 11:00
        s.vars.update({"tp_stance": "gives_time", "cb_date_text": "today", "cb_time_text": "3 pm"}); self.assertEqual(s.node("tp_eval"), "schedule")

    def test_opening_deceased(self):
        s = Sim(self.spec, self.api, []); s.vars["ack"] = "deceased"; self.assertEqual(s.node("opening_tally"), "close")
        self.assertEqual((s.vars["outcome"], s.vars["reason"]), ("not_reached", "deceased")); self.assertIn("sorry for your loss", s.vars["say"].lower())

    def test_identity_hint_then_correct(self):
        s = Sim(self.spec, self.api, []); s.node("identity_prep")
        s.vars.update({"id_stance": "answering", "id_answer_text": "3/14/1988"}); self.assertEqual(s.node("identity_eval"), "verify")
        s.vars.update({"vi_ok": "true", "vi_verified": "false", "vi_all": "false", "vi_left": "3", "vi_hint": "day_month_swapped"}); self.assertEqual(s.node("identity_after"), "identity")
        self.assertEqual(s.vars["id_wrong"], 0); self.assertIn("month as a word", s.vars["say"])
        s.vars.update({"id_stance": "answering", "id_answer_text": "14 March 1988"}); self.assertEqual(s.node("identity_eval"), "verify"); self.assertEqual(s.vars["id_answer"], "1988-03-14")

    def test_single_product_agrees_to_deadline_offer_counts_no_extra_attempt(self):
        s = Sim(self.spec, self.api, [LOAN("p1", "car_loan", 1250.0, 14, 400.0)]); s.start()
        self.assertEqual(s.say("proposes", date="6 November"), "negotiate"); self.assertEqual(s.vars["p1_attempts_used"], 0)
        self.assertEqual(s.say("refuses"), "negotiate"); self.assertEqual(s.vars["p1_attempts_used"], 1); self.assertIn("16 October", s.vars["say"])  # attempt 1 after refusing the deadline
        self.assertEqual(s.say("refuses"), "negotiate"); self.assertEqual(s.vars["p1_attempts_used"], 2); self.assertIn("400", s.vars["say"])       # attempt 2: floor on the deadline
        self.assertEqual(s.say("refuses"), "close"); self.assertEqual(s.close(), ("no_promise", "refused"))


if __name__ == "__main__":
    unittest.main()
