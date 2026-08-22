#!/usr/bin/env python3
"""
backfill_style_codes.py -- populate comp_items.style_code in the RRR Comp CaNNon.

WHY
  `comp_items.style_code` is NULL on all ~10,046 rows, so CaNNon cascade tier 1
  (brand + style_code) cannot fire and never has. Every comp lookup has silently
  started at tier 2 or lower. The codes exist -- they sit in `raw_description`.
  This restores the tier.

SAFETY MODEL
  - Dry run is the DEFAULT. Nothing is written without --apply.
  - --apply refuses unless style_code is 100% NULL, so the write is purely
    additive and can never overwrite someone's work. Override with --force only
    deliberately.
  - A timestamped file backup is taken before any write.
  - The write runs in ONE transaction. It commits fully or not at all.
  - Every decision -- written, held, rejected -- lands in the `style_code_backfill`
    audit table with its run id and reasoning. Nothing is lost.
  - --rollback restores exactly, using that audit table.
  - Only HIGH-confidence codes are written. MED and LOW are recorded for review
    and left out of the column.
  - Re-running is safe: rows already carrying a code are skipped.

Usage
  python backfill_style_codes.py --cannon PATH                 # dry run + report
  python backfill_style_codes.py --cannon PATH --apply         # write
  python backfill_style_codes.py --cannon PATH --rollback RUN  # undo
  python backfill_style_codes.py --cannon PATH --review        # MED/LOW queue
"""

import argparse, os, re, shutil, sqlite3, sys, json
from collections import defaultdict, Counter
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from style_codes import Extractor, norm_brand          # noqa: E402
from build_comps_index import detect                    # noqa: E402

AUDIT = "style_code_backfill"
LOCK_N = 5          # the CaNNon locks a tier at pooled n >= 5


def connect(path, writable=False):
    if not os.path.exists(path):
        sys.exit("ERROR: cannon not found: %s" % path)
    if writable:
        c = sqlite3.connect(path)
    else:
        c = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
    c.row_factory = sqlite3.Row
    return c


def preflight(conn, mapping, force, writing):
    """The column must be entirely NULL for this to be a purely additive write.

    The refusal binds only a real write. A dry run must always be allowed to
    run and report -- refusing to even LOOK at an already-backfilled cannon
    would make the tool useless exactly when someone needs to inspect it."""
    col = mapping.get("style")
    if not col:
        sys.exit("ERROR: comp_items has no style_code column to backfill.\n"
                 "       Add one first:  ALTER TABLE comp_items ADD COLUMN style_code TEXT;")
    total = conn.execute("SELECT COUNT(*) FROM comp_items").fetchone()[0]
    filled = conn.execute(
        'SELECT COUNT(*) FROM comp_items WHERE "%s" IS NOT NULL AND TRIM("%s") <> ""'
        % (col, col)).fetchone()[0]
    print("  rows: %d   style_code already populated: %d" % (total, filled))
    if filled and writing and not force:
        sys.exit("\nREFUSING TO WRITE. %d rows already carry a style_code, so this would\n"
                 "no longer be a purely additive backfill. Inspect those rows first;\n"
                 "pass --force only if you intend to fill the remaining NULLs anyway."
                 % filled)
    return total, filled


def gather(conn, mapping, limit=None):
    """Feed every row through the extractor."""
    sel = ["rowid AS _rid"]
    for k in ("brand", "description", "title", "style", "source", "subcat"):
        if mapping.get(k):
            sel.append('"%s" AS "%s"' % (mapping[k], k))
    sql = "SELECT %s FROM comp_items" % ", ".join(sel)
    if limit:
        sql += " LIMIT %d" % int(limit)

    ex, meta = Extractor(), {}
    for r in conn.execute(sql):
        d = dict(r)
        rid = d["_rid"]
        meta[rid] = {"brand": d.get("brand") or "", "source": d.get("source") or "",
                     "subcat": d.get("subcat") or "",
                     "existing": (d.get("style") or "").strip(),
                     "desc": (d.get("description") or "")[:160]}
        ex.add(rid, d.get("brand"), d.get("description"), d.get("title"))
    return ex, meta


def report(results, meta, ex, total):
    """Everything the operator needs to judge the run before committing."""
    by_conf = Counter(r["confidence"] or "NONE" for r in results)
    high = [r for r in results if r["confidence"] == "HIGH"]
    skip = [r for r in high if meta[r["id"]]["existing"]]
    write = [r for r in high if not meta[r["id"]]["existing"]]

    print("\n=== EXTRACTION ===")
    for k in ("HIGH", "MED", "LOW", "AMBIGUOUS", "NONE"):
        if by_conf.get(k):
            print("  %-10s %6d" % (k, by_conf[k]))
    print("  %-10s %6d  (%.1f%% of rows)" % ("writable", len(write),
                                             100.0 * len(write) / max(total, 1)))
    if skip:
        print("  %-10s %6d  (already carry a code — skipped)" % ("skipped", len(skip)))

    print("\n=== WHY CANDIDATES WERE REJECTED ===")
    for reason, n in sorted(ex.rejects.items(), key=lambda x: -x[1])[:12]:
        print("  %6d  %s" % (n, reason))

    # tier-1 impact: how many brand+style cohorts actually become lockable
    cohort = Counter()
    for r in write:
        cohort[(r["bkey"], r["code"])] += 1
    for r in high:
        if meta[r["id"]]["existing"]:
            cohort[(r["bkey"], meta[r["id"]]["existing"].upper())] += 1
    lockable = [c for c, n in cohort.items() if n >= LOCK_N]
    print("\n=== TIER-1 IMPACT ===")
    print("  distinct brand+style cohorts created : %d" % len(cohort))
    print("  cohorts reaching n>=%d (tier 1 can LOCK): %d" % (LOCK_N, len(lockable)))
    print("  rows inside a lockable cohort        : %d"
          % sum(n for c, n in cohort.items() if n >= LOCK_N))

    top = sorted(((n, c) for c, n in cohort.items()), reverse=True)[:12]
    if top:
        print("\n  largest cohorts:")
        for n, (b, code) in top:
            print("    n=%-4d %-22s %s" % (n, b[:22], code))

    coll = ex.collisions()
    if coll:
        print("\n=== ⚠ POSSIBLE DENYLIST COLLISIONS ===")
        print("  These brands yielded NO codes while a denylisted prefix was rejected")
        print("  repeatedly. If the brand really numbers its styles that way, the")
        print("  denylist is silencing it and this needs a human eye.")
        for c in coll[:10]:
            print("    %-24s prefix %-5s rejected on %d rows" %
                  (c["brand"][:24], c["prefix"], c["rows"]))

    print("\n=== SAMPLE (20 writes, eyeball these) ===")
    for r in write[:20]:
        m = meta[r["id"]]
        print("  %-8s %-18s -> %-9s %s" % (r["id"], (m["brand"] or "?")[:18],
                                           r["code"], r["why"][:44]))
        print("           %s" % m["desc"][:96].replace("\n", " "))
    return write


def apply(path, mapping, write, results, meta, run_id):
    col = mapping["style"]
    backup = "%s.bak-%s" % (path, run_id)
    shutil.copy2(path, backup)
    print("\nbackup: %s" % backup)

    conn = connect(path, writable=True)
    try:
        conn.execute("BEGIN")
        conn.execute("""CREATE TABLE IF NOT EXISTS %s(
            run_id TEXT, rowid_ref INTEGER, brand TEXT, code TEXT,
            confidence TEXT, why TEXT, source TEXT, prior TEXT,
            written INTEGER, created_at TEXT)""" % AUDIT)
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")

        # audit EVERY decision, not only the writes -- a held row is a finding
        conn.executemany(
            "INSERT INTO %s VALUES(?,?,?,?,?,?,?,?,?,?)" % AUDIT,
            [(run_id, r["id"], meta[r["id"]]["brand"], r["code"], r["confidence"],
              r["why"], r["source"], meta[r["id"]]["existing"] or None,
              1 if (r["confidence"] == "HIGH" and not meta[r["id"]]["existing"]) else 0,
              stamp) for r in results if r["confidence"]])

        conn.executemany(
            'UPDATE comp_items SET "%s"=? WHERE rowid=?' % col,
            [(r["code"], r["id"]) for r in write])
        conn.execute("COMMIT")
    except Exception as e:
        conn.execute("ROLLBACK")
        conn.close()
        sys.exit("WRITE FAILED, nothing committed: %s\nRestore from %s if needed." % (e, backup))

    n = conn.execute(
        'SELECT COUNT(*) FROM comp_items WHERE "%s" IS NOT NULL AND TRIM("%s")<>""'
        % (col, col)).fetchone()[0]
    print("verified: %d rows now carry a style_code (expected %d)" % (n, len(write)))
    print("run id  : %s" % run_id)
    print("undo    : --rollback %s" % run_id)
    conn.close()


def rollback(path, mapping, run_id):
    col = mapping["style"]
    conn = connect(path, writable=True)
    rows = conn.execute(
        "SELECT rowid_ref, prior FROM %s WHERE run_id=? AND written=1" % AUDIT,
        (run_id,)).fetchall()
    if not rows:
        sys.exit("No written rows found for run %s." % run_id)
    conn.execute("BEGIN")
    conn.executemany('UPDATE comp_items SET "%s"=? WHERE rowid=?' % col,
                     [(r["prior"], r["rowid_ref"]) for r in rows])
    conn.execute("DELETE FROM %s WHERE run_id=?" % AUDIT, (run_id,))
    conn.execute("COMMIT")
    print("rolled back %d rows from run %s" % (len(rows), run_id))
    conn.close()


def review(results, meta):
    """The MED/LOW/AMBIGUOUS queue -- candidates deliberately not written."""
    q = [r for r in results if r["confidence"] in ("MED", "LOW", "AMBIGUOUS")]
    print("\n=== REVIEW QUEUE (%d rows, none written) ===" % len(q))
    for r in q[:120]:
        m = meta[r["id"]]
        print("  [%s] %-9s %-18s %-8s %s" % (r["confidence"], r["id"],
              (m["brand"] or "?")[:18], r["code"] or "-", r["why"][:50]))
        print("        %s" % m["desc"][:100].replace("\n", " "))
    if len(q) > 120:
        print("  ... and %d more" % (len(q) - 120))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cannon", required=True)
    ap.add_argument("--apply", action="store_true", help="write (default is dry run)")
    ap.add_argument("--force", action="store_true", help="write even if some codes exist")
    ap.add_argument("--rollback", metavar="RUN_ID")
    ap.add_argument("--review", action="store_true")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()

    conn = connect(args.cannon, writable=False)
    mapping, _ = detect(conn, "comp_items")

    if args.rollback:
        conn.close()
        return rollback(args.cannon, mapping, args.rollback)

    print("cannon : %s" % args.cannon)
    print("mode   : %s" % ("APPLY" if args.apply else "DRY RUN — nothing will be written"))
    total, filled = preflight(conn, mapping, args.force, writing=args.apply)

    ex, meta = gather(conn, mapping, args.limit)
    conn.close()
    results = ex.run()
    write = report(results, meta, ex, total)

    if args.review:
        review(results, meta)

    if not args.apply:
        print("\nDRY RUN — nothing written. Re-run with --apply to commit %d codes."
              % len(write))
        return

    if not write:
        print("\nNothing to write.")
        return
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    apply(args.cannon, mapping, write, results, meta, run_id)


if __name__ == "__main__":
    main()
