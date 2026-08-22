#!/usr/bin/env python3
"""
style_codes.py -- style-code extraction for the RRR Comp CaNNon.

`comp_items.style_code` is NULL across every row, so CaNNon cascade tier 1
(brand + style_code) can never fire. The codes are not missing -- they sit in
`raw_description` free text. This module recovers them.

PRECISION IS THE WHOLE JOB. Tier 1 is the most-specific tier and the cascade
locks at the FIRST tier reaching n>=5, so a wrong code there anchors a price on
the wrong garment and nothing downstream would catch it. A NULL is merely the
status quo; a wrong value is a new, silent, load-bearing error. Every rule below
is therefore biased to reject.

Three defences, in order of strength:

  1. DENYLIST      Garment tags are full of regulatory numbers that look exactly
                   like style codes -- RN, CA, WPL -- plus measurements and
                   platform ids. These are rejected on the token and on the word
                   in front of it.
  2. MARKER        A candidate introduced by "Style", "Style #", "Style No"
                   is trusted on its own. This is the only path that accepts a
                   digits-only code.
  3. CONSENSUS     The strongest signal available and the reason this beats a
                   regex: a real style code recurs across rows of the same
                   brand. A token seen on >=2 rows of one brand is corroborated.
                   A one-off is not written unless its prefix is already
                   established for that brand.

Anything not reaching HIGH is recorded for review, never written.
"""

import re
from collections import defaultdict

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# Letters+digits, e.g. NP124, MJ923, G4471, AE900. Optional single trailing
# letter (some lines suffix a fit/wash variant). Anchored on word boundaries.
TOKEN_RE = re.compile(r"\b([A-Z]{1,4}-?\d{3,6}[A-Z]?)\b")

# An explicit marker. This is the ONLY path that may accept a digits-only code,
# because "Style 12345" is unambiguous while a bare 12345 is not.
MARKER_RE = re.compile(
    r"\b(?:style|stylenumber|style\s*(?:#|no\.?|num(?:ber)?|code)?)\s*[:#]?\s*"
    r"([A-Z]{0,4}-?\d{3,6}[A-Z]?)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Denylists
# ---------------------------------------------------------------------------

# Prefixes that are never style codes. RN / CA / WPL are on virtually every US
# and Canadian garment tag and are the single largest false-positive source in
# apparel resale text.
BAD_PREFIX = {
    # regulatory / label
    "RN", "CA", "WPL", "PA", "PMS", "DWR", "FR",
    # identifiers
    "UPC", "EAN", "ISBN", "SKU", "ITEM", "ID", "REF", "NO", "NUM", "MPN", "ASIN",
    # internal handling
    "LOT", "BIN", "POD", "PO", "RACK", "SLOT", "BOX", "TOTE", "B",
    # sizing systems
    "US", "EU", "UK", "FR", "IT", "AU", "JP", "SZ", "SIZE",
    # measurements
    "W", "L", "IN", "CM", "MM", "OZ", "LB", "KG", "ML", "QTY", "PC", "PCS",
    "INSEAM", "WAIST", "BUST", "CHEST", "HIP", "RISE", "LEN",
}

# A candidate is rejected when one of these is the word immediately before it,
# which catches the space-separated forms ("RN 12345", "size 29").
BAD_PRECEDING = {
    "rn", "ca", "wpl", "pa", "upc", "ean", "isbn", "asin", "mpn",
    "sku", "item", "id", "ref", "no", "num", "number",
    "lot", "bin", "pod", "po", "rack", "slot", "box", "tote", "batch",
    "size", "sz", "us", "eu", "uk", "fr", "it", "au", "jp",
    "waist", "inseam", "bust", "chest", "hip", "rise", "length", "width",
    "measures", "measurement", "approx", "approximately",
    "tracking", "order", "invoice", "phone", "tel",
}

# Words after which a number is a measurement, not a code.
BAD_FOLLOWING = {"inch", "inches", "cm", "mm", "oz", "lb", "lbs", "kg",
                 "ml", "percent", "%"}

# Tokens that are a size expressed with a letter, e.g. W28, L32, US29.
SIZEY_RE = re.compile(r"^(?:W|L|US|EU|UK|SZ|IN)\d{1,3}$")

# A 4-digit run in the modern era read as a year, with a 0-1 letter prefix.
YEARISH_RE = re.compile(r"^[A-Z]?(?:19|20)\d{2}$")

MIN_ROWS_FOR_CONSENSUS = 2   # distinct rows, same brand, before a token is real
MIN_CODES_FOR_PREFIX = 3     # distinct corroborated codes before a prefix counts


def norm_brand(b):
    """Join key. Mirrors build_comps_index.norm_brand so 'J. Crew' and 'J.Crew'
    are one brand for consensus purposes."""
    if not b:
        return ""
    b = str(b).strip().lower().replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", "", b)


def _reject(tok, text, start, end, marked=False):
    """Return a reason string when this candidate must be rejected, else None.

    `marked` suppresses the preceding-word test only: the word in front of a
    marked candidate is the marker itself ("Style No. G4471"), so reading it as
    context would reject the very codes the marker exists to identify. The
    prefix test still applies -- "Style RN12345" is still an RN number."""
    m = re.match(r"^([A-Z]+)", tok)
    prefix = m.group(1) if m else ""

    if prefix in BAD_PREFIX:
        return "prefix '%s' is a label/measurement code, not a style" % prefix
    if SIZEY_RE.match(tok):
        return "reads as a size, not a style"
    if YEARISH_RE.match(tok):
        return "reads as a year"

    if not marked:
        before = text[max(0, start - 24):start].lower()
        w = re.findall(r"[a-z#]+", before)
        if w and w[-1].strip("#") in BAD_PRECEDING:
            return "preceded by '%s'" % w[-1].strip("#")

    # A measurement never carries a letter prefix, so this test applies only to
    # digits-only tokens. Without the guard, "MJ923 in light wash" reads as
    # inches and a real code is thrown away.
    if not prefix:
        after = text[end:end + 14].lower()
        wa = re.findall(r"[a-z%]+", after)
        if wa and wa[0] in BAD_FOLLOWING:
            return "followed by '%s' — a measurement" % wa[0]
    return None


def candidates(text):
    """Every surviving candidate in one blob, each as (token, marked, reason).

    `marked` means an explicit Style marker introduced it. Rejected candidates
    come back with a reason so the run can be audited rather than trusted."""
    if not text:
        return []
    up = str(text).upper()
    out, seen = [], set()

    for m in MARKER_RE.finditer(str(text)):
        tok = m.group(1).upper().replace("-", "")
        if not tok or tok in seen:
            continue
        # a marked candidate still may not be a denylisted form
        r = _reject(tok, up, m.start(1), m.end(1), marked=True)
        seen.add(tok)
        out.append((tok, True, r))

    for m in TOKEN_RE.finditer(up):
        raw = m.group(1)
        tok = raw.replace("-", "")
        if tok in seen:
            continue
        seen.add(tok)
        out.append((tok, False, _reject(tok, up, m.start(1), m.end(1))))
    return out


class Extractor:
    """Two-pass extractor. Pass 1 learns what real codes look like for each
    brand; pass 2 decides each row against that evidence."""

    def __init__(self):
        self.rows = []
        self.tok_rows = defaultdict(set)     # (bkey, token) -> {row ids}
        self.marked = set()                  # (bkey, token) seen with a marker
        self.brand_prefixes = defaultdict(set)
        self.rejects = defaultdict(int)

    def add(self, rid, brand, description, title=None):
        """Register a row. Description is authoritative; the title is a weaker
        fallback searched only when the description yields nothing."""
        bkey = norm_brand(brand)
        cands = candidates(description)
        src = "description"
        if not any(c[2] is None for c in cands) and title:
            t = candidates(title)
            if any(c[2] is None for c in t):
                cands, src = t, "title"
        self.rows.append((rid, bkey, cands, src))
        for tok, marked, reason in cands:
            if reason:
                self.rejects[reason.split(" —")[0]] += 1
                continue
            self.tok_rows[(bkey, tok)].add(rid)
            if marked:
                self.marked.add((bkey, tok))

    def learn(self):
        """Establish, per brand, which prefixes carry corroborated codes."""
        for (bkey, tok), rids in self.tok_rows.items():
            if len(rids) >= MIN_ROWS_FOR_CONSENSUS or (bkey, tok) in self.marked:
                p = re.match(r"^([A-Z]+)", tok)
                if p:
                    self.brand_prefixes[bkey].add((p.group(1), tok))
        self.known_prefix = {
            b: {p for p, _ in s
                if len({t for pp, t in s if pp == p}) >= MIN_CODES_FOR_PREFIX}
            for b, s in self.brand_prefixes.items()
        }

    def decide(self, rid, bkey, cands, src):
        """Return (code, confidence, why, alternatives) for one row.

        HIGH is the only confidence that may be written. Two competing HIGH
        candidates on one row resolve to no code at all -- an ambiguous row is
        exactly the row a wrong code would do the most damage on."""
        live = [(t, m) for t, m, r in cands if r is None]
        if not live:
            return None, None, "no candidate survived the denylist", []

        scored = []
        for tok, marked in live:
            n = len(self.tok_rows.get((bkey, tok), ()))
            prefix = (re.match(r"^([A-Z]+)", tok) or [None, ""])[1]
            if marked:
                scored.append((3, n, tok, "explicit Style marker"))
            elif n >= MIN_ROWS_FOR_CONSENSUS:
                scored.append((2, n, tok, "corroborated on %d rows of this brand" % n))
            elif prefix and prefix in self.known_prefix.get(bkey, set()):
                scored.append((1, n, tok, "prefix '%s' established for this brand" % prefix))
            else:
                scored.append((0, n, tok, "single occurrence, unestablished prefix"))

        scored.sort(key=lambda x: (-x[0], -x[1], x[2]))
        rank, n, tok, why = scored[0]
        alts = [s[2] for s in scored[1:]]

        if rank == 0:
            return None, "LOW", why, alts
        if rank == 1:
            return tok, "MED", why, alts
        if len(scored) > 1 and scored[1][0] == rank and scored[1][2] != tok:
            return None, "AMBIGUOUS", \
                "two equally-supported candidates (%s, %s) — refusing to guess" % (tok, scored[1][2]), alts
        return tok, "HIGH", why, alts

    def collisions(self):
        """Prefixes rejected repeatedly for a brand that ends up with no codes.

        This is the denylist's own failure mode. If a brand really does number
        its styles CA100, CA101 ... the denylist silences it and the result is
        indistinguishable from a brand with no codes on record. Surfacing the
        collision turns a silent zero into a reviewable finding."""
        blocked = defaultdict(lambda: defaultdict(int))
        for rid, bkey, cands, src in self.rows:
            for tok, marked, reason in cands:
                if reason and "is a label" in reason:
                    pre = (re.match(r"^([A-Z]+)", tok) or [None, ""])[1]
                    blocked[bkey][pre] += 1
        accepted = defaultdict(int)
        for (bkey, tok), rids in self.tok_rows.items():
            accepted[bkey] += 1
        out = []
        for bkey, prefs in blocked.items():
            if accepted.get(bkey):
                continue                      # brand yields codes elsewhere
            for pre, n in prefs.items():
                if n >= 3:                    # a pattern, not a stray tag line
                    out.append({"brand": bkey, "prefix": pre, "rows": n})
        return sorted(out, key=lambda x: -x["rows"])

    def run(self):
        """Decide every registered row. Returns a list of dicts."""
        self.learn()
        out = []
        for rid, bkey, cands, src in self.rows:
            code, conf, why, alts = self.decide(rid, bkey, cands, src)
            out.append({"id": rid, "bkey": bkey, "code": code, "confidence": conf,
                        "why": why, "source": src if code else None,
                        "alternatives": alts})
        return out
