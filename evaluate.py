"""Score the check and two baselines on generated sessions.  python evaluate.py [dev|heldout] [out.json]"""
import json, sys
from collections import Counter
import gen
from claimcheck import check

REG = json.load(open("data/registry.json"))
MODES = {"claim": "claim scrubber (claim + registry only)", "note": "note-trusting check (no recording)",
         "full": "note + recording + platform log (this)"}


def run(which):
    if which == "heldout":
        cfg = json.load(open("heldout/config.json"))
        sessions = gen.dataset(range(cfg["seeds"][0], cfg["seeds"][1] + 1), cfg["bank"])
    else:
        sessions = gen.dataset(range(1, 401), "data/bank_dev.json")
    res = {}
    for mode in MODES:
        caught, wrong_reason, clean_stopped, per = 0, 0, 0, Counter()
        n_def = n_clean = 0
        misses, false = [], []
        for s in sessions:
            out = check.check(s, REG["clinicians"], REG["payers"], mode)
            codes = {f["code"] for f in out["findings"]}
            if s["defect"]:
                n_def += 1
                if out["decision"] != "SUBMIT" and s["expect"] in codes:
                    caught += 1
                    per[s["defect"]] += 1
                else:
                    if out["decision"] != "SUBMIT":
                        wrong_reason += 1
                    misses.append((s["id"], s["defect"], out["decision"], sorted(codes)))
            else:
                n_clean += 1
                if out["decision"] != "SUBMIT":
                    clean_stopped += 1
                    false.append((s["id"], out["decision"], [f["msg"] for f in out["findings"]]))
        res[mode] = dict(caught=caught, defects=n_def, stopped_wrong_reason=wrong_reason, clean_stopped=clean_stopped,
                         clean=n_clean, per_defect=dict(per), misses=misses, false_stops=false)
    total = Counter(s["defect"] for s in sessions if s["defect"])
    return dict(set=which, sessions=len(sessions), defects_by_kind=dict(total), results=res)


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "dev"
    r = run(which)
    print(f"{which}: {r['sessions']} sessions, {sum(r['defects_by_kind'].values())} with a planted defect")
    for m, x in r["results"].items():
        print(f"  {MODES[m]:42s} caught {x['caught']:3d}/{x['defects']} (+{x['stopped_wrong_reason']} stopped for another reason)"
              f"   clean stopped {x['clean_stopped']}/{x['clean']}")
    print("\nper defect (claim / note / full):")
    for d, n in sorted(r["defects_by_kind"].items()):
        print(f"  {d:24s} {n:3d}   " + "  ".join(f"{r['results'][m]['per_defect'].get(d, 0):3d}" for m in MODES))
    if len(sys.argv) > 2:
        json.dump(r, open(sys.argv[2], "w"), indent=1)
