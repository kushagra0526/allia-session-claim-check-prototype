"""Check one session's claim against its note, its recording and the rules.

mode="full"   note + transcript + platform log (this)
mode="note"   trusts the note for time and modality (no recording)
mode="claim"  claim fields + registry only (a typical claim scrubber)
"""
import re
from . import parse

# CPT psychotherapy time bands (minutes); add-ons count psychotherapy time only
BANDS = {"90832": (16, 37), "90834": (38, 52), "90837": (53, 999),
         "90833": (16, 37), "90836": (38, 52), "90838": (53, 999)}
THERAPY = {"90832", "90834", "90837"}
ADDON = {"90833": "90832", "90836": "90834", "90838": "90837"}
EM = {"99212", "99213", "99214", "99215"}
EM_CREDS = {"MD", "DO", "PMHNP", "NP", "PA"}
IC_OK = THERAPY | set(ADDON) | {"90791", "90792"}
LEVEL = {"BLOCK": 3, "HOLD": 2, "FIX": 1}
TOL = 1  # minutes of slack on recorded time

CITES = {
    "TIME_CODE": "CPT psychotherapy time bands: 90832 16-37, 90834 38-52, 90837 53+ min",
    "TIME_EVIDENCE": "Time billed must be face-to-face clinical time; scheduling/payment talk does not count",
    "START_STOP": "Payer profile requires actual start and stop times for timed psychotherapy",
    "ADDON_EM": "90833/90836/90838 are add-ons to an E/M on the same day; psychotherapy time documented separately from E/M",
    "CREDENTIAL": "E/M codes are billed by prescribers (MD/DO/NP/PA), not by LCSW/LPC/LMFT/psychologists",
    "MODALITY": "Telehealth: POS 10 at home / 02 elsewhere; video modifier vs audio-only modifier per payer profile",
    "LICENSE_STATE": "Clinician must be licensed where the patient is located at the time of the session",
    "ENROLLMENT": "Rendering clinician must be enrolled with the payer",
    "IC_90785": "90785 only with psychotherapy/diagnostic codes, not crisis; needs a documented qualifying reason",
    "CRISIS": "90839 first 30-74 min; 90840 each additional 30 min; not with 90785 or 90832-90838",
    "RISK_DOC": "Client statement of suicidal thinking needs a documented risk assessment that matches it",
    "CLONED": "Payers treat near-identical notes across visits as cloned documentation",
}


def code_for(minutes, addon=False):
    for c, (a, b) in BANDS.items():
        if (c in ADDON) == addon and a <= minutes <= b:
            return c
    return None


def shingles(text, k=5):
    w = re.sub(r"\d", "#", text.lower()).split()
    return {" ".join(w[i:i + k]) for i in range(len(w) - k + 1)}


def check(s, registry, payers, mode="full"):
    note, claim = s["note"], s["claim"]
    cpt = claim["cpt"]
    clin = registry[claim["clinician"]]
    payer = payers[claim["payer"]]
    plat = s["platform"]
    f = []

    def add(code, level, msg, fix=""):
        f.append(dict(code=code, level=level, msg=msg, fix=fix, cite=CITES[code]))

    # -------- who / where --------
    if claim["payer"] not in clin["payers"]:
        add("ENROLLMENT", "HOLD", f"{clin['name']} is not enrolled with {payer['name']}", "bill under an enrolled clinician or hold for enrollment")
    em = [c for c in cpt if c in EM]
    if em and clin["cred"] not in EM_CREDS:
        add("CREDENTIAL", "BLOCK", f"{clin['cred']} billing E/M {em[0]}", "bill psychotherapy-only code by time")
    if mode == "claim":
        state = claim["patient_address_state"]
    elif mode == "note":
        m = re.search(r"\b([A-Z]{2})\b(?=[^\n]*(home|located|location|traveling|travelling))|(?:located|location)[^\n]*?\b([A-Z]{2})\b", note)
        state = (m[1] or m[3]) if m else claim["patient_address_state"]
    else:
        state = plat["patient_state"]
    if state and state not in clin["states"]:
        add("LICENSE_STATE", "BLOCK", f"patient located in {state} at the session; {clin['name']} licensed in {', '.join(clin['states'])}",
            "do not bill; reschedule when the patient is in a licensed state")

    # -------- code combinations --------
    addons = [c for c in cpt if c in ADDON]
    if addons and not em:
        add("ADDON_EM", "FIX", f"{addons[0]} billed without an E/M code", "add the E/M or bill the stand-alone code")
    if "90785" in cpt:
        if not any(c in IC_OK for c in cpt) or "90839" in cpt:
            add("IC_90785", "FIX", "90785 with a code it can't be added to", "remove 90785")
        elif mode != "claim" and not parse.interactive_complexity_reason(note):
            add("IC_90785", "FIX", "90785 billed but the note gives no qualifying reason", "document the reason or remove 90785")
    if "90839" in cpt and any(c in BANDS for c in cpt):
        add("CRISIS", "FIX", "90839 with a 90832-90838 code on the same claim", "bill one or the other")

    if mode == "claim":
        return _decide(f)

    # -------- time --------
    times = parse.note_times(note)
    stated = parse.note_minutes(note)
    if times and not stated:
        stated = times[1] - times[0]
    timed = [c for c in cpt if c in BANDS or c in ("90839", "90840")]
    if timed and payer["start_stop_required"] and not times:
        add("START_STOP", "FIX", "no start/stop times in the note", "add actual start and stop clock times")

    if mode == "full":
        span = parse.clinical_span(s["transcript"])
        recorded = (span[1] - span[0]) / 60
    else:
        recorded = None

    for c in cpt:
        if c in THERAPY:
            if stated is not None and code_for(stated) != c:
                add("TIME_CODE", "FIX", f"{c} billed, note documents {stated} min", f"bill {code_for(stated) or 'nothing (<16 min)'}")
            if recorded is not None and recorded + TOL < BANDS[c][0]:
                add("TIME_EVIDENCE", "FIX", f"{c} needs {BANDS[c][0]}+ min; recording shows {recorded:.0f} min of clinical talk"
                    + (f" (note says {stated})" if stated else ""), f"bill {code_for(int(recorded + TOL)) or 'nothing (<16 min)'}")
        elif c in ADDON:
            pt = parse.psychotherapy_minutes(note)
            if pt is None:
                add("ADDON_EM", "FIX", f"{c} billed but psychotherapy time is not documented separately from E/M",
                    "document psychotherapy minutes separate from the E/M")
            elif code_for(pt, addon=True) != c:
                add("TIME_CODE", "FIX", f"{c} billed, note documents {pt} min of psychotherapy", f"bill {code_for(pt, addon=True) or 'no add-on'}")
            if pt is not None and recorded is not None and recorded + TOL < pt + 5:
                add("TIME_EVIDENCE", "FIX", f"{pt} min psychotherapy + E/M does not fit in {recorded:.0f} recorded min", "correct the psychotherapy time")
        elif c == "90839":
            mins = recorded if recorded is not None else stated
            if mins is not None and mins + (TOL if recorded is not None else 0) < 30:
                add("CRISIS", "FIX", f"90839 needs 30+ min; {'recording shows' if recorded is not None else 'note says'} {mins:.0f}",
                    f"bill {code_for(int(mins + TOL)) or 'nothing'}")
            n40 = cpt.count("90840")
            if mins is not None and n40 and mins + TOL < 75 + 30 * (n40 - 1):
                add("CRISIS", "FIX", f"90840 x{n40} needs {75 + 30 * (n40 - 1)}+ min", "remove 90840")

    # -------- modality --------
    mod = claim["modifiers"]
    pos = claim["pos"]
    if mode == "full":
        if plat["in_person"]:
            actual = "in_person"
        else:
            actual = "video" if parse.video_share(plat["media"], parse.clinical_span(s["transcript"])) >= 0.5 else "audio"
        home = plat["patient_at_home"]
    else:
        actual = parse.note_modality(note) or ("in_person" if pos == "11" else "video")
        home = pos == "10" if actual != "in_person" else False
    if actual == "in_person":
        if pos != "11" or set(mod) & {"95", "93"}:
            add("MODALITY", "FIX", "in-person session billed as telehealth", "POS 11, no telehealth modifier")
    else:
        want_pos = payer["pos_home"] if home else payer["pos_other"]
        if actual == "audio" and payer["audio_only"] is None:
            add("MODALITY", "HOLD", f"session was audio-only; {payer['name']} doesn't cover audio-only", "hold: patient/payer decision")
        else:
            want_mod = payer["audio_only"] if actual == "audio" else payer["video_modifier"]
            if want_mod not in mod or (actual == "audio" and payer["video_modifier"] in mod) or pos != want_pos:
                add("MODALITY", "FIX", f"{actual} session billed with POS {pos} {'+'.join(mod) or 'no modifier'}",
                    f"POS {want_pos} + {want_mod}")

    if mode != "full":
        return _decide(f)

    # -------- risk documentation (needs the recording) --------
    si = parse.si_statements(s["transcript"])
    if si:
        t, text = si[0]
        risk = parse.note_risk(note)
        stamp = f"{int(t // 60)}:{int(t % 60):02d}"
        if risk == "denies":
            add("RISK_DOC", "HOLD", f'note says client denies SI; at {stamp} client said "{text}"', "clinician to review and correct the risk assessment")
        elif risk == "none":
            add("RISK_DOC", "FIX", f'no risk assessment in note; at {stamp} client said "{text}"', "clinician to document risk assessment")

    # -------- cloned note --------
    if s.get("prev_note"):
        a, b = shingles(note), shingles(s["prev_note"])
        if a and b and len(a & b) / len(a | b) > 0.8:
            add("CLONED", "FIX", f"note {100 * len(a & b) / len(a | b):.0f}% identical to the previous visit's note", "rewrite from this session")
    return _decide(f)


def _decide(findings):
    lvl = max((LEVEL[x["level"]] for x in findings), default=0)
    return dict(decision={3: "BLOCK", 2: "HOLD", 1: "FIX", 0: "SUBMIT"}[lvl], findings=findings)
