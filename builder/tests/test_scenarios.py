import json, os, unittest

from builder.cfg import build_cfg
from builder.selftest import scenarios
from builder.toolapi import load_openapi

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class ScenarioTests(unittest.TestCase):
    def test_generate_with_session(self):
        spec = json.load(open(os.path.join(ROOT, "builder", "tests", "fixtures", "spec-brief-a.json")))
        api = load_openapi(os.path.join(ROOT, "tools", "openapi.json")); cfg = build_cfg(spec, api)
        session = {"variables": {"customer_id": "c_x", "now": "2026-10-14T11:00"}, "identity": {"date_of_birth": "1988-03-14", "phone_last4": "4471"}, "case": "PUB-01"}
        out = scenarios.generate(spec, cfg, session)
        names = [s["name"] for s in out]
        self.assertIn("happy_path_today", names); self.assertIn("third_party_callback", names)
        happy = [s for s in out if s["name"] == "happy_path_today"][0]
        self.assertEqual(happy["turns"][0], "Hello?"); self.assertIn("1988-03-14", happy["turns"]); self.assertIn("4471", happy["turns"])
        cb = [s for s in out if s["name"] == "third_party_callback"][0]
        self.assertEqual(cb["expect_ledger"]["callback"], {"date": "2026-10-15", "time": "11:00"})

    def test_generate_without_session(self):
        spec = json.load(open(os.path.join(ROOT, "builder", "tests", "fixtures", "spec-brief-a.json")))
        api = load_openapi(os.path.join(ROOT, "tools", "openapi.json")); cfg = build_cfg(spec, api)
        out = scenarios.generate(spec, cfg, None)
        self.assertTrue(all(s["name"] != "happy_path_today" for s in out)); self.assertTrue(any(s["name"] == "third_party_callback" for s in out))


if __name__ == "__main__":
    unittest.main()
