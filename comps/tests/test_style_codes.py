#!/usr/bin/env python3
"""Labelled corpus for style-code extraction.

Every case is text of the kind that actually appears in Vendoo descriptions.
The adversarial half is drawn from what genuinely sits on garment tags -- RN and
CA registration numbers, WPL numbers, measurements, size systems, platform ids.

Precision is the metric that matters. A missed code leaves tier 1 where it
already is; a wrong code anchors a price on the wrong garment.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from style_codes import Extractor

# (row_id, brand, description, expected_code)  expected None = must not write
CASES = [
    # --- explicit markers -------------------------------------------------
    ("m1", "Madewell", "Style NP124. The Melody Smocked Midi Dress in black.", "NP124"),
    ("m2", "Madewell", "Style #NP571 — tiered maxi, size XS.", "NP571"),
    ("m3", "J. Crew",  "Style No. G4471. Gwen dress, navy.", "G4471"),
    ("m4", "Talbots",  "style code TB204, wool blazer", "TB204"),
    ("m5", "Gap",      "Style: 12345. Cotton tee.", "12345"),   # digits ok WITH marker
    ("m6", "Loft",     "STYLE LF8890 pleated skirt", "LF8890"),

    # --- consensus: same token recurring across rows of one brand ---------
    ("c1", "Madewell", "MJ923 Perfect Vintage Jean, light wash.", "MJ923"),
    ("c2", "Madewell", "Perfect Vintage MJ923 in light wash, size 28.", "MJ923"),
    ("c3", "Madewell", "MJ923 denim, excellent used condition.", "MJ923"),
    ("c4", "Free People", "FP771 Adella wrap mini.", "FP771"),
    ("c5", "Free People", "Adella FP771 rust, size L.", "FP771"),

    # --- established prefix, single sighting -> MED, must NOT be written --
    ("p1", "Madewell", "NP998 smocked dress, one of a kind.", None),

    # --- unestablished single occurrence ---------------------------------
    ("u1", "Wrangler", "ZX447 western shirt.", None),

    # --- ADVERSARIAL: regulatory numbers on garment tags -----------------
    ("a1", "Gap",      "RN 54023 CA 05231. 100% cotton. Made in Vietnam.", None),
    ("a2", "Gap",      "RN54023 tagged, no holes.", None),
    ("a3", "Old Navy", "WPL 12345, machine wash cold.", None),
    ("a4", "Talbots",  "CA02356 wool blend, dry clean only.", None),
    ("a5", "Nike",     "PA 1234 label intact.", None),

    # --- ADVERSARIAL: measurements and sizes -----------------------------
    ("a6",  "Levi's", "Waist 28 inches, inseam 32 inches, rise 10.", None),
    ("a7",  "Levi's", "W28 L32 straight leg.", None),
    ("a8",  "Levi's", "Size US29, fits true.", None),
    ("a9",  "H&M",    "Bust 36 in, length 40 in.", None),
    ("a10", "Zara",   "Measures 21 inches pit to pit.", None),

    # --- ADVERSARIAL: platform and internal identifiers ------------------
    ("a11", "Coach",  "UPC 889532104567, retail $350.", None),
    ("a12", "Coach",  "SKU 44821, bin 12, pod 3.", None),
    ("a13", "Nike",   "Item #99381 from lot 44.", None),
    ("a14", "Nike",   "Tracking 9400111899223", None),
    ("a15", "Puma",   "Order 55231 shipped.", None),

    # --- ADVERSARIAL: years ----------------------------------------------
    ("a16", "Patagonia", "S2019 season piece, great shape.", None),
    ("a17", "Patagonia", "From the 2018 line.", None),

    # --- ADVERSARIAL: ambiguity ------------------------------------------
    # two markers on one row, both explicit -> refuse rather than guess
    ("a18", "Ann Taylor", "Style AT101 replaces style AT102.", None),

    # --- real code sitting beside regulatory noise (the hard case) -------
    ("h1", "Madewell", "Style NQ890. RN 76582 CA 12345. 100% viscose.", "NQ890"),
    ("h2", "Madewell", "NQ890 smocked midi. RN 76582.", "NQ890"),
    ("h3", "Madewell", "NQ890 in pistachio, waist 26 inches.", "NQ890"),

    # --- no code at all ---------------------------------------------------
    ("n1", "Old Navy", "Soft cotton tee, great condition, no flaws.", None),
    ("n2", "H&M",      "Black dress. Machine wash.", None),
    ("n3", "Shein",    "", None),
]


def main():
    ex = Extractor()
    for rid, brand, desc, _ in CASES:
        ex.add(rid, brand, desc)
    got = {r["id"]: r for r in ex.run()}

    tp = fp = fn = tn = 0
    wrong = []
    for rid, brand, desc, want in CASES:
        r = got[rid]
        # only HIGH is ever written, so that is what we score
        have = r["code"] if r["confidence"] == "HIGH" else None
        if want and have == want:      tp += 1
        elif want and have is None:    fn += 1; wrong.append((rid, desc, want, have, r))
        elif want and have != want:    fp += 1; wrong.append((rid, desc, want, have, r))
        elif not want and have:        fp += 1; wrong.append((rid, desc, want, have, r))
        else:                          tn += 1

    prec = tp / (tp + fp) if (tp + fp) else 1.0
    rec  = tp / (tp + fn) if (tp + fn) else 1.0
    print("cases=%d  TP=%d  FP=%d  FN=%d  TN=%d" % (len(CASES), tp, fp, fn, tn))
    print("PRECISION = %.1f%%   RECALL = %.1f%%" % (prec * 100, rec * 100))

    if wrong:
        print("\n--- misses ---")
        for rid, desc, want, have, r in wrong:
            print("  [%s] want=%-6s got=%-6s conf=%-9s %s" %
                  (rid, want, have, r["confidence"], r["why"]))
            print("        %s" % desc[:78])

    print("\n--- rejections by reason ---")
    for reason, n in sorted(ex.rejects.items(), key=lambda x: -x[1]):
        print("  %3d  %s" % (n, reason))

    return 0 if (fp == 0 and fn == 0) else 1


if __name__ == "__main__":
    sys.exit(main())

# --------------------------------------------------------------------------
# Round 2 -- harder adversarial cases, added after round 1 hit 100/100.
# --------------------------------------------------------------------------
HARD = [
    # hyphenated and lowercase forms of real codes
    ("r1", "Madewell", "style np-124 smocked midi", "NP124"),
    ("r2", "Madewell", "np124 black, worn twice", "NP124"),
    ("r3", "Madewell", "Style NP124.", "NP124"),

    # bra / numeric-leading sizes must never match
    ("r4", "Aerie",   "34DD underwire, lightly worn", None),
    ("r5", "Aerie",   "size 2P petite", None),
    ("r6", "Levi's",  "40C wash, tumble dry low", None),

    # care, print and finish codes
    ("r7",  "Patagonia", "DWR 2000 finish still beading", None),
    ("r8",  "Nike",      "PMS 185 red colourway", None),
    ("r9",  "Columbia",  "FR 1234 flame resistant liner", None),

    # postal, phone, price, percentages
    ("r10", "Gap",   "ships from 90210", None),
    ("r11", "Gap",   "call 555-1234 with questions", None),
    ("r12", "Gap",   "retail was 129 dollars", None),
    ("r13", "Gap",   "97% cotton 3% elastane", None),

    # long platform identifiers
    ("r14", "Coach", "eBay item 123456789012", None),
    ("r15", "Coach", "ASIN B07XJ8C8F5 on amazon", None),

    # a token recurring across DIFFERENT brands must not corroborate
    ("x1", "Talbots", "XY555 blazer", None),
    ("x2", "Chico's", "XY555 blouse", None),

    # marker pointing at a regulatory number is still rejected
    ("g1", "Gap", "Style RN54023", None),

    # measurement words either side
    ("r16", "Levi's", "rise 10 inches, leg opening 14 inches", None),
    # cross-brand guard: a Madewell code appearing on a Levi's row must NOT be
    # written. The brand column is contaminated (311 measured contradictions),
    # so consensus is deliberately per-brand and a stray stays unwritten.
    ("r17", "Levi's",   "MJ923 measures 28 inches at waist", None),
    # ...but the same text under its own brand, already corroborated, is taken
    ("r18", "Madewell", "MJ923 measures 28 inches at waist", "MJ923"),
]

def _round2():
    ex = Extractor()
    allcases = CASES + HARD
    for rid, brand, desc, _ in allcases:
        ex.add(rid, brand, desc)
    got = {r["id"]: r for r in ex.run()}
    tp = fp = fn = tn = 0; wrong = []
    for rid, brand, desc, want in allcases:
        r = got[rid]
        have = r["code"] if r["confidence"] == "HIGH" else None
        if want and have == want: tp += 1
        elif want and have is None: fn += 1; wrong.append((rid, desc, want, have, r))
        elif want and have != want: fp += 1; wrong.append((rid, desc, want, have, r))
        elif not want and have: fp += 1; wrong.append((rid, desc, want, have, r))
        else: tn += 1
    prec = tp/(tp+fp) if (tp+fp) else 1.0
    rec = tp/(tp+fn) if (tp+fn) else 1.0
    print("\n===== ROUND 2 (full corpus) =====")
    print("cases=%d  TP=%d  FP=%d  FN=%d  TN=%d" % (len(allcases), tp, fp, fn, tn))
    print("PRECISION = %.1f%%   RECALL = %.1f%%" % (prec*100, rec*100))
    for rid, desc, want, have, r in wrong:
        print("  [%s] want=%-6s got=%-6s conf=%-9s %s" % (rid, want, have, r["confidence"], r["why"]))
        print("        %s" % desc[:78])
    return fp, fn

if __name__ == "__main__":
    pass
