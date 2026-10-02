# Scotland Open Land — Methodology

## What is AGR?

Annual Ground Rent (AGR) is a charge on the **site rental value** of land — the rent for the land alone, excluding buildings and improvements. SLRG uses the term AGR rather than "land value tax" to emphasise that it recovers **economic rent** the community creates, not a tax on labour or trade.

## Intellectual lineage

Calculation **maths** still run on the operational trio **Wightman → Pickard → Sandilands scenarios**. The wider lineage explains *what* is being measured and *why* it is a legitimate public claim.

### Core layers

| # | Thinker | Role in this tool |
|---|---------|-------------------|
| 1 | **Adam Smith** | Classical **ground-rent**: distinct revenue from location; can specially bear tax without taxing labour or buildings (*Wealth of Nations*). |
| 2 | **David Ricardo** | **Differential rent**: better location yields surplus that accrues as rent — why this square’s AGR exceeds another’s. |
| 3 | **William Ogilvie** | Scottish **equal natural right** in land (1781/82); improvements private; community claim on land rent. |
| 4 | **Henry George** | Full recovery of site rent as primary public revenue (single-tax tradition). |
| 5 | **Mason Gaffney** | **ATCOR / EBCOR** — taxes and excess burdens ultimately load onto land rent at productive locations. |
| 6 | **Fred Harrison** | Land **boom–bust** cycles; market prices capitalise speculation above economic rent. |
| 7 | **Joseph Stiglitz** | **Henry George theorem**: public goods and amenity capitalise into land values. |
| 8 | **Laurie Macfarlane** | Modern **housing = land market**; hope value, financialisation, Scotland/UK policy context. |
| 9 | **Martin Adams (Unitism)** | **Community land contribution**: collect land rental value; untax work/buildings; fund services or a **citizen dividend**. |
| 10 | **Roger Sandilands** | Scotland **macro**: true rent ~50% of GDP; income-tax replacement and growth arguments. |
| 11 | **Andy Wightman** | **Residual / HABU** site capital for Scottish locations. |
| 12 | **Duncan Pickard** | **De-speculation**: charge productive/economic rent, not bubble market price. |

### Satellite references (also see)

| Thinker / body | Role |
|----------------|------|
| **John Stuart Mill** | Unearned increment — social claim on rises in land value from general progress. |
| **Thomas Paine** | *Agrarian Justice* — land rent as basis for an equal citizen dividend. |
| **School of Cooperative Individualism** | Free online library of Georgist / single-tax primary sources (George, periodicals, land question) — [cooperative-individualism.org](https://cooperative-individualism.org/index.htm). |
| **Lars Doucet / Center for Land Economics** | Modern LVT evidence (*Land is a Big Deal*); city incidence studies; assessment equity. |
| **OpenAVMKit** (CLE) | FOSS mass appraisal / land modeling — planned path to a finer Scotland roll. |
| **John McEwen** | *Who Owns Scotland* — ownership concentration and who captures rent. |
| **Churchill (1909 land campaign)** | Historic UK political case against land monopoly. |
| **Scottish Land Commission** | Hope value, public interest, contemporary LVT policy options. |

**Attribution note:** ATCOR/EBCOR are formalised by **Gaffney**. **Sandilands** applies the rent-shift and Scotland GDP case. Market price correction is **Harrison** (cycle/speculation story) + **Pickard** (operational discount). **Adams** supplies citizen-dividend / Unitism framing; **Doucet/CLE** supply modern mass-appraisal tooling direction (see [valuation roadmap](valuation-roadmap.md)).

### External links

- [Unitism (Martin Adams)](https://unitism.com/)
- [School of Cooperative Individualism](https://cooperative-individualism.org/index.htm) — Georgist source library (Edward J. Dodson)
- [Center for Land Economics](https://landeconomics.org/home)
- [OpenAVMKit](https://www.openavmkit.com/)

## Valuer-style AGR roll (primary calculation)

The map now computes charges as an **open-data approximation of a valuer residual roll** (Wightman residual + Pickard economic base), not as a simple price × site-share shortcut.

### Step-by-step (urban / existing residential HABU)

```
1. HABU = existing authorised residential use (hope value excluded from basis)
2. MV   = council HPI average dwelling price (existing-use sales evidence)
3. Rebuild_new = floor_m² × blended rebuild £/m² × regional factor
4. DRC  = Rebuild_new × average stock remaining factor (default 55%)
5. Site_capital_market = clamp(MV − DRC) within min/max land-share bounds
6. Site_capital_economic = Site_capital_market × Pickard urban factor (default 70%)
7. Annual_rent_economic = Site_capital_economic × yield (default 5%)
8. Grid charge = Annual_rent_economic_per_m² × 9 m² × scenario
```

Also reported: **notional plot** roll line (default 280 m²) and **parcel** roll line when ROS INSPIRE area is available.

### Rural / agriculture HABU

```
Category £/ha (2009 land-use table) × HPI factor
  × Pickard farmland productive factor (0.20 — market ~5× productive)
  × yield 5% → annual rent / m²
```

### 1. Roger Sandilands (macro scenarios)

- True rent **~50% of GDP** with ATCOR; official “rent on land” (~£417m) is not the pool.
- Income-tax replacement and growth narratives use the **national pool**, not the sum of roll cells.

### 2. Andy Wightman (residual)

- Residual = **market value − DRC of improvements** (rebuild / insurance family of methods).
- HABU = authorised / existing use for most sites; hope value out of the levy base.

### 3. Duncan Pickard (economic rent)

| Land type | Distortion | Correction on residual capital |
|-----------|------------|--------------------------------|
| Farmland | Market ~5× productive | × 0.20 |
| Urban | Tax design, credit, bubble premia | × 0.70 (config; SLRG-tuned) |

Marginal land: near-zero rent after wages and capital (Ricardo).

## Fiscal tool (tax replacement for decision-makers)

The map can be used as a **fiscal incidence instrument**:

1. **Taxes to replace** — configurable basket (income tax + Council Tax + NDR research totals in `agr.yaml` `fiscal.basket`).
2. **AGR collection** — under each scenario, how much of the Sandilands **national rent pool** is collected.
3. **Surplus** — collection − basket (**revenue neutral or better** when ≥ 0). Full economic rent typically shows a large surplus.
4. **Who pays** — highest land-rent places have the highest **gross** liability (map residual plot AGR).
5. **Net position** — gross − **equal dividend** (pool ÷ population) − optional **remote/island credit**. Low-rent and remote councils can be **net receivers** (negative net tax), encouraging people to thrive outside the hot core.

Scenarios include **Replace all listed taxes (neutral)** (`replace_full_basket`), full rent with surplus, income tax only, and CT+NDR.

This is **research**, not a live bill. National totals use the macro pool; place figures use the residual roll and are not calibrated to sum to the pool.

## Two rent concepts (read this)

| Concept | Source | Used for |
|---------|--------|----------|
| **Map residual AGR roll** | Valuer residual (MV − DRC) → Pickard → 5% yield | Per-cell / plot / parcel roll lines and scenario base |
| **National rent pool** | Sandilands macro (~£90bn / ~50% of GDP) | Equal-share illustration; income-tax **scale factor** only |

**They are not the same number.** Summing all map squares is **not** calibrated to equal the Sandilands pool. Income-tax scenario multiplies map economic rent by `(£11.5bn ÷ £90bn)`. Equal-share divides the **national pool** by population, then compares this square’s **map** rent to that claim.

## Integrity and limitations

1. **Research estimate** — not VOA, ROS, or a rates bill.
2. **Residual is a proxy** — urban path is largely `HPI average × site share ÷ dwelling m²`, not full `price − DRC` on every plot.
3. **Site share** — the parcel rent is the residual, not a fixed share. The Group’s homepage illustration of a 60% site share, and the claim that prices fall by half, are not the display engine (`use_slrg_for_display` is false). The Wightman research share of 49% remains in config.
4. **Spatial coarseness** — capital/m² is **council-level** (flat within council) except rural land-use fallbacks; Ricardo differential is national-to-local, not street-level.
5. **HABU aspirational** — HPI embeds credit conditions and some hope value; Pickard discounts are **static** policy knobs (Harrison cycle not modelled year-by-year).
6. **Residential-heavy** — non-domestic urban land is thin; NDR in the revenue-neutral *label* does not mean full commercial cadastral coverage.
7. **Lineage is pedagogical** — Smith through Macfarlane explain *why*; they do not each supply a separate square formula.

Caveats also live in `data/config/agr.yaml` under `integrity.caveats` and are returned on every AGR API response.

## Equal-share illustration (Ogilvie / Paine / Unitism)

For pedagogy only (does not change the charge formula):

```
equal_share_rent_per_person = estimated_scotland_annual_rent ÷ scotland_population
square_as_fraction_of_equal_claim = map_economic_rent_of_square ÷ equal_share_rent_per_person
```

This frames each cell relative to one Scot’s equal annual claim on the **national** rent pool (Ogilvie’s right; Paine’s *Agrarian Justice*; Adams / Unitism citizen dividend or community fund). Population and rent pool live in `data/config/agr.yaml`.

## Per-square formula (W3W 3×3 m)

```
1. Snap lat/lng to 3m W3W grid cell (9 m²)
2. Run valuer residual / productive assessment at council HABU
3. Economic rent £/m² × 9 × scenario capture
4. Also emit notional-plot and parcel roll lines
5. Equal-share stats from national rent pool [Ogilvie/Paine framing]
```

## Policy scenarios

| Scenario | Idea | Rent base used |
|----------|------|----------------|
| Full AGR | 100% of **map** economic site rent | Map residual only |
| Replace income tax | Scale map rent by £11.5bn ÷ **national pool** | Map × macro ratio |
| Revenue-neutral CT+NDR | Fixed % of **map** de-speculated capital | Map residual capital |

Lineage gloss: full AGR (Smith–George); income tax (Sandilands + Gaffney ATCOR); revenue-neutral (Wightman).

## Data sources (Phase 1+)

| Dataset | Source | Use |
|---------|--------|-----|
| Property transactions | ROS open data | Residual valuation |
| HPI by area | ROS / UK HPI | Zone base rates |
| Planning zones | Spatial Hub / LDP | HABU |
| Cadastral parcels | ROS INSPIRE | Parcel area |
| Postcodes | ONSPD / postcodes.io | Search |

## References

### Classical and Georgist

- Adam Smith — *An Inquiry into the Nature and Causes of the Wealth of Nations* (1776), esp. rent and taxes on ground-rents
- David Ricardo — *On the Principles of Political Economy and Taxation* (1817), law of rent
- William Ogilvie — *An Essay on the Right of Property in Land* (1781/82)
- Henry George — *Progress and Poverty* (1879)
- Mason Gaffney — ATCOR / EBCOR; *The Corruption of Economics* (with Fred Harrison)
- Fred Harrison — *The Power in the Land*; *Boom Bust*; *Ricardo’s Law*
- Joseph Stiglitz — Henry George theorem / capitalisation of public goods into land values
- John Stuart Mill — unearned increment (land value and progress)
- Thomas Paine — *Agrarian Justice* (1797)

### Scotland and contemporary

- [Sandilands — The Hidden Potential of Rents](https://slrg.scot/blog/wp-content/uploads/2020/05/THE-HIDDEN-POTENTIAL-OF-RENTS-Scotland-2015b.docx)
- [Sandilands — Rent is half of GDP](https://slrg.scot/blog/rent-is-half-of-gdp/)
- [Pickard — Calculating AGR charges](https://slrg.scot/blog/calculating-agrlvt-charges-when-council-tax-and-income-tax-are-replaced/)
- [Wightman — A Land Value Tax for Scotland](https://andywightman.scot/docs/LVTREPORT.pdf)
- Josh Ryan-Collins, Toby Lloyd & Laurie Macfarlane — *Rethinking the Economics of Land and Housing* (2017)
- Laurie Macfarlane — [Scottish Land Commission housing land market paper](https://www.landcommission.gov.scot/downloads/5de1a716b632b_Land-Lines-Discussion-Paper-Housing-Land-Market-Dec-2017.pdf)
- Martin Adams — *Land: A New Paradigm for a Thriving World* · [Unitism](https://unitism.com/)
- [School of Cooperative Individualism](https://cooperative-individualism.org/index.htm) — archive of Henry George, single-tax periodicals, and land-value literature
- Lars Doucet — *Land is a Big Deal* · [Center for Land Economics](https://landeconomics.org/home) · [OpenAVMKit](https://www.openavmkit.com/)
- [Scottish Land Commission — LVT policy options](https://www.landcommission.gov.scot/downloads/5dd6984da0491_Land-Value-Tax-Policy-Options-for-Scotland-Final-Report-23-7-18.pdf)
- John McEwen — *Who Owns Scotland*

## Disclaimer

Research estimate with SLRG economist sign-off on **charge parameters** (macro, site share, despeculation, scenarios). Intellectual lineage and integrity caveats are pedagogical and do not by themselves alter residual maths. Not an official tax assessment or rates bill.
