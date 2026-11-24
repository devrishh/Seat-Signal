"""Stop-name normalisation shared by the pipeline scripts (same rules as build_model.py)."""
import re
ABBREV = [
    (r"\bbdr\b", "border"), (r"\bxing\b", "crossing"), (r"\bsec\b", "sector"),
    (r"\bsect\b", "sector"), (r"\bstn\b", "station"), (r"\brly\b", "railway"),
    (r"\bopp\b\.?", "opposite"), (r"\bext\b", "extension"), (r"\bmkt\b", "market"),
    (r"\bclny\b", "colony"), (r"\bhosp\b", "hospital"), (r"\btmnl\b", "terminal"),
]
def norm_stop(name):
    s = re.sub(r"\((t|terminal)\)", " ", str(name).lower())
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    for pat, rep in ABBREV:
        s = re.sub(pat, rep, s)
    return re.sub(r"\s+", " ", s).strip()
