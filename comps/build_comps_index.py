#!/usr/bin/env python3
"""
build_comps_index.py -- builds the data file behind the RRR Quick Comp tool.

Reads, on Vaughn's machine, the two foundations:

  1. ACTUAL SOLD   -- the RRR Comp CaNNon sqlite
                      (Projects\\Metrics\\RRR_Comp_Cannon\\_staging\\rrr_comp_cannon.sqlite)
                      comp_items, both sides: source='RRR' (E2) and source='Anderson' (E3).

  2. ACTIVE RULED  -- the ruled artifacts
                      (Projects\\Platform Data Agent\\Pricing_Ruled\\*.json)
                      header identity + MSRP + the seven ruled rungs.

Writes comps-data.json next to index.html.

WHAT THIS SCRIPT NEVER DOES
  - It never writes to the cannon or to any ruled artifact. Read-only, both.
  - It never emits acquisition cost, margin, or profit. The tool is a comp
    surface; what we paid is not comp evidence and must not leave the machine.

Usage
  python build_comps_index.py \
      --cannon  "C:\\...\\RRR_Comp_Cannon\\_staging\\rrr_comp_cannon.sqlite" \
      --ruled   "C:\\...\\Platform Data Agent\\Pricing_Ruled" \
      --out     "comps-data.json"

  --limit N       cap sold rows (smoke tests)
  --schema-only   print the detected cannon schema mapping and exit
"""

import argparse, json, os, re, sqlite3, statistics, sys, glob
from collections import defaultdict
from datetime import datetime, timezone

# --- canon: brand tier boundaries -------------------------------------------
# brand_tier_classification.md v1.0.4, apparel defaults. Median of combined
# RRR + Anderson sold. Brands under MIN_N are tier_unknown and are NEVER
# offered as peers -- an unclassified brand is not a safe comp.
TIER_BOUNDS = [("premium", 39.0), ("mid-high", 35.0), ("mid-low", 29.0)]
TIER_VALUE = "value"
MIN_N_FOR_TIER = 5

# Cannon locks a cohort at the first level reaching this pooled n (_universal.md).
LOCK_N = 5

# style codes live in raw_description free text; comp_items.style_code is NULL
# across all rows (SKILL.md schema hazards). Match NP124 / NQ890 / G1234 shapes.
STYLE_RE = re.compile(r"\b([A-Z]{1,3}\d{3,6})\b")

# Column-name candidates. The cannon has been rebuilt more than once; detect
# rather than assume, and fail loudly naming what was missing.
CANDIDATES = {
    "source":      ["source", "src", "store"],
    "brand":       ["brand"],
    "title":       ["raw_title", "title", "item_title", "name"],
    "description": ["raw_description", "description", "raw_desc", "notes"],
    "price":       ["price", "sold_price", "sold_for", "soldfor", "sale_price"],
    "date":        ["date_sold", "sold_date", "sold_at", "date"],
    "platform":    ["platform", "marketplace", "sold_on"],
    "cat":         ["internal_cat", "category", "cat"],
    "subcat":      ["sub_cat", "subcategory", "subcat"],
    "size":        ["size"],
    "color":       ["color", "colour", "colorway"],
    "cond":        ["condition", "cond", "item_condition"],
    "style":       ["style_code", "style", "style_number"],
}
REQUIRED = ["source", "title", "price"]


def norm_brand(b):
    """Join key only. lowercase, &->and, strip non-alphanumerics.

    This clears the benign variants (J. Crew / J Crew, Levi's / Levis) that a
    naive substring test reports as 37.9% contamination when it is really a
    join-key problem (Conductor audit 2026-07-27). It is applied to the TOOL's
    in-memory key only -- the cannon is not touched, and the normalisation
    proposal itself is still awaiting Vaughn.
    """
    if not b:
        return ""
    b = str(b).strip().lower().replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", "", b)


def money(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return round(float(v), 2) if float(v) > 0 else None
    s = re.sub(r"[^0-9.\-]", "", str(v))
    if not s or s in {"-", "."}:
        return None
    try:
        f = float(s)
    except ValueError:
        return None
    return round(f, 2) if f > 0 else None


def detect(conn, table):
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
    if not cols:
        sys.exit(f"ERROR: table '{table}' not found in the cannon.")
    lower = {c.lower(): c for c in cols}
    mapping, missing = {}, []
    for key, opts in CANDIDATES.items():
        hit = next((lower[o] for o in opts if o in lower), None)
        if hit:
            mapping[key] = hit
        elif key in REQUIRED:
            missing.append(f"{key} (looked for: {', '.join(opts)})")
    if missing:
        sys.exit("ERROR: cannon is missing required columns:\n  - " +
                 "\n  - ".join(missing) + f"\nColumns present: {', '.join(cols)}")
    return mapping, cols


def load_sold(path, limit=None, schema_only=False):
    if not os.path.exists(path):
        sys.exit(f"ERROR: cannon not found: {path}")
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    mapping, cols = detect(conn, "comp_items")

    if schema_only:
        print(f"comp_items columns: {', '.join(cols)}\n")
        for k in CANDIDATES:
            print(f"  {k:12s} -> {mapping.get(k) or '(absent)'}")
        sys.exit(0)

    sel = ", ".join(f'"{v}" AS "{k}"' for k, v in mapping.items())
    sql = f"SELECT {sel} FROM comp_items"
    if limit:
        sql += f" LIMIT {int(limit)}"

    rows, dropped = [], 0
    for r in conn.execute(sql):
        d = dict(r)
        price = money(d.get("price"))
        if price is None:
            dropped += 1          # unpriced row is not sold evidence
            continue
        title = (d.get("title") or "").strip()

        # style_code column is NULL cannon-wide; recover it from the
        # description body, then the title. Free-text match on free text --
        # logged as such, never presented as a structured field.
        style = (d.get("style") or "").strip().upper()
        if not style:
            for blob in (d.get("description"), title):
                if blob:
                    m = STYLE_RE.search(str(blob).upper())
                    if m:
                        style = m.group(1)
                        break

        src = (d.get("source") or "").strip()
        src = "RRR" if src.upper() == "RRR" else ("Anderson" if src else "?")

        rows.append({
            "src": src,
            "brand": (d.get("brand") or "").strip(),
            "bkey": norm_brand(d.get("brand")),
            "title": title,
            "style": style,
            "cat": (d.get("cat") or "").strip(),
            "subcat": (d.get("subcat") or "").strip(),
            "size": (d.get("size") or "").strip(),
            "color": (d.get("color") or "").strip(),
            "cond": (d.get("cond") or "").strip(),
            "price": price,
            "date": (str(d.get("date") or "")[:10]),
            "plat": (d.get("platform") or "").strip(),
        })
    conn.close()
    return rows, dropped, mapping


def leaf(v):
    """Ruled artifacts use the Data Conductor leaf convention:
    {value, source, state, locked}. Accept a leaf or a bare value."""
    if isinstance(v, dict):
        if v.get("state") == "EMPTY":
            return None, v.get("source") or v.get("reason")
        return v.get("value"), v.get("source")
    return v, None


def load_ruled(folder):
    """Read ruled artifacts -- the ACTIVE prices already ruled.

    Honours _INDEX.json as the current-version pointer when present; a ruled
    price is never erased, so without the index an older version of a SKU can
    otherwise shadow the current one.
    """
    if not folder or not os.path.isdir(folder):
        return [], []

    current = None
    idx_path = os.path.join(folder, "_INDEX.json")
    if os.path.exists(idx_path):
        try:
            with open(idx_path, encoding="utf-8") as f:
                idx = json.load(f)
            if isinstance(idx, dict):
                pointer = idx.get("current") or idx.get("items") or idx
                if isinstance(pointer, dict):
                    current = {str(k): str(v) for k, v in pointer.items()
                               if isinstance(v, str)}
        except Exception as e:
            print(f"  note: _INDEX.json unreadable ({e}) -- reading all artifacts", file=sys.stderr)

    out, gap = [], []
    for p in sorted(glob.glob(os.path.join(folder, "**", "*.json"), recursive=True)):
        base = os.path.basename(p)
        if base.startswith("_") or os.sep + "_archive" + os.sep in p:
            continue
        try:
            with open(p, encoding="utf-8") as f:
                a = json.load(f)
        except Exception:
            continue
        if not isinstance(a, dict) or "t1_recommendation" not in a:
            continue

        sku = a.get("sku") or ""
        if current and sku in current and os.path.basename(current[sku]) != base:
            continue                      # superseded version

        h = a.get("header") or {}
        def hv(*names):
            for n in names:
                if n in h:
                    val, src = leaf(h[n])
                    if val not in (None, ""):
                        return val, src
            return None, None

        msrp, msrp_src = hv("retail_price", "msrp", "original_price")
        msrp = money(msrp)

        # The seven rung keys the item record uses (amendment 7). t1 is a LIST
        # of dicts from v2.2 forward; older artifacts shipped a dict -- read both
        # rather than dropping a real ruled price on a shape technicality.
        rungs = {}
        t1 = a.get("t1_recommendation")
        entries = t1 if isinstance(t1, list) else (
            list(t1.values()) if isinstance(t1, dict) else [])
        for e in entries:
            if not isinstance(e, dict):
                continue
            k = str(e.get("rung") or e.get("label") or "").strip().upper()
            val, _ = leaf(e.get("ruled"))
            val = money(val)
            if k and val:
                rungs[k] = val

        brand, _ = hv("brand")
        model, _ = hv("model_name", "model")
        style, _ = hv("style_number", "style_code", "style")

        rec = {
            "sku": sku,
            "brand": (brand or "").strip(),
            "bkey": norm_brand(brand),
            "model": (model or "").strip(),
            "style": str(style or "").strip().upper(),
            "size": str(hv("size")[0] or "").strip(),
            "color": str(hv("color", "colour")[0] or "").strip(),
            "cond": str(hv("condition")[0] or "").strip(),
            "msrp": msrp,
            "msrp_src": msrp_src or "",
            "rungs": rungs,
            "ruled_date": str(a.get("ruled_date") or "")[:10],
            "file": base,
        }
        out.append(rec)
        if not msrp:
            gap.append(sku or base)
    return out, gap


def build_tiers(sold):
    """Brand tier from combined RRR + Anderson median. Under MIN_N -> unknown.

    Tier is the guard that keeps Old Navy out of a J.Crew comp set, so a brand
    we cannot classify is excluded rather than guessed into a peer set.
    """
    by = defaultdict(list)
    label = {}
    for r in sold:
        if r["bkey"]:
            by[r["bkey"]].append(r["price"])
            label.setdefault(r["bkey"], r["brand"])

    tiers = {}
    for k, prices in by.items():
        n = len(prices)
        med = round(statistics.median(prices), 2)
        if n < MIN_N_FOR_TIER:
            tier = "tier_unknown"
        else:
            tier = TIER_VALUE
            for name, floor in TIER_BOUNDS:
                if med >= floor:
                    tier = name
                    break
        tiers[k] = {"brand": label[k], "tier": tier, "n": n, "median": med}
    return tiers


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cannon", required=True)
    ap.add_argument("--ruled", default="")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "comps-data.json"))
    ap.add_argument("--limit", type=int)
    ap.add_argument("--schema-only", action="store_true")
    args = ap.parse_args()

    sold, dropped, mapping = load_sold(args.cannon, args.limit, args.schema_only)
    print(f"cannon: {len(sold)} priced sold rows ({dropped} unpriced dropped)")

    per_src = defaultdict(list)
    for r in sold:
        per_src[r["src"]].append(r)
    fresh = {}
    for s, rs in per_src.items():
        dates = [r["date"] for r in rs if r["date"]]
        fresh[s] = {"n": len(rs), "max_date_sold": max(dates) if dates else ""}
        print(f"  {s}: n={len(rs)} through {fresh[s]['max_date_sold'] or '(no dates)'}")

    ruled, gap = load_ruled(args.ruled)
    print(f"ruled: {len(ruled)} current artifacts, {len(gap)} without MSRP")

    tiers = build_tiers(sold)
    known = sum(1 for v in tiers.values() if v["tier"] != "tier_unknown")
    print(f"tiers: {known} brands classified, {len(tiers)-known} below n>={MIN_N_FOR_TIER}")

    cols = ["src", "brand", "bkey", "title", "style", "cat", "subcat",
            "size", "color", "cond", "price", "date", "plat"]
    doc = {
        "schema": "rrr-comps-index/1.0",
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "is_demo": False,
        "sources": {
            "cannon": os.path.basename(args.cannon),
            "ruled": os.path.basename(args.ruled.rstrip("/\\")) if args.ruled else "",
            "column_map": mapping,
        },
        "freshness": fresh,
        "policy": {
            "tier_bounds": {n: f for n, f in TIER_BOUNDS},
            "min_n_for_tier": MIN_N_FOR_TIER,
            "lock_n": LOCK_N,
            "excludes": "acquisition cost, margin and profit are never emitted",
        },
        "brand_tiers": tiers,
        "cols": cols,
        "sold": [[r[c] for c in cols] for r in sold],
        "ruled": ruled,
        "msrp_gap": gap,
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(doc, f, separators=(",", ":"), ensure_ascii=False)
    mb = os.path.getsize(args.out) / 1048576
    print(f"\nwrote {args.out} ({mb:.2f} MB)")

    if gap:
        report = os.path.join(os.path.dirname(args.out) or ".", "msrp-gap.txt")
        with open(report, "w", encoding="utf-8") as f:
            f.write("Ruled SKUs with no MSRP captured\n")
            f.write(f"built {doc['built_at']}  n={len(gap)}\n\n")
            f.write("\n".join(gap) + "\n")
        print(f"wrote {report} -- {len(gap)} SKUs need an MSRP")


if __name__ == "__main__":
    main()
