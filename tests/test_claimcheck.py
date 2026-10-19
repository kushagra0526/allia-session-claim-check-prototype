import json, os, sys, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
import gen
from claimcheck import check, parse

REG = json.load(open("data/registry.json"))
BANK = json.load(open("data/bank_dev.json", encoding="utf-8"))


def run(s):
    return check.check(s, REG["clinicians"], REG["payers"])


class T(unittest.TestCase):
    def test_note_times(self):
        self.assertEqual(parse.note_times("Session time: 2:03 PM - 2:55 PM"), (14 * 60 + 3, 14 * 60 + 55))
        self.assertEqual(parse.note_times("Time in: 14:03 / Time out: 14:55"), (843, 895))
        self.assertEqual(parse.note_times("Time: 1403-1455"), (843, 895))
        self.assertEqual(parse.note_times("11:40 - 12:35"), (700, 755))
        self.assertIsNone(parse.note_times("Duration: 45 minutes"))

    def test_scheduling_talk_not_counted(self):
        tr = [dict(t=0, spk="clinician", text="How was the week?"), dict(t=2900, spk="client", text="Better."),
              dict(t=3000, spk="clinician", text="Same time next week?"), dict(t=3200, spk="client", text="Yes, see you then, bye.")]
        self.assertEqual(parse.clinical_span(tr), (0, 3000))

    def test_si_filters(self):
        lines = ["I've been thinking about killing myself.", "I'm not having any thoughts of hurting myself.",
                 "Years ago, back in college, I thought about ending it, but not since.",
                 "My roommate told me she wanted to die and it scared me."]
        got = parse.si_statements([dict(t=i, spk="client", text=x) for i, x in enumerate(lines)])
        self.assertEqual([t for t, _ in got], [0])

    def test_admin_padding_caught(self):
        s = gen.make(5, BANK, "admin_padding")
        out = run(s)
        self.assertEqual(out["decision"], "FIX")
        self.assertEqual(out["findings"][0]["code"], "TIME_EVIDENCE")
        self.assertIn("bill 90834", out["findings"][0]["fix"])

    def test_non_prescriber_em_blocked(self):
        out = run(gen.make(11, BANK, "non_prescriber_em"))
        self.assertEqual(out["decision"], "BLOCK")
        self.assertIn("CREDENTIAL", {f["code"] for f in out["findings"]})

    def test_dev_set_regression(self):
        sessions = gen.dataset(range(1, 121), "data/bank_dev.json")
        for s in sessions:
            out = run(s)
            if s["defect"]:
                self.assertIn(s["expect"], {f["code"] for f in out["findings"]}, s["id"])
            else:
                self.assertEqual(out["decision"], "SUBMIT", (s["id"], out["findings"]))


if __name__ == "__main__":
    unittest.main()
