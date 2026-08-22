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
