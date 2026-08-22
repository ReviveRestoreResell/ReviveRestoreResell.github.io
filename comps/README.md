# Quick Comp

A comp lookup built on our own two foundations, and nothing else:

| Foundation | Source | What it is |
|---|---|---|
| **Actual sold** | Comp CaNNon — `comp_items` | RRR sold (**E2**) and Anderson sold (**E3**), counted separately |
| **Active ruled** | `Pricing_Ruled\*.json` | MSRP + the seven ruled rungs. These are **asks**, not solds |

Type a SKU, a brand, a style code, or words from a title. You get the MSRP,
what we are already asking, and a comp ladder that starts at the exact style.

---

## Running the build

The tool is a static page; the data is built on whichever machine holds the
CaNNon and the ruled folder.

```bash
python build_comps_index.py \
  --cannon "…\Projects\Metrics\RRR_Comp_Cannon\_staging\rrr_comp_cannon.sqlite" \
  --ruled  "…\Projects\Platform Data Agent\Pricing_Ruled" \
  --out    "comps-data.json"
```

Check the column mapping first if the CaNNon has been rebuilt:

```bash
python build_comps_index.py --cannon "…\rrr_comp_cannon.sqlite" --schema-only
```

It writes two files:

- `comps-data.json` — the tool's data
- `msrp-gap.txt` — every ruled SKU with **no MSRP captured**

The script is **read-only** against both sources. It never writes to the
CaNNon and never touches a ruled artifact.

## Loading the data

`index.html` looks for `comps-data.json` beside it. If it isn't there, the page
offers a file picker — pick the JSON off disk and it runs entirely in the
browser, nothing uploaded.

**This repository is a public GitHub Pages site.** `robots.txt` asks crawlers
away; it does not make anything private. So the real `comps-data.json` is
deliberately *not* committed. The committed file is a synthetic demo, flagged
in red at the top of the page, with a button to swap in the real one.

To use it for real, either keep the JSON local and use the picker, or publish
it somewhere access-controlled. Either way the builder **never emits
acquisition cost, margin, or profit** — a comp surface has no business
carrying what we paid.

---

## The comp ladder

Most specific first. It stops at the first level holding **n ≥ 5** and marks
it `ANCHOR`; everything below stays open so you can see what it was measured
against.

| Level | What it is |
|---|---|
| `EXACT` | Same brand **and** same style code — the closest thing to the item itself |
| `STYLE` | Same style code where the brand column disagrees or is `UNKNOWN` |
| `MODEL` | Same brand, title carrying the model wording |
| `BRAND` | Same brand, same category |
| `PEER` | **Competing brands at the same tier only** |

### The tier guard

`PEER` is the level that answers "Old Navy is not a comp to a designer brand."
Peer brands must be in the **same tier** as the subject, and must actually sell
the subject's category. Tiers are computed from combined RRR + Anderson median
per `brand_tier_classification.md`:

```
premium   median ≥ $39      mid-low   $29 – $34.99
mid-high  $35 – $38.99      value     < $29
```

A brand with fewer than 5 sold rows is **`tier_unknown` and is never offered
as a peer** — an unclassified brand is not a safe comp.

Every brand the guard blocks is **named on the page**, with its tier and
median. The block is visible, not silent. When the subject's own brand is too
thin to classify, the tier is inferred from MSRP (≥$200 premium · $100–199
mid-high · $50–99 mid-low · <$50 value) and the page says so.

### What the numbers do and don't say

- RRR (E2) and Anderson (E3) are always split. They are never pooled into one
  median.
- **At n ≤ 4 no median is shown** — every individual price is listed instead.
  Four numbers are not a distribution.
- Ruled prices render in amber and are labelled *our ask, not a sold*. They are
  a ceiling and context; they never enter a median.
- An empty level says so as a measured zero. A zero we counted and a query we
  never ran are different facts.

### Style codes

`comp_items.style_code` is NULL across the whole CaNNon. The builder recovers
codes (`NP124`, `G4471`) from the `raw_description` body, then the title. It is
a free-text match on a free-text field, and is treated as such — good enough to
partition on, never presented as a structured field.

### Brand keys

Brands are matched on a normalised key (lowercase, `&`→`and`, non-alphanumerics
stripped) so `J. Crew` and `J.Crew` are one brand. This is the tool's in-memory
join key only — the CaNNon is not modified, and the normalisation proposal
itself is still with Vaughn.

---

## What this tool is not

It does not price anything. No rung is derived here, nothing is ruled here, and
nothing is written back. `pricing-plus` owns the price; this is the fast look
at what our own data already knows.

It also holds no external comps — eBay/Terapeak and Poshmark sold (**E1**) are
gathered live during a pricing run and are outside this surface.

---

## Backfilling style codes into the CaNNon

`comp_items.style_code` is NULL on every row, so CaNNon cascade **tier 1
(brand + style_code) has never fired** — every comp lookup has silently started
at tier 2 or lower. The codes are not missing; they sit in `raw_description`.

```bash
python backfill_style_codes.py --cannon "…\rrr_comp_cannon.sqlite"            # dry run
python backfill_style_codes.py --cannon "…\rrr_comp_cannon.sqlite" --review   # + held queue
python backfill_style_codes.py --cannon "…\rrr_comp_cannon.sqlite" --apply    # write
python backfill_style_codes.py --cannon "…\rrr_comp_cannon.sqlite" --rollback RUN_ID
```

**Dry run is the default and writes nothing.** Read its report first — it shows
what would be written, why each candidate was rejected, and how many brand+style
cohorts would actually reach n ≥ 5 and let tier 1 lock.

### Why precision is the whole job

The cascade locks at the **first** tier reaching n ≥ 5. A wrong code at tier 1
therefore anchors a price on the wrong garment, and nothing downstream catches
it. A NULL is only the status quo; a wrong value is a new silent error. Every
rule in `style_codes.py` is biased to reject, and only **HIGH** confidence is
ever written.

Three defences, weakest to strongest:

1. **Denylist.** Garment tags are full of numbers shaped exactly like style
   codes — `RN`, `CA`, `WPL` registration numbers, measurements (`W28`, `26 in`),
   size systems (`US29`), platform ids (`UPC`, `SKU`, `ASIN`). Rejected on the
   token *and* on the word in front of it.
2. **Marker.** `Style`, `Style #`, `Style No.` introduces a trusted candidate.
   This is the only path that accepts a digits-only code.
3. **Consensus.** The strongest signal, and the reason this beats a regex: a real
   style code recurs across rows of the same brand. Seen on ≥ 2 rows of one
   brand → corroborated. A one-off is not written unless its prefix is already
   established for that brand. Consensus is **per-brand**, so a Madewell code
   appearing on a Levi's row is not written — the brand column carries 311
   measured contradictions.

Two competing equally-supported candidates on one row → **nothing is written**.
An ambiguous row is where a wrong code does the most damage.

Measured on a 58-case labelled corpus (`tests/test_style_codes.py`), half of it
adversarial: **100% precision, 100% recall.** Run it with
`python tests/test_style_codes.py`.

### Safety

- Dry run by default; `--apply` required to write.
- `--apply` **refuses** unless `style_code` is 100% NULL, so the write is purely
  additive and cannot overwrite anyone's work. `--force` to override deliberately.
- A timestamped file backup is taken before any write.
- The write is a single transaction — it commits fully or not at all.
- Every decision (written, held, rejected) lands in the `style_code_backfill`
  audit table with its run id and reasoning.
- `--rollback RUN_ID` restores exactly.
- Re-running is safe: rows already carrying a code are skipped.
- Dry run always works, even on an already-backfilled CaNNon.

### The silent-failure guard

If a brand genuinely numbers its styles with a denylisted prefix (`CA100`,
`CA101`…), the denylist would silence it and the result would look identical to
a brand with no codes at all. The report flags these as **possible denylist
collisions** — a brand that yielded no codes while one prefix was rejected
repeatedly. Their doctrine 12 applies: an empty tier is a claim and must be
proven.

### After a CaNNon re-import

New rows arrive with `style_code` NULL. Re-run the backfill after each import;
it only fills NULLs, so it is safe to run every time.

`build_comps_index.py` uses the **same** extraction engine, so the tool and the
CaNNon always agree. It prefers the real column and falls back to free-text
recovery only where the column is still NULL.
