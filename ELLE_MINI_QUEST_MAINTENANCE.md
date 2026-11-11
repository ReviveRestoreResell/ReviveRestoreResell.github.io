# Elle's Mini Cooper Quest — maintenance handoff
Updated: 2026-11-11

## Canonical app and URLs
- Live no-login app: https://reviverestoreresell.github.io/elle_mini_tracker_1.html
- Source file: ReviveRestoreResell/ReviveRestoreResell.github.io / elle_mini_tracker_1.html on main.
- This GitHub Pages tracker is the app the owner and Elle use. Do NOT confuse it with the separate Cloudflare Worker "elle-work-ledger" and D1 database: those are distinct, have Cloudflare Access, and are **not** the canonical Mini Cooper Quest. Do not inadvertently duplicate or overwrite the live GitHub tracker when adjusting the Cloudflare ledger.
- Keep GitHub Pages login-free and retain the existing Mini Cooper road/car design.

## Current accounting rules
- Car goal: $3,000 = 200 hours * $15/hour.
- Progress toward the car = banked CoWork hours * $15 + actual cash deposits toward the car. Existing $200 deposit dated 2026-11-03. For forecast ONLY, assume another $200 on each future 1st of the month; do not book speculative deposits as received.
- Historic 31 worked hours minus 21 redeemed for iPhone = 10 carried forward. Other legacy balances: 10 hours August boxes and 3 miscellaneous; October shipping 1 hour; October Armada vacuum 1 hour. November 3: 2.5 hours; November 4: 1.5 hours; November 5: 4.5 hours, 80+ items; November 10: 5.5 hours, 100+ items. As at November 10, banked total = 39 hours; $585 hours credit + $200 actual deposit = $785 car progress.
- Cash bonuses are **straight cash** and NOT car credits. October: shipping $10, vacuum $10; November 5: $10; November 10: $20. Current cash bonus total $50. For 4+ hours, $10; for 100+ items, total day bonus $20, **not** an additional $20 on top of $10.
- Legacy noncash/item bonuses: May 8 three watches at $10 profit each, May 25 three shoes at $10 profit each = $60 legacy bonus earnings. Effective hourly wage = (hours earned at $15 + legacy bonus profit + cash bonuses) / banked hours, currently ($585 + $60 + $50)/39 = $17.82/hr. Cash bonus and legacy bonus earnings improve effective rate but don't change car progress.
- Preserve separate meanings of base wages/earned, cash deposits, cash bonuses, and legacy item bonuses. Do not count any bonus twice.

## UI requirements as last approved
- Five top badges: HOURS, EARNED, DEPOSITS, TOTAL (earned + deposits), PACE (forecast finish).
- Put milestones immediately below badges; then Effective Rate; then Longest Hustle/Longest Day; then visible Estimated Completion with simple formula; progress bars thereafter.
- PACE is a real clickable button whose handler jumps/scrolls to the Estimated Completion calculation section. Verify listener at runtime; a visually clickable badge without registered behavior was a prior regression.
- Forecast is recalculated from dated work entries in the most recent 14 days, weekly earnings = (hours over 14 days / 2) * $15, plus assumed $200 on each future calendar month 1st; simulate forward until $3,000. As hours/work pace change, forecast can move earlier or later. It is an estimate and can become unreliable if a two-week window has few/no shifts; explain assumptions and consider a more robust fallback if asked.
- Recent Work is a collapsed <details> showing only Monday–Sunday of current and preceding calendar week; older records in collapsed Legacy Hours. Legacy Hours header is the main toggle; include both older post-legacy work and original dated legacy work there without double-counting.
- Cash Deposit Log is a collapsed header/details toggle; Cash Bonus Log stays separate.
- No red X / remove buttons on logged work; owner asked to eliminate accidental deletion.
- App is responsive for a phone; preserve accessibility and readable compact badges/sections.

## Persistence and risk
- The static GitHub Pages app seeds known work entries and bonus history in source. Some modifications made through the app persist in browser localStorage (key elle_mini_log_v11; bonus key elle_mini_bonuses_v4), **not** across devices. Existing browser histories need idempotent migration when seed entries change; never erase browser data or assume the GitHub file holds every manually entered edit.
- Don't treat Cloudflare D1 totals as authoritative for the Mini Cooper app. The separate Cloudflare ledger was found with only a 23h opening balance before three Nov 4/5/10 work entries; that differed from the full GitHub Mini Cooper history (39h).
- Validate after changes: fetch existing HTML and SHA; make targeted patch; save via GitHub update_file with current SHA; fetch again to verify. Check syntax of inline JS, element ID uniqueness, mobile layout, and actual event handlers. Verify the completed site or disclose if only source-level validation was possible. Earlier modification briefly introduced broken JavaScript and a tap control that did nothing; both required correction.
- Do not use Cloudflare authentication or move the project unless explicitly asked. If proposing public write access to hours, caution about unwanted edits; GitHub Pages itself is openly readable.
- Source history is version-controlled. Last UI reorganization commit: 002bb6eb21b7a8fdb35ea7692a64f43a22759a60; newer commits may follow.

## Common gaps discovered
1. We initially looked at the Cloudflare ledger instead of the original GitHub Pages Mini Cooper app. Always search GitHub for elle_mini_tracker_1.html first.
2. The Cloudflare Access login was unsuitable for Elle. The correct no-login URL is the GitHub Pages link above.
3. Workdays Nov 3/4/5/10 and earlier balances must be reconciled before updating totals; avoid missing/double-counting Nov 4's 1.5 hours.
4. The milestone counts "80+" and "100+" must appear both in work notes and cash bonus records.
5. Cash bonuses are separate and not deposits; the effective hourly wage *does* include both cash and legacy item bonus earnings.
6. PACE must be wired to a working click handler, not just a visible label; check JS syntax after adding dynamically generated code.
7. When recent work collapses/ages out, move its presentation to legacy without changing the underlying hours, totals, or pace source.
8. Remove controls were unwanted; preserve audit history instead of making deletions easy.

## Maintenance path
Read this document and then read the current HTML. Change the smallest part needed. Preserve all existing entries, mobile presentation, legacy reconciliation, and the correct GitHub Pages link.