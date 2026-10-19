"""Three synthetic sessions where the claim and the note agree with each other, but not with the recording."""
import json, sys
import gen
from claimcheck import check, parse

sys.stdout.reconfigure(encoding="utf-8")
REG = json.load(open("data/registry.json"))
BANK = json.load(open("data/bank_dev.json", encoding="utf-8"))

for seed, defect, title in [(5, "admin_padding", "Note and claim say 60-minute psychotherapy"),
                            (10, "si_contradicted", "Note says the client denies SI"),
                            (2, "audio_billed_as_video", "Note says video, claim has modifier 95")]:
    s = gen.make(seed, BANK, defect)
    c = s["claim"]
    print("=" * 78)
    print(f"{title}   |   claim: {' + '.join(c['cpt'])}  POS {c['pos']}  {' '.join(c['modifiers'])}  ({REG['payers'][c['payer']]['name']})")
    print("-" * 78)
    for line in s["note"].splitlines():
        if line.strip():
            print("  note | " + line)
    span = parse.clinical_span(s["transcript"])
    print(f"  recording | clinical talk {span[0] // 60}:{span[0] % 60:02d}-{span[1] // 60}:{span[1] % 60:02d}"
          f"  ({(span[1] - span[0]) / 60:.0f} min); then: " + " / ".join(x["text"] for x in s["transcript"] if x["t"] >= span[1])[:120])
    if s["platform"]["media"]:
        print("  platform  | " + ", ".join(f"{a // 60}-{b // 60} min {k}" for a, b, k in s["platform"]["media"]))
    out = check.check(s, REG["clinicians"], REG["payers"])
    print(f"\n  -> {out['decision']}")
    for f in out["findings"]:
        print(f"     {f['code']}: {f['msg']}\n       fix: {f['fix']}\n       rule: {f['cite']}")
    base = check.check(s, REG["clinicians"], REG["payers"], mode="note")
    print(f"     (checking the note alone: {base['decision']})")
