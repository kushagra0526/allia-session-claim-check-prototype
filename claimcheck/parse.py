"""Read an AI-drafted progress note and a session transcript.

Note: start/stop clock times, total minutes, separate psychotherapy minutes,
modality, location, risk documentation (endorses / denies / none), 90785 reason.
Transcript: clinical minutes (scheduling, payment and goodbye talk at the ends
don't count), video share, and client statements of suicidal thinking (negated,
past, third-person and question echoes filtered out).
"""
import re

NUM_WORDS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
    "sixteen seventeen eighteen nineteen".split())}
NUM_WORDS.update({"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
                  "eighty": 80, "ninety": 90})
_TENS = "twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety"
_UNITS = "one|two|three|four|five|six|seven|eight|nine"
NUM = rf"(\d{{1,3}}|(?:{_TENS})(?:[- ](?:{_UNITS}))?|{'|'.join(NUM_WORDS)})"


def to_int(s):
    s = s.lower()
    if s.isdigit():
        return int(s)
    parts = re.split(r"[- ]", s)
    return sum(NUM_WORDS[p] for p in parts)


AMPM = r"\s*(a\.?\s?m\.?|p\.?\s?m\.?)?"
CLOCK = re.compile(r"(?<![\d/.:])([01]?\d|2[0-3])[:.]([0-5]\d)(?![\d/])" + AMPM, re.I)
MILITARY = re.compile(r"\b([01]\d|2[0-3])([0-5]\d)\s*(?:-|–|to|until)\s*([01]\d|2[0-3])([0-5]\d)\b")
MINUTES = re.compile(NUM + r"[- ]?(?:minutes?|mins?)\b", re.I)


def _mins(h, m, ap):
    h, m = int(h), int(m)
    if ap:
        pm = ap.lower().startswith("p")
        h = h % 12 + (12 if pm else 0)
    return h * 60 + m


def note_times(note):
    """(start, stop) in minutes after midnight, or None. Takes the first two clock
    times in the note; a missing am/pm is taken from the other time."""
    m = MILITARY.search(note)
    if m:
        a, b = int(m[1]) * 60 + int(m[2]), int(m[3]) * 60 + int(m[4])
        return (a, b) if b > a else None
    found = [(x[1], x[2], x[3]) for x in CLOCK.finditer(note)][:2]
    if len(found) < 2:
        return None
    (h1, m1, ap1), (h2, m2, ap2) = found
    ap1, ap2 = ap1 or ap2, ap2 or ap1
    a, b = _mins(h1, m1, ap1), _mins(h2, m2, ap2)
    if b <= a and not (ap1 or ap2) and int(h2) < 12:  # 11:40 - 12:35 / 1:05 without am/pm
        b += 12 * 60
    return (a, b) if 0 < b - a < 240 else None


def _pt_match(line):
    """The minutes figure tied to 'psychotherapy' on a line that separates it from E/M."""
    l = line.lower()
    if "psychotherapy" not in l or not any(w in l for w in ("e/m", "separate", "add-on", "distinct")):
        return None
    k = l.index("psychotherapy")
    ms = list(MINUTES.finditer(line))
    after = [m for m in ms if m.start() > k]          # "Psychotherapy time ...: 42 minutes"
    return after[0] if after else (ms[-1] if ms else None)  # "42 minutes of psychotherapy"


def note_minutes(note):
    """Total minutes: the first minutes figure that isn't the separate psychotherapy figure."""
    for line in note.splitlines():
        pt = _pt_match(line)
        for m in MINUTES.finditer(line):
            if pt is None or m.start() != pt.start():
                return to_int(m[1])
    return None


def psychotherapy_minutes(note):
    """Minutes the note attributes to psychotherapy separately from E/M."""
    for line in note.splitlines():
        pt = _pt_match(line)
        if pt:
            return to_int(pt[1])
    return None


def note_modality(note):
    n = note.lower()
    if re.search(r"audio[- ]only|telephone|by phone|phone session|phone call", n):
        return "audio"
    if re.search(r"video|zoom|telehealth|virtual", n):
        return "video"
    if re.search(r"in[- ]person|in[- ]office|in clinic|office visit", n):
        return "in_person"
    return None


RISK_ANY = re.compile(r"risk assessment|c-ssrs|columbia|safety plan|\bsi\b|suicid|self[- ]harm|risk:", re.I)
DENIES = re.compile(r"(denie[sd]|denying|no (current |active |reported )?(si|suicidal|thoughts of (self[- ]harm|suicide)))", re.I)
ENDORSES = re.compile(r"(endorse[sd]?|reported|reports|disclosed|expressed|acknowledged|voiced|described)\s+(\w+\s+){0,3}"
                      r"(si\b|suicidal|thoughts of (ending|suicide|death|not being alive)|passive|wish(es)? to die)", re.I)


def note_risk(note):
    """'endorses' / 'denies' / 'none'."""
    if ENDORSES.search(note):
        return "endorses"
    if DENIES.search(note):
        return "denies"
    return "documented" if RISK_ANY.search(note) else "none"


IC_REASON = re.compile(r"(caregiver|parent|mother|father|interfered|guardian|third[- ]party|sentinel|mandated report|play (equipment|therapy)|"
                       r"maladaptive communication|disagree|conflict(ing)? between)", re.I)


def interactive_complexity_reason(note):
    return bool(IC_REASON.search(note))


# ---------------- transcript ----------------
ADMIN = re.compile(r"(schedul|next week|same time|reschedul|calendar|copay|co-pay|insurance|invoice|"
                   r"\bbill(ing)?\b|portal|send (me |you )?(a |the )?link|appointment|\bbye\b|take care|see you|"
                   r"talk (to you )?soon|book (you|it|the)|card on file|receipt|reminder|statement|"
                   r"\b(mon|tues|wednes|thurs|fri|satur|sun)days?\b|have a good (week|weekend|day))", re.I)


def clinical_span(transcript):
    """Seconds (start, end) of clinical talk: drop scheduling/payment/goodbye lines at the ends."""
    lines = transcript
    i, j = 0, len(lines) - 1
    while i <= j and ADMIN.search(lines[i]["text"]):
        i += 1
    while j >= i and ADMIN.search(lines[j]["text"]):
        j -= 1
    if i > j:
        return (0, 0)
    end = lines[j + 1]["t"] if j + 1 < len(lines) else lines[j]["t"] + 15
    return (lines[i]["t"], end)


def video_share(media, span):
    a, b = span
    if b <= a:
        return 0.0
    v = sum(max(0, min(t1, b) - max(t0, a)) for t0, t1, kind in media if kind == "video")
    return v / (b - a)


SI = re.compile(r"(kill(ing)? myself|end(ing)? (my life|it( all)?)\b|not (to )?wake up|better off without me|"
                r"(want(ed)?|wish(ed)?|wanting) (I could |to )?(just )?die|wasn'?t here|not be(ing)? here|"
                r"(no|don'?t see the|don'?t see any) point (in |of )?(living|being alive|going on)|hurt(ing)? myself|suicid|overdos|how many pills|"
                r"driv(e|ing) (off|into)|thoughts of (dying|death|ending))", re.I)
NEG = re.compile(r"\b(no|not|never|nothing|don'?t|didn'?t|wouldn'?t|won'?t|isn'?t|aren'?t|haven'?t had|without)\b", re.I)
PAST = re.compile(r"(years ago|when I was|back (in|when)|used to|in the past|a long time|haven'?t (felt|thought)|"
                  r"anymore since|as a (kid|teen)|in high school|in college)", re.I)
THIRD = re.compile(r"\b(he|she|they|his|her|their)\b", re.I)
FIRST = re.compile(r"\b(I|I'm|I've|I'd|me|my|myself)\b")


def si_statements(transcript):
    """Client lines that state current suicidal thinking: [(t, text)]."""
    out = []
    for ln in transcript:
        if ln["spk"] != "client":
            continue
        for sent in re.split(r"(?<=[.!?])\s+", ln["text"]):
            m = SI.search(sent)
            if not m:
                continue
            before = sent[:m.start()]
            if sent.rstrip().endswith("?") and len(sent) < 40:      # "Suicide? ..." echoing a question
                continue
            if NEG.search(before[-40:]) and "wish" not in before.lower():
                continue
            if PAST.search(sent):
                continue
            # owned by someone else: a third-person pronoun after the last first-person word
            fp = list(FIRST.finditer(before))
            tail = before[fp[-1].end():] if fp else before
            if THIRD.search(tail) and "myself" not in m[0].lower():
                continue
            out.append((ln["t"], sent.strip()))
            break
    return out
