# Scot-LAND — project charter (updated 12 Oct 2026)

## Vision — LAURIE TO CONFIRM
A free, public, open land information system for Scotland, with Annual Ground Rent (the rental value of land alone) at its core, showing who holds land and what it is worth.

## Who it's for / why it matters
The public, researchers, journalists, policy people and community groups who want to understand Scottish land. It matters because it makes land value and ownership visible, and it's honest about the gaps (Sasine land, private owner names).

## Current state
The app starts, has automatic tests, land registry (RoS INSPIRE) and public land layers (PR #4), and the Wealth Engine v1 (PR #1) is merged with locked internal endpoints and database setup scripts. Existing databases need a one-time `alembic stamp head`. The live site www.scot-land.scot is set up and has been served from Laurie's own PC through Cloudflare, so it's only up while the PC is on.

## Definition of done for v1
The public map shows Annual Ground Rent and the Wealth Engine figures (surface, resource and ecological rent) alongside ownership, public land and vacant land layers. Every figure is clearly labelled as a research estimate, all checks pass, and it runs on the live site. *(Guess from docs/PLATFORM.md; Laurie to confirm.)*

## Roadmap
| Milestone | Outcome | Status |
|---|---|---|
| 1. Stable base | the app starts, tests run, no fake figures | Done (PR #3, PR #5) |
| 2. Land and ownership layers | land registry parcels and public land on the map, gaps labelled | Done (PR #4) |
| 3. Wealth Engine v1 | logins on internal endpoints, database setup scripts | Done (PR #1 merged) |
| 4. Proper hosting | stays on Laurie's PC via Cloudflare for now; revisit before public launch | Decided: PC for now (12 Oct) |
| 5. Vacant land, community layers and public launch | vacant/derelict land, Common Good, open downloads and public API on the live site | Not started |

## Next 3 steps
1. Keep hosting on Laurie's PC via Cloudflare for now (her decision, 12 Oct); bring the hosting options back before public launch.
2. Run `alembic stamp head` on any existing scot-land database (on her PC, so with her).
3. Close or refresh draft PR #2 (Cloud Agent notes), then plan the vacant land and Common Good layers.

## Decision rights
- **Grok Bot decides alone:** picking the next step from this roadmap, sending plans to the Cursor Project, rebases, merging pull requests that pass every check and are routine, tidy-ups, and a short note to Laurie afterwards.
- **Goes to Laurie:** the vision and scope, anything touching security, logins, money, customer or personal data, anything that must be tested on her PC, deleting things, publishing or posting publicly, and spending money.
- Extra for this project: choosing a host, paying for it, and changing DNS for www.scot-land.scot go to Laurie.

## Hosting (decided 12 Oct: stay on the PC via Cloudflare; revisit before public launch). Options for later (estimates, prices checked 12 Oct 2026, ex-VAT)
Today the site runs from Laurie's PC via Cloudflare (most likely a Cloudflare Tunnel), so it goes down whenever the PC sleeps and the PC is exposed. Keep Cloudflare for DNS in every option.
- **A. Cheapest, one box (recommended to start):** a Hetzner Cloud VPS running the Next.js frontend, FastAPI and Postgres+PostGIS in Docker. CX23 (2 vCPU, 4 GB) about €5.49/month or CX33 (4 vCPU, 8 GB RAM, more headroom for PostGIS) about €8.49/month, plus a small IPv4 and backup add-on. Roughly £6-12/month. Grok Bot/Cursor can write the setup; someone has to look after updates.
- **B. Managed, least upkeep:** Vercel for the frontend (Hobby is free but non-commercial only; Pro $20/month) plus Render for FastAPI ($7-25/month) and Render Postgres with PostGIS ($19-40/month). Roughly $26-85/month.
- **C. Keep the PC for now:** free, but only up when the PC is on. Fine until public launch, not after.

## Open questions for Laurie
1. Which comes first next: vacant land layers, or the Annual Ground Rent / tax scenario tools?
2. Is there a deadline or audience (for example an SLRG event) we're building towards?
