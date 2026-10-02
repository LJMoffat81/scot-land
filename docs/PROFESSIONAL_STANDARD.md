# Professional standard — Scot-LAND

This project is built as a **professional Annual Ground Rent assessment tool** for Scotland (education, advocacy, and research), not a throwaway prototype. We start as we mean to go on.

## Mission

Estimate **site-only annual ground rent** at place scale (What3Words 3×3 m cells and plot/parcel roll lines), using **SLRG-aligned** methods (Wightman residual, Pickard economic rent, Sandilands scenarios), with **defensible data provenance**.

## Non‑negotiables

1. **Legitimate data only**  
   Official open data, OGL-licensed products, or **written commercial/research licences**.  
   **No scraping** of Zoopla, Rightmove, ESPC, or similar portals.

2. **Scotland-first registers**  
   Transaction truth for Scotland is **Registers of Scotland** (and derived licensed extracts), not England & Wales Price Paid alone.

3. **Method transparency**  
   Every £ figure is traceable: inputs → residual/productive path → Pickard → yield → scenario.  
   Map residual and Sandilands national pool are **never conflated**.

4. **Valuer-shaped assessment**  
   Prefer residual (MV − DRC) and, when sales exist, sales-comparison / mass appraisal — not ad-hoc site-share shortcuts as the end state.

5. **Separation of concerns**  
   - **UI:** clarity for the public  
   - **Engine:** professional assessment pipeline  
   - **Data layer:** licensed/open stores with explicit provenance  
   - **Policy:** SLRG scenarios in config, versioned

6. **Research overrides ≠ production defaults**  
   Sensitivity sliders are labelled research. Signed-off defaults live in `data/config/agr.yaml`.

## Architecture (target)

```text
data/config/          Sources, licences, valuation parameters
data/fixtures/        Synthetic / test-only samples (never claim as ROS)
data/licensed/        Local licensed extracts (gitignored)
data/processed/       Built artefacts from ETL

backend/datasources/  Loaders + schemas (HPI, sales, rebuild)
backend/agr/          Assessment engine (residual, scenarios, overrides)
backend/etl/          Reproducible builds
backend/api/          HTTP surface
frontend/             Public education UI
```

## Valuation pipeline stages

| Stage | Status | Source of truth |
|-------|--------|-----------------|
| A — Place resolution | Live | W3W 3 m grid, postcode, parcels |
| B — Market evidence | Live (aggregate) | UK HPI council averages |
| B2 — Transaction sales | Scaffolded | ROS / licensed extract → `SalesStore` |
| C — Residual site capital | Live | MV − DRC (valuer residual) |
| C2 — Sales land model | Planned | OpenAVMKit pilot when sales loaded |
| D — Economic rent | Live | Pickard factors |
| E — Annualisation | Live | Yield (default 5%) |
| F — Policy scenarios | Live | Full AGR / income tax / CT+NDR |

## Quality bar before calling a number “roll-grade”

- [ ] Documented data licence for every input  
- [ ] Deterministic build from config + data version  
- [ ] Residual or sales method with stated confidence  
- [ ] Outlier / clamp policy documented  
- [ ] Ratio or spot-check vs known area (e.g. Ward 18)  
- [ ] Public UI clearly states research vs statutory  

## Related docs

- [DATA_LICENSING.md](DATA_LICENSING.md)  
- [DATA_ACQUISITION.md](DATA_ACQUISITION.md)  
- [methodology.md](methodology.md)  
- [valuation-roadmap.md](valuation-roadmap.md)  
