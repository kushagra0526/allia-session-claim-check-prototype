"""Synthetic behavioral-health sessions with known truth: transcript, platform log,
AI-drafted note, claim, previous note. About half carry one planted defect.
All patients, clinicians and payers are made up."""
import json, random

REG = json.load(open("data/registry.json"))
DEFECTS = {  # defect -> the finding code that should catch it
    "upcode_time": "TIME_EVIDENCE", "code_above_note": "TIME_CODE", "missing_start_stop": "START_STOP",
    "audio_billed_as_video": "MODALITY", "out_of_state": "LICENSE_STATE", "non_prescriber_em": "CREDENTIAL",
    "addon_no_pt_time": "ADDON_EM", "si_no_risk_doc": "RISK_DOC", "si_contradicted": "RISK_DOC",
    "ic_no_reason": "IC_90785", "crisis_short": "CRISIS", "cloned_note": "CLONED", "not_enrolled": "ENROLLMENT",
    "admin_padding": "TIME_EVIDENCE",
}
PRESCRIBERS = ["C04", "C05"]


def _clock(m, style):
    h, mm = divmod(m, 60)
    if style == "24":
        return f"{h:02d}:{mm:02d}"
    if style == "mil":
        return f"{h:02d}{mm:02d}"
    ap = "PM" if h >= 12 else "AM"
    h12 = h % 12 or 12
    if style == "dot":
        return f"{h12}.{mm:02d} {'p.m.' if ap == 'PM' else 'a.m.'}"
    if style == "12lower":
        return f"{h12}:{mm:02d}{ap.lower()}"
    return f"{h12}:{mm:02d} {ap}"


def _words(n):
    ones = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
    tens = {2: "twenty", 3: "thirty", 4: "forty", 5: "fifty", 6: "sixty", 7: "seventy", 8: "eighty"}
    if n < 20:
        return ones[n]
    return tens[n // 10] + ("" if n % 10 == 0 else "-" + ones[n % 10])


def make(seed, bank, defect=None):
    r = random.Random(seed)
    B = bank
    kind = r.choices(["therapy", "em_addon", "crisis", "intake"], [60, 20, 8, 12])[0]
    if defect in ("upcode_time", "code_above_note", "admin_padding", "ic_no_reason", "missing_start_stop"):
        kind = "therapy"
    elif defect in ("addon_no_pt_time",):
        kind = "em_addon"
    elif defect == "crisis_short":
        kind = "crisis"
    elif defect == "non_prescriber_em":
        kind = "em_addon"

    if kind == "em_addon":
        cid = r.choice(PRESCRIBERS) if defect != "non_prescriber_em" else r.choice(["C01", "C02", "C03", "C06"])
    else:
        cid = r.choice(sorted(REG["clinicians"]))
    clin = REG["clinicians"][cid]
    payer = r.choice(clin["payers"])
    if defect == "not_enrolled":
        payer = r.choice([p for p in REG["payers"] if p not in clin["payers"]] or ["PAYER_C"])
        if payer in clin["payers"]:
            cid = "C02"; clin = REG["clinicians"][cid]; payer = "PAYER_C"
    if defect == "missing_start_stop" and not REG["payers"][payer]["start_stop_required"]:
        payer = next(p for p in clin["payers"] if REG["payers"][p]["start_stop_required"]) if any(
            REG["payers"][p]["start_stop_required"] for p in clin["payers"]) else payer
        if not REG["payers"][payer]["start_stop_required"]:
            cid, clin, payer = "C01", REG["clinicians"]["C01"], "PAYER_A"
    P = REG["payers"][payer]

    modality = r.choices(["video", "audio", "in_person"], [65, 10, 25])[0]
    if modality == "audio" and P["audio_only"] is None:
        modality = "video"
    if defect == "audio_billed_as_video":
        modality = "video"
    home_state = r.choice(clin["states"])
    at_state = home_state if r.random() < 0.85 else r.choice(clin["states"])
    if defect == "out_of_state":
        modality = "video"
        at_state = r.choice([s for s in B["cities"] if s not in clin["states"]])
    at_home = r.random() < 0.8

    # ---- time ----
    cpt, E, P_min = [], 0, None
    if kind == "therapy":
        code = r.choice(["90832", "90834", "90837"])
        lo, hi = {"90832": (18, 36), "90834": (39, 51), "90837": (54, 60)}[code]
        L = r.randint(lo, hi)
        if defect in ("upcode_time",):
            L = r.randint(38, 49)
        if defect == "code_above_note":
            L, code = r.randint(39, 51), "90834"
        if defect == "admin_padding":
            L, code = r.randint(46, 51), "90837"
        cpt = [code]
    elif kind == "em_addon":
        E = r.randint(8, 15)
        add = r.choice(["90833", "90836"])
        P_min = r.randint(18, 35) if add == "90833" else r.randint(39, 45)
        L = E + P_min
        cpt = [r.choice(["99213", "99214"]), add]
    elif kind == "crisis":
        L = r.randint(32, 70) if r.random() < 0.8 else r.randint(76, 95)
        if defect == "crisis_short":
            L = r.randint(18, 27)
        cpt = ["90839"] + (["90840"] if L >= 75 and defect != "crisis_short" else [])
    else:
        L = r.randint(45, 60)
        cpt = ["90791"]
    A = 0 if r.random() < 0.3 else r.randint(1, 4)
    if defect == "admin_padding":
        A = 53 - L + r.randint(1, 3)
    noted_L = L
    if defect == "upcode_time":
        noted_L = r.randint(53, 58)
        cpt = ["90837"]
    if defect == "admin_padding":
        noted_L = L + A
    if defect == "code_above_note":
        cpt = ["90837"]
    if defect == "ic_no_reason" or (kind in ("therapy", "intake") and r.random() < 0.15):
        cpt.append("90785")

    # ---- transcript ----
    si_kind = None
    if defect in ("si_no_risk_doc", "si_contradicted"):
        si_kind = "pos"
    elif r.random() < 0.12:
        si_kind = "pos"
    elif r.random() < 0.25:
        si_kind = r.choice(["neg", "past", "third"])
    tr, t, spk = [], 0, "clinician"
    si_at = r.randint(120, max(121, L * 60 - 240)) if si_kind else None
    while t < L * 60:
        if si_at is not None and t >= si_at and spk == "client":
            tr.append(dict(t=t, spk="client", text=r.choice(B["si_" + si_kind])))
            si_at = None
            t += r.randint(15, 40)
            if si_kind == "pos":
                tr.append(dict(t=t, spk="clinician", text=r.choice(B["si_followup"])))
                t += r.randint(15, 40)
            spk = "client"
            continue
        tr.append(dict(t=t, spk=spk, text=r.choice(B[spk + "_lines"])))
        t += r.randint(20, 60)
        spk = "client" if spk == "clinician" else "clinician"
    tr = [x for x in tr if x["t"] < L * 60]
    if A == 0:
        tr.append(dict(t=L * 60, spk="clinician", text=B["admin"][-1]))
    else:
        k = max(2, min(len(B["admin"]), A + 1))
        for j, line in enumerate(B["admin"][:k - 1] + [B["admin"][-1]]):
            tr.append(dict(t=L * 60 + j * (A * 60) // (k - 1) if j < k - 1 else (L + A) * 60, spk=["clinician", "client"][j % 2], text=line))

    media = []
    if modality == "video":
        if defect == "audio_billed_as_video":
            cut = r.randint(2, 8) * 60
            media = [[0, cut, "video"], [cut, (L + A) * 60, "audio"]]
        elif r.random() < 0.2:  # brief dropout, still a video session
            d0 = r.randint(60, max(61, L * 60 - 300))
            media = [[0, d0, "video"], [d0, d0 + r.randint(30, 150), "audio"], [d0 + 150, (L + A) * 60, "video"]]
        else:
            media = [[0, (L + A) * 60, "video"]]
    elif modality == "audio":
        media = [[0, (L + A) * 60, "audio"]]
    platform = dict(media=media, patient_state=at_state, patient_at_home=at_home and modality != "in_person",
                    in_person=modality == "in_person")

    # ---- note ----
    start = r.randint(8 * 60, 17 * 60)
    tmpl, style = r.choice(B["time_range"])
    time_line = tmpl.format(s=_clock(start, style), e=_clock(start + noted_L, style))
    payer_needs = P["start_stop_required"]
    if defect == "missing_start_stop" or (not payer_needs and r.random() < 0.5) or kind == "intake" and r.random() < 0.3 and not payer_needs:
        time_line = ""
    dtmpl = r.choice(B["duration"])
    if kind == "em_addon":
        dtmpl = r.choice([d for d in B["duration"] if "psychotherapy" not in d])
    dur_line = dtmpl.format(m=noted_L, mw=_words(noted_L)) if (r.random() < 0.7 or not time_line) else ""
    pt_line = ""
    if kind == "em_addon" and defect != "addon_no_pt_time":
        pt_line = r.choice(B["pt_time"]).format(p=P_min, pw=_words(P_min))
    mod_line = r.choice(B["modality"]["video" if defect == "audio_billed_as_video" else modality])
    loc_state = at_state if (defect != "out_of_state" or r.random() < 0.5) else home_state
    loc_line = "" if modality == "in_person" else r.choice(B["location"]["home" if at_home else "other"]).format(
        city=B["cities"][loc_state], st=loc_state)
    risk = ""
    if si_kind == "pos" and defect != "si_no_risk_doc":
        risk = r.choice(B["risk_deny"] if defect == "si_contradicted" else B["risk_endorse"])
    elif si_kind != "pos" and r.random() < 0.6:
        risk = r.choice(B["risk_deny"])
    ic = r.choice(B["ic_reason"]) if "90785" in cpt and defect != "ic_no_reason" else ""
    body = {k: r.choice(v) for k, v in B["bodies"].items()}
    fmt = r.choice(sorted(B["templates"]))
    date = f"2026-{r.randint(9, 12):02d}-{r.randint(1, 28):02d}"

    assess = r.choice(B["assess"])

    def write(date, body, assess):
        return B["templates"][fmt].format(date=date, clin=clin["name"], time=time_line, dur=dur_line, pt=pt_line,
                                          mod=mod_line, loc=loc_line, risk=risk, ic=ic, A=assess, **body)
    note = write(date, body, assess)
    prev_date = f"2026-{r.randint(5, 8):02d}-{r.randint(1, 28):02d}"
    if defect == "cloned_note":
        prev = write(prev_date, body, assess)
    else:  # a real earlier visit: different content in every section
        prev = write(prev_date, {k: r.choice([x for x in v if x != body[k]] or v) for k, v in B["bodies"].items()},
                     r.choice(B["assess"]))

    # ---- claim ----
    if modality == "in_person":
        pos, mods = "11", []
    else:
        pos = P["pos_home"] if at_home else P["pos_other"]
        mods = [P["audio_only"]] if modality == "audio" else [P["video_modifier"]]
    claim = dict(cpt=cpt, modifiers=mods, pos=pos, payer=payer, clinician=cid, patient_address_state=home_state)
    return dict(id=f"S{seed}", kind=kind, defect=defect, expect=DEFECTS.get(defect), transcript=tr, platform=platform,
                note=note, prev_note=prev, claim=claim, truth=dict(clinical_min=L, admin_min=A, modality=modality, si=si_kind))


def dataset(seeds, bank_path):
    bank = json.load(open(bank_path, encoding="utf-8"))
    out, kinds = [], sorted(DEFECTS)
    for s in seeds:
        r = random.Random(s * 7919)
        out.append(make(s, bank, r.choice(kinds) if r.random() < 0.55 else None))
    return out
