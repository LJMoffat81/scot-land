# Scot-LAND — Project Charter
Status: Approved 12 Oct 2026 (vision); success targets, out-of-scope list and target date still open, no deadline set · Owner: Laurie Moffat · PM bot: Project Manager · Repo: https://github.com/LJMoffat81/scot-land · Cursor Project: scot-land · Live site: www.scot-land.scot

## 1. Vision — Approved by Laurie 12 Oct 2026
Make the value of Scotland's land visible to everyone: a free, open map showing the Annual Ground Rent of every place in Scotland alongside who holds it, so land reform and land value tax debates rest on shared, honest evidence.

## 2. Problem & who it's for
For the public, researchers, journalists, policy people and community groups who want to understand Scottish land. It matters because it makes land value and ownership visible, and it's honest about the gaps (Sasine land, private owner names).

## 3. Objectives & success measures
Definition of done for v1: the public map shows Annual Ground Rent and the Wealth Engine figures (surface, resource and ecological rent) alongside ownership, public land and vacant land layers. Every figure is clearly labelled as a research estimate, all checks pass, and it runs on the live site. *(Guess from docs/PLATFORM.md — LAURIE TO CONFIRM.)*
- Measurable success targets (users, coverage %, launch date): **LAURIE TO CONFIRM**

## 4. Scope
- In scope: AGR estimates; Wealth Engine v1; RoS INSPIRE parcels; public land; vacant/derelict land; Common Good; open downloads and public API.
- Out of scope: **LAURIE TO CONFIRM** (e.g. private owner names beyond public records, England/Wales, official valuations).

## 5. Deliverables & milestones
| Milestone | Outcome | Status |
|---|---|---|
| 1. Stable base | the app starts, tests run, no fake figures | Done (PR #3, PR #5) |
| 2. Land and ownership layers | land registry parcels and public land on the map, gaps labelled | Done (PR #4) |
| 3. Wealth Engine v1 | logins on internal endpoints, database setup scripts | Done (PR #1 merged) |
| 4. Proper hosting | stays on Laurie's PC via Cloudflare for now; revisit before public launch | Decided: PC for now (12 Oct) |
| 5. Vacant land, community layers and public launch | vacant/derelict land, Common Good, open downloads and public API on the live site | Not started |

Target dates: **LAURIE TO CONFIRM** (any deadline or audience, e.g. an SLRG event?).

### Current state
The app starts, has automatic tests, land registry (RoS INSPIRE) and public land layers (PR #4), and the Wealth Engine v1 (PR #1) is merged with locked internal endpoints and database setup scripts. Existing databases need a one-time `alembic stamp head`. The live site www.scot-land.scot is served from Laurie's own PC through Cloudflare, so it's only up while the PC is on.

### Next 3 steps
1. Keep hosting on Laurie's PC via Cloudflare for now (his decision, 12 Oct); bring the hosting options back before public launch.
2. Run `alembic stamp head` on any existing scot-land database (on his PC, so with him).
3. Close or refresh draft PR #2 (Cloud Agent notes), then plan the vacant land and Common Good layers.

## 6. Constraints
- Budget: currently £0 hosting (PC + Cloudflare); any spend needs Laurie. Limit: **LAURIE TO CONFIRM**.
- Uptime: site only up while the PC is on; PC is exposed to the internet.
- Data: estimates must be labelled as research estimates; respect personal data rules on owner names.

### Hosting options for later (prices checked 12 Oct 2026, ex-VAT; keep Cloudflare DNS in all)
- **A. Cheapest, one box (recommended to start):** Hetzner Cloud VPS with Next.js, FastAPI and Postgres+PostGIS in Docker. CX23 (2 vCPU, 4 GB) ~€5.49/month or CX33 (4 vCPU, 8 GB) ~€8.49/month, plus IPv4 and backups. Roughly £6–12/month. Someone must look after updates.
- **B. Managed, least upkeep:** Vercel frontend (Hobby free but non-commercial; Pro $20/month) + Render FastAPI ($7–25/month) + Render Postgres with PostGIS ($19–40/month). Roughly $26–85/month.
- **C. Keep the PC for now:** free, only up when the PC is on. Fine until public launch, not after.

## 7. Assumptions & dependencies
- RoS INSPIRE and public land datasets stay openly available; Sasine-only land remains a labelled gap.
- Cloudflare (DNS/tunnel); Postgres+PostGIS; Alembic migrations.

## 8. Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Site down when PC off | High | Medium | Move to option A before launch |
| PC exposed via tunnel | Medium | High | Move hosting before launch; keep tunnel locked down |
| Estimates mistaken for official values | Medium | High | Label every figure as research estimate |
| Personal data in ownership layers | Low | High | Public records only; Laurie approves any change |

## 9. Team & roles
| Role | Who | Responsibility |
|---|---|---|
| Sponsor/approver | Laurie | Approves charter and every gate |
| Project manager | Project Manager | Runs lifecycle, tracks gates, status |
| Planner/router | Grok Bot | Plans, PRDs |
| Outer loop | Repo Outer Loop | Cursor prompts, merges safe green PRs |
| Builder | Cursor Project `scot-land` | All code via PRs |
| Reviewers | Scot-LAND specialist bots (**which ones — LAURIE TO CONFIRM**) | Code/data review |

### Decision rights
- **Grok Bot decides alone:** picking the next step from this roadmap, sending plans to the Cursor Project, rebases, merging pull requests that pass every check and are routine, tidy-ups, and a short note to Laurie afterwards.
- **Goes to Laurie:** vision and scope, anything touching security, logins, money, customer or personal data, anything that must be tested on his PC, deleting things, publishing or posting publicly, and spending money.
- Extra for this project: choosing a host, paying for it, and changing DNS for www.scot-land.scot.

## 10. Ways of working
Two-tool rule: Grok Bot plans, Cursor codes (see AGENTS.md; the rule `.cursor/rules/two-tool.mdc` should be committed in the repo). Pull latest `main` first; never discard others' uncommitted work. Done = checks green, reviewed, merged.

## Open questions for Laurie
1. Which comes first next: vacant land layers, or the Annual Ground Rent / tax scenario tools?
2. Is there a deadline or audience (for example an SLRG event) we're building towards?

## 11. Sign-off
Vision approved by Laurie on 12 Oct 2026. Full charter still open on success targets, out-of-scope list and target date (no deadline set).

## Change log
- 12 Oct 2026: original charter.
- 12 Oct 2026: restructured to standard template; draft Vision; fixed pronouns (he/him); added scope, constraints, risks and roles.
- 12 Oct 2026: Laurie approved the vision; PM bot set to Project Manager; success targets, out-of-scope list and target date still open (no deadline set).
