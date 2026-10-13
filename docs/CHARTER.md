# Scot-LAND — Project Charter
Status: Vision approved 12 Oct 2026; scope, data and workflow updated 13 Oct 2026. Success targets, out-of-scope list and target date still open, no deadline set · Owner: Laurie Moffat · Project lead: Grok Bot (PM bot retired 12 Oct) · Repo: https://github.com/LJMoffat81/scot-land · Cursor Project: scot-land · Live site: www.scot-land.scot

## 1. Vision (approved by Laurie 12 Oct 2026)
Make the value of Scotland's land and natural resources visible to everyone. A free, open map shows the Annual Ground Rent of every place in Scotland and who holds it, so land reform and land value tax debates rest on shared, honest evidence.

## 2. Who it's for
The public, researchers, journalists, policy people and community groups who want to understand Scottish land. It is honest about the gaps, such as Sasine land and private owner names.

## 3. Scope: full Georgist natural-capital rent (updated 13 Oct)
- **Surface land rent:** AGR for every Data Zone, with RoS INSPIRE parcels, Data Zone boundaries, public land, vacant/derelict land, Housing Land Audit, Common Good and community ownership.
- **Resource rents:** offshore wind seabed (Crown Estate Scotland), onshore wind, aquaculture, hydro, water abstraction, minerals (BritPits quarry index only), forestry, peat and soil carbon, fisheries, oil and gas (Scottish-waters share), foreshore and moorings, and cables.
- **Eco module (later):** biodiversity and ecosystem services, as shadow rent.
- **Rules:** one rent per hectare per use. Surface, resource and eco rents stay separate. Overlays (designations, crofting, flood) change the best permitted use and never add value. Every figure is tagged **market** (observed rents), **proxy** (modelled) or **shadow** (no market price).
- Out of scope at launch *(Decided by Laurie, 13 Oct)*: paid data and what3words (future add-ons only); republishing paid data in any form; map layers without a clear open licence; using the "what3words" name or brand for the Scot-LAND grid (called "Scot-LAND squares").
- Further out of scope: **LAURIE TO CONFIRM** (e.g. private owner names beyond public records, England/Wales, official valuations).

## 4. Data licence rule (13 Oct)
- OGL-3.0 is preferred. Other free open licences are fine (e.g. James Hutton Institute Open Data Licence for Land Capability for Agriculture).
- Non-commercial licences (Carbon & Peatland 2016 map, NSTA oil and gas) are allowed because Scot-LAND is non-commercial. They are tagged `licence=non-commercial` and come out if that ever changes.
- **At launch only open sources are used** (government sources first). **Paid data and what3words are off at launch** — future add-ons only *(Decided by Laurie, 13 Oct)*. They may be built behind switched-off flags, but launch uses open data only. Paid data is never republished. Examples of paid sources that stay off unless Laurie decides otherwise: BGS mineral data, Who Owns Scotland.
- Layers without a clear licence stay off the public map.
- Every layer carries a `licence_url`. All data is loaded into PostGIS so the Georgist and Valuation bots can use it.

## 5. Front end
One full-screen map with a single search box, place cards and a layers panel. The grid is called **"Scot-LAND squares"**. what3words lookup is a future add-on and is switched off at launch *(Decided by Laurie, 13 Oct)*.

## 6. Milestones
| Milestone | Status |
|---|---|
| 1. Stable base; 2. land and ownership layers; 3. Wealth Engine v1 | Done (PRs #1–#5) |
| 4. Hosting | Laurie's PC via Cloudflare for now; revisit before public launch |
| 5. OGL layer build-out (DZ boundaries, parcels, place card, licences) | In progress; DZ boundaries live 13 Oct |
| 6. Natural-capital resource layers (P1 wind, aquaculture, hydro; then P2/P3) | Queued |
| 7. Publish AGR £ figures and public launch | Blocked on Laurie's ECONOMIC_RULES approval |

## 7. Workflow
- Cursor Project builds in small parallel PRs. Trunk-based: PRs are squash-merged to `main` when green and branches are deleted.
- Grok Bot merges routine green PRs. A post-deploy smoke test (site loads, every layer returns data) is mandatory after each redeploy.
- Hosted on Laurie's PC (Docker Compose + Cloudflare) for now. Two-tool rule: Grok Bot plans, Cursor codes.

## 8. Quality gates
- AGR £ figures are internal only (Data Zone-level band with proxy tag) until Laurie approves `docs/ECONOMIC_RULES.md`. Held valuation PRs: **#6, #9, #10, #16, #17 and #19**.
- The Valuation and Georgist bots check figures; the GIS bot checks every source and licence; CI must pass before merge.

## 9. Decision rights
- **Grok Bot alone:** next steps from this charter, plans for Cursor, rebases, routine green merges, tidy-ups, then a note to Laurie.
- **Laurie:** vision and scope, security/logins, money, personal data, PC testing, deletes, publishing, hosting/DNS.

## 10. Risks
Site down when the PC is off; PC exposed via tunnel (move host before launch). Estimates mistaken for official values (label every figure). Licence drift (GIS bot checks; `licence_url` on every layer). Personal data in ownership layers (public records only).

## 11. Open decisions for Laurie
1. Carbon price (£/tonne) for the peat and soil carbon rent.
2. Pickard factors.
3. Remediation assumptions.
4. Approval of ECONOMIC_RULES, which unblocks #6, #9, #10, #16, #17, #19 and publication.
5. Success targets, out-of-scope list and any deadline.

## Change log
- 12 Oct 2026: original charter; restructured; vision approved.
- 13 Oct 2026: scope widened to full natural-capital rent; data licence rule; w3w-style front end and "Scot-LAND squares"; trunk-based workflow and smoke test; quality gates; PM bot retired; open decisions updated.
- 13 Oct 2026: paid data and what3words off at launch (future add-ons); six held valuation PRs listed (#6, #9, #10, #16, #17, #19); front end no longer described as what3words-style at launch.
