# Paste this into Claude Code on the PC

Everything below is one prompt. Copy it whole. You don't need to do anything
else — no paths to find, no commands to run, no questions to answer.

---

```
Run the Comp CaNNon style-code backfill end to end. Do not ask me questions —
I don't know the answers and I don't want to make any decisions. You have full
authority to figure it out, fix problems yourself, and finish the job. Report
back at the end in plain English.

END GOAL
The Comp CaNNon's most specific comp tier (brand + style code) has never worked,
because the style_code column is empty on every row. The codes are sitting in the
description text. Put them where they belong, then show me a working comp lookup
built on my real data.

THE CODE ALREADY EXISTS — don't write your own.
Repo: https://github.com/ReviveRestoreResell/ReviveRestoreResell.github.io
Branch: claude/quick-access-comp-tool-6158g1

If the repo is already on this machine, pull that branch. Otherwise clone it
somewhere sensible and check that branch out. Everything you need is in comps/.
Read comps/README.md first.

STEP 1 — find my data
Search this machine (OneDrive included) for:
  - rrr_comp_cannon.sqlite   (likely under Projects\Metrics\RRR_Comp_Cannon\_staging\)
  - the Pricing_Ruled folder (likely under Projects\Platform Data Agent\)
Use the newest/most complete copy if you find more than one, and say which you
picked and why. If you genuinely cannot find the sqlite, stop and tell me the
exact filename to look for — that is the ONLY thing worth interrupting me for.

STEP 2 — dry run, and read the report yourself
  python comps\backfill_style_codes.py --cannon "<path>" --review
This writes nothing. Read the whole report. Sanity-check the sample writes: does
each extracted code actually appear in that row's description, and does it look
like a style code rather than a tag number?

STEP 3 — apply it
  python comps\backfill_style_codes.py --cannon "<path>" --apply

You may do this without checking with me. It is safe by construction:
  - it refuses to run at all unless style_code is 100% empty, so it can only add
  - it takes a timestamped backup of the sqlite before writing
  - the write is a single transaction — all or nothing
  - every decision is logged to a style_code_backfill audit table
  - --rollback <RUN_ID> undoes it exactly
  - only HIGH-confidence codes are written; anything uncertain is held back

If the report shows POSSIBLE DENYLIST COLLISIONS, note them and CARRY ON. A
collision means codes were MISSED for that brand, never that a wrong one was
written — it cannot corrupt anything. Just list the affected brands for me.

If anything fails, fix it and retry. If the write itself fails it rolls back on
its own; restore from the .bak file if you need to and tell me what happened.

STEP 4 — verify it actually worked
Confirm, by querying the sqlite:
  - how many rows now carry a style_code
  - that none of them start with RN, CA, or WPL (those are garment tag numbers,
    not style codes — any of those means something went wrong, so roll back)
  - how many distinct brand+style groups now have 5 or more sold rows, because
    that is the number that decides whether the comp tier can actually fire

STEP 5 — build the comp tool on my real data
  python comps\build_comps_index.py --cannon "<path>" --ruled "<Pricing_Ruled path>"
Then open comps\index.html in a browser and confirm it loads MY data, not the
demo. Search a SKU you can see in Pricing_Ruled and check the top comp level says
"Exact — brand + style code".

comps-data.json is gitignored on purpose — it holds real sales data and this repo
is a public site. Do not commit it, do not publish it. Leave it on this machine.

STEP 6 — tell me one more thing
Print the CaNNon's full column list:
  python comps\backfill_style_codes.py --cannon "<path>" --schema-only
I specifically need to know whether comp_items has a "vid" or any listing-id
column. That decides whether we can link what I ruled a price at to what it
actually sold for. Just report what's there.

REPORT BACK, in plain English, no jargon:
  1. how many style codes went in, and how many rows still have none
  2. how many comp groups are now big enough for the exact tier to fire
  3. any brands flagged for collisions
  4. whether the comp tool opens on my real data
  5. whether a vid / listing-id column exists
  6. the rollback command, in case I want to undo it later

Do not commit or push anything unless I ask. This is all local.
```

---

## If it goes wrong

Everything is reversible. The backfill prints a run id like `20260822T043245Z`.
To undo:

```
python comps\backfill_style_codes.py --cannon "<path>" --rollback <RUN_ID>
```

There is also a `.bak-<runid>` copy of the sqlite sitting next to the original.
