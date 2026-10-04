> **Working design** (Scot-LAND, 4 Oct 2026). Copied unchanged from the team's working file `model-equation-2026-10-04.md`.
> Where it mentions sign-off, pinned Glasgow and Wick figures or frozen files, those were the rules when it was written; they were lifted on 4 Oct 2026 while the engine is developed.

# Scot-LAND model equation (white paper §3a)
*Policy & Economics, 4 Oct 2026, about 13:05 BST. **PROPOSAL, unsigned.** No code change, nothing posted. Live figures are untouched: Glasgow G1 1BL £8,000.67 and Wick KW1 4AA £8.28 stay as they are. Once Laurie signs this, it becomes the source of truth: QA's independent calculator must match the API to the penny, and Engine confirms Part 1 line by line.*

**Sources.**
- Live code: `LJMoffat81/scot-land` main @ `98c73ce`. Read from the box's read-only copy at `/workspace/scot-land/repo`, which I checked is clean and matches `origin/main` (`git ls-remote`). Nothing was pushed.
- Engine's `live-equation-as-coded-2026-10-04.md`, as corrected.
- QA's `/workspace/qa/reference-calc/`.
- Policy, Data and farmland files: the method spec ("M"), the principles file ("P-xx"), the farmland options paper ("FOP") and Data's inputs v2 ("v2").

**Labels.**
- **SIGNED**: in the live config, signed by SLRG on 8 Jun 2026 (`agr.yaml:261-266`). That sign-off covers `agr.yaml` only.
- **LIVE**: used by the live site but outside that sign-off (`sources.yaml`, `councils.json`, code constants).
- **UNSIGNED PROPOSAL**, **UNKNOWN**, **ASSUMPTION**, **STAND-IN**: as used in the other team files.
- No figure is invented. Every number is quoted from code, config or a workspace file.

## 0. Final symbol set (stable names; Data builds the inputs table from these)

**Part 1 (live):**
- Indexes: \(i\) is a parcel, \(c\) is a council.
- Parcel area: \(A_i\).
- Rural switch: \(Z_c\), the rural indicator, with \(\mathcal{R}\) the five listed codes and \(\bar P_{rur}\) the price threshold.
- Urban residual inputs:
  - \(P_c\) council average price;
  - \(F\) floor area;
  - \(R_h, R_f\) house and flat rebuild cost per m², \(w_h, w_f\) their weights, \(\bar R\) the blend;
  - \(k_c\) regional factor; \(d\) remaining-value factor;
  - \(B_c\) rebuild cost new, \(D_c\) depreciated rebuild cost;
  - \(\sigma_{lo}, \sigma_{hi}\) clamp bounds, \(S_c\) site capital, \(s_c\) implied share;
  - \(L\) notional plot.
- Factors: \(\pi_u\) urban factor, \(\pi_f\) farmland factor, \(y\) yield.
- Rural inputs: \(V_{09}\) 2009 farmland value, \(H\) HPI, \(H_0\) HPI base, \(\lambda\) fallback.
- Rent and charges:
  - \(e_c\) unrounded rent per m²;
  - \(\tau_{cap}\) capture rate (Engine's \(\kappa\)), \(\tau_{sc}\) scenario rate (Engine's \(\phi\)), \(\tau=\tau_{cap}\tau_{sc}\);
  - \(G\) grid square area, \(N\) m² per ha;
  - \(\mathrm{AGR}^{par}_i\) parcel charge, \(\mathrm{AGR}^{plot}_c\) plot charge, \(\mathrm{AGR}^{sq}\) square charge.

**Part 2 (target):**
- Date and layers: \(t_0\) valuation date; \(k\) land layer and \(\Omega_k\) its total area; \(\mathcal{U}_k\) unit register, with \(\mathcal{U}^{LR}\) Land Register units and \(\mathcal{U}^{S}\) Sasine units.
- Urban/rural: \(U_i\) per-point urban indicator.
- Location and use: \(x_i\) location, \(u_i\) use, \(b\) basis.
- Urban value:
  - \(v_b(x,u)\) land capital value per m²;
  - \(y^{*}\) market capitalisation rate;
  - \(r_{b,i}\) site rent per m²;
  - \(g(\cdot)\) plot-size curve, \(A^{ref}\) reference plot, \(\mu_i\) assembly factor.
- Rural value:
  - \(q\) LCA class, \(A_{iq}\) area of class \(q\) in unit \(i\);
  - \(\rho_q\) class rent, \(\theta_1, \theta_2\) curve parameters, \(n_q\) class rank;
  - \(a^{L}_q, a^{N}_q\) measured class areas inside and outside the LFA;
  - \(\bar\rho^{L}, \bar\rho^{N}\) the LFA and non-LFA mean rents;
  - \(I(\cdot)\) rent index, \(\beta\) buildings deduction.
- Outputs: \(\mathrm{SRV}^{raw}_i\), \(\mathrm{SRV}_i\), \(h_i\) hope difference.
- Policy: \(\delta_i\) relief, \(\phi_t\) phasing, \(\tau\), \(\mathrm{AGR}_i\).
- Totals: \(T\) published total, \(T^{raw}\) raw total.
- Validation: \(j\) held-out sale, \(P_j\) price, \(\hat P_j\) prediction, \(R_j\) ratio, COD, PRD.
- Uncertainty: \(\varepsilon_X\) log error of symbol \(X\).

*Name clash avoided on purpose:* \(c\) is always a council and \(q\) is always a capability class. Engine's \(\kappa, \phi\) for the two rates are written \(\tau_{cap}, \tau_{sc}\) here, and \(\phi_t\) is kept for phasing.

---
## Part 1. The live model as it is (main @ `98c73ce`)

**Proof that it matches the site.** QA's independent calculator (`/workspace/qa/reference-calc/live_equation.py`, inputs `inputs-98c73ce.json`, results `compare-98c73ce.csv`) reproduces the live API on **60 of 60 checks across 10 postcodes, to the penny**. It uses the rounding written below. Engine's corrected `live-equation-as-coded-2026-10-04.md` agrees with this Part 1. Where the two differed earlier, the differences are noted in §1.8.

### 1.1 Branch: urban or rural, by council
$$
Z_c=\mathbb{1}\!\left[\,c\in\mathcal{R}\ \lor\ P_c<\bar P_{rur}\,\right],\qquad \mathcal{R}=\{\text{S12000013, S12000017, S12000023, S12000027, S12000035}\},\quad \bar P_{rur}=\pounds145{,}000 .
$$
- **Where it is set:** `backend/etl/build_processed.py:90-96`, using `data/config/sources.yaml:28-34`, and stored as `rural` in `data/processed/councils.json`. It is read at `backend/agr/areas.py:64`, and the branch is taken at `backend/agr/valuation.py:299-301`. If \(Z_c=1\) the rural path runs, otherwise the urban path.
- **Councils on the rural rate at this commit: 11.** The five listed are Na h-Eileanan Siar, Highland, Orkney, Shetland, and Argyll and Bute. Six more are caught by the price rule: Aberdeen City (£133,906), Dundee City (£134,392), East Ayrshire (£128,845), Inverclyde (£112,529), North Ayrshire (£130,233) and West Dunbartonshire (£127,161). These prices are from `councils.json`. As a result, AB10 1AQ (Aberdeen city centre) is valued as farmland at **£69.50** for its parcel (QA `compare-98c73ce.csv`).
- **KNOWN DEFECT, unintended under the method.** Cheap housing is not rural land. The rule also creates a cliff at £145,000: a council £1 either side of the threshold switches between a town residual and the farmland rate. This is BACKLOG P0-1 and D0-1. The target replaces \(Z_c\) with a per-point urban/rural test, \(U_i\), using the SG Urban Rural Classification 2022 (v2 labels it `stand-in:sg-ur2022` under S9, and S11 uses it for pooling) (§2.2).

### 1.2 Urban path (\(Z_c=0\)): `_urban_residual_drc`, `valuation.py:102-212`
$$
\bar R=\frac{w_hR_h+w_fR_f}{w_h+w_f},\qquad B_c=F\,\bar R\,k_c,\qquad D_c=d\,B_c
$$
$$
s_c=\frac{P_c-D_c}{P_c},\qquad
S_c=\begin{cases}\sigma_{lo}P_c & s_c<\sigma_{lo}\\ \sigma_{hi}P_c & s_c>\sigma_{hi}\\ \max(0,\,P_c-D_c) & \text{otherwise}\end{cases}\quad(P_c>0);\qquad S_c=0\ \ (P_c\le 0)
$$
$$
e_c=\frac{S_c}{L}\,\pi_u\,y\qquad[\pounds/\text{m}^2/\text{yr, unrounded}]
$$
- \(\bar R\): lines 89-99 (if \(w_h+w_f\le0\), \(\bar R=R_h\)). \(k_c\): lines 83-86 (default 1.0). \(B_c, D_c\): lines 126-127. Clamp: lines 129-146. \(e_c\): lines 149, 151-152, 156.
- **The clamp is not binding for any urban council at this commit.** Implied shares run from 0.371 (North Lanarkshire) to 0.670 (East Renfrewshire), recomputed from `councils.json` with the constants below. So the \(\sigma\) branches are **UNTESTED** by QA's 60 checks.

### 1.3 Rural path (\(Z_c=1\)): `_rural_productive`, `valuation.py:215-288`
$$
e_c=\frac{V_{09}\,(H/H_0)\,\pi_f\,y}{N}\qquad[\pounds/\text{m}^2/\text{yr, unrounded}],\qquad N=10{,}000
$$
- Lines 233, 238-241 and 244.
- \(H_0=100\) is **hard-coded** (`valuation.py:27`), not config.
- If `councils.json` or its index is missing, \(H/H_0\) is replaced by the **hard-coded fallback \(\lambda=2.5\)** (lines 73-74 and 78-79).
- **Defects:**
  - \(H\) is a *house* price index applied to farmland.
  - \(H\) is based at Jan 2023 = 100, while \(V_{09}\) is a Jan 2009 value, so \(H/H_0\) is not a 2009-to-2026 uplift. This is BACKLOG P0-2 (`farmland-check` §1).

### 1.4 Published figures and rounding
\(\operatorname{rd}_n\) is Python's `round(x, n)` on a float64 (round half to even on the binary value).
$$
\mathrm{AGR}^{par}_i=\operatorname{rd}_2\!\left(e_c\,A_i\right)\quad(A_i>0),\qquad
\mathrm{AGR}^{plot}_c=\operatorname{rd}_2\!\left(e_c\,L^{*}\right),\ \ L^{*}=\begin{cases}L=280 & Z_c=0\\ N=10{,}000 & Z_c=1\end{cases}
$$
$$
\mathrm{AGR}^{sq}=\operatorname{rd}_2\!\Big(\tau_{sc}\cdot\big[\operatorname{rd}_m(e_c)\cdot G\cdot\tau_{cap}\big]\Big),\quad m=\begin{cases}4 & Z_c=0\\ 6 & Z_c=1\end{cases},\quad G=9
$$
- **Parcel figure:** `valuation.py:178-180` (urban) and `:257-259` (rural). **Plot figure:** `:208` and `:284`.
- **Square figure:** the rounded per-m² rent `:201` / `:277` → `engine.py:106` → `scenarios.py:30`, then \(\tau_{sc}\) at `scenarios.py:50`, rounded at `:73`.
- **The rounding before multiplying by area applies only to the 9 m² square.** The parcel and plot figures use the unrounded \(e_c\) and round only the final pound.
- **\(A_i\)** comes from the RoS INSPIRE polygon returned by a live WMS GetFeatureInfo (`spatial/parcels.py:86-95,120-121`). Its planar area is computed in EPSG:27700 and rounded to 2 dp (`parcels.py:62-66`). It is a runtime spatial input, not code or config.

### 1.5 The charge rate τ: where it sits
$$
\tau=\tau_{cap}\,\tau_{sc},\qquad \tau_{cap}=\texttt{per\_square.agr\_capture\_rate}=1.0\ (\texttt{agr.yaml:217}),\quad \tau_{sc}=\texttt{scenarios.full\_agr.capture\_rate}=1.0\ (\texttt{agr.yaml:232})
$$
- \(\tau\) is **not** inside the valuation. `valuation.py` stops at \(e_c\), and \(\tau\) is applied afterwards in `engine.py:105` and `scenarios.py:30,50`.
- **The public parcel and plot figures are computed in `valuation.py` before either rate is applied, so τ never reaches them. Only the 9 m² square uses τ.** Today this makes no difference, because both rates are 1.0. Job 002's split of the valuation and policy layers puts τ on every figure.
- **What is not separated is the config.** Both layers read `agr.yaml`. The Pickard factors \(\pi_u, \pi_f\), which are policy-style de-speculation choices, sit *inside the valuation step, before the yield* (`valuation.py:151-156`, `:228-244`).
- **The live route is \(r=y\cdot v\),** a land value times an **unsourced 5% yield** (v2 S13, `stand-in:yield-5pct-unsourced`).
- **Fiscal panel (not the public figure):** `api/main.py:157-164` and `agr/report.py:48-53` scale the parcel figure by \(\operatorname{rd}_2(\text{active square})/\operatorname{rd}_2(\text{full square})\).
  - Under `full_agr` the scale is exactly 1.
  - Under other scenarios, the 2 dp rounding of tiny rural squares distorts it. My arithmetic from the code for Wick under `replace_income_tax`: \(0.01/0.04=0.25\) instead of the unrounded ratio of about 0.128. This is **derived from the code, not tested against the API.** It belongs on Engine's list.

### 1.6 Overrides on the public route (documented; not used by live figures)
- `/postcode` accepts `yield_rate`, `urban_speculation` and `farmland_factor` (`api/main.py:586-588`, parsed by `_parse_sensitivity` at `:82-93`, called at `:615`).
- They are validated and merged in `agr/overrides.py:9-43`, with allowed ranges \(y\in[0.02,0.12]\), \(\pi_u\in[0.3,1.0]\) and \(\pi_f\in[0.1,1.0]\).
- No live or snapshot figure uses them (QA: `sensitivity_overrides: {}`).

### 1.7 Constants and inputs, with dates and vintages

| Symbol | Value | Where (read at) | Date / vintage | Status |
|---|---|---|---|---|
| \(F\) | 85 m² | `agr.yaml:165` (`valuation.py:113`) | undated | SIGNED; source unknown (committed HEAD = 85; 97 is an uncommitted scratch value, v2) |
| \(L\) | 280 m² | `agr.yaml:167` (`:114`) | undated | SIGNED; unsourced (BACKLOG P1-6) |
| \(y\) | 0.05 | `agr.yaml:168` (`:115`, `:227`) | undated | SIGNED; **unsourced** (S13) |
| \(w_h,w_f\) | 0.75, 0.25 | `agr.yaml:170-171` (`:94-95`) | undated | SIGNED; source unknown |
| \(R_h,R_f\) | £1,950, £2,300/m² | `agr.yaml:174-175` (`:92-93`) | undated, "BCIS/ABI-style" | SIGNED; open-data approximation (`agr.yaml:266`) |
| \(k_c\) | Glasgow S12000049 = 1.05; default 1.0 | `agr.yaml:176-184` (`:83-86`) | undated | SIGNED; all unverified (`physical-inputs` file) |
| \(d\) | 0.55 | `agr.yaml:187` (`:116-118`) | undated | SIGNED; **unsourced** (v2 S3) |
| \(\sigma_{lo},\sigma_{hi}\) | 0.15, 0.85 | `agr.yaml:189-190` (`:119-120`) | undated | SIGNED; not binding at this commit |
| \(\pi_u\) | 0.70 | `agr.yaml:212` (`:151`) | undated | SIGNED; "not a published table" |
| \(\pi_f\) | 0.20 | `agr.yaml:210` (`:228`) | Pickard blog, 23 Aug 2018 | SIGNED; advocacy example (`farmland-check` §5) |
| \(V_{09}\) | £4,094/ha | `agr.yaml:225` (`:238`) | VOA Jan 2009 via Wightman | SIGNED; includes rough grazing |
| \(H\) | 106.6 | `councils.json` (`:4`) | UK HPI Scotland, 2026-03, base Jan 2023 = 100; file built 2026-06-08 (since revised to 107.6 in the Jul 2026 release; v1 stays pinned to 106.6) | LIVE, not covered by the `agr.yaml` sign-off; wrong base for \(V_{09}\) (P0-2) |
| \(H_0,\lambda\) | 100, 2.5 | `valuation.py:27`, `:74/79` | hard-coded | code constants |
| \(P_c\) | Glasgow £184,281 | `councils.json` (`:83`) | UK HPI average price, 2026-03 (since revised to £186,428; v1 stays pinned) | LIVE, not covered by the `agr.yaml` sign-off |
| \(G\) | 9 m² | `agr.yaml:216` (`:121`) | n/a | SIGNED |
| \(A_i\) | 759.57 m² (G1 1BL); 1,897.42 m² (KW1 4AA) | runtime RoS INSPIRE WMS (`parcels.py:62-66,120-121`); also `backend/tests/test_shadow.py:9,36` | WMS at request time (QA snapshot, 4 Oct 2026) | runtime input |
| Council geometry | n/a | `sources.yaml` boundaries | unofficial mirror, 2013 vintage (BACKLOG D1-2) | defect |
| Data zone | not priced | `docs/ENGINE.md:53` (2022 DZ is a label only) | 2022 DZ label | n/a |

### 1.8 Worked substitution (reproduces both live figures to the penny)

**Glasgow G1 1BL** (\(c=\) S12000049, \(Z_c=0\)):
$$
\bar R=0.75(1950)+0.25(2300)=2037.5,\quad B_c=85\times2037.5\times1.05=181{,}846.875,\quad D_c=0.55B_c=100{,}015.78125
$$
$$
s_c=\tfrac{184{,}281-100{,}015.78125}{184{,}281}=0.45726\in[0.15,0.85]\Rightarrow S_c=84{,}265.21875
$$
$$
e_c=\tfrac{84{,}265.21875}{280}\times0.70\times0.05=10.53315234375,\qquad
\mathrm{AGR}^{par}=\operatorname{rd}_2(10.53315234375\times759.57)=\operatorname{rd}_2(8{,}000.6665)=\mathbf{\pounds8{,}000.67}\ \checkmark
$$
- Plot: \(\operatorname{rd}_2(e_c\times280)=\pounds2{,}949.28\).
- Square: \(\operatorname{rd}_2(10.5332\times9)=\pounds94.80\).
- **Warning for QA:** rounding \(e_c\) first gives \(10.5332\times759.57=8{,}000.69\), which is 2p off.

**Wick KW1 4AA** (\(c=\) S12000017 Highland \(\in\mathcal R\), \(Z_c=1\)):
$$
e_c=\tfrac{4094\times(106.6/100)\times0.20\times0.05}{10{,}000}=0.004364204,\qquad
\mathrm{AGR}^{par}=\operatorname{rd}_2(0.004364204\times1897.42)=\operatorname{rd}_2(8.28073)=\mathbf{\pounds8.28}\ \checkmark
$$
- Plot (1 ha): £43.64. Square: \(\operatorname{rd}_2(0.004364\times9)=\pounds0.04\).

**Both reproduced to the penny.** The only input not in code or config is \(A_i\), which comes from the live RoS polygon (§1.4).

**Reconciliation with Engine's file.** I now agree with Engine's corrected version on τ placement, the 4/6 dp rounding applying only to the square, the hard-coded \(H_0\) and \(\lambda\), the 11 rural councils and the overrides. Engine's open item 8 (the `report.py` scale step) is now checked: it is the fiscal-panel scale in §1.5, and it doesn't touch the public parcel figure.

### 1.9 Live defects an economist will raise (all already logged; none fixed here)
1. The council-level \(Z_c\) with its price rule (§1.1).
2. One location per council: \(P_c\) is a council average, so \(e_c\) is flat within a council.
3. The residual \(P_c-D_c\) rests on an unsourced \(d\) and on \(F\), the top two uncertainty drivers (BACKLOG P0-2).
4. \(\pi_u\) and \(\pi_f\) are policy-style factors inside the valuation, before an unsourced \(y\) (S13 double-count point).
5. The farmland value is uplifted with a house price index on the wrong base.
6. There is no plot-size curve (\(g\equiv1\)): \(e_c\) is spread over a notional 280 m² but charged on the whole parcel.
7. The clamp bounds are untested.
8. The fiscal-panel scaling uses rounded squares.

---
## Part 2. Target model (the design Laurie accepted at 12:21; terms unsigned)

### 2.1 Units, layers, date
$$
t_0=\text{1 Apr 2025 (UNSIGNED PROPOSAL; D13)},\qquad k\in\{\text{surface}^{\,active},\ \text{foreshore\_seabed},\ \text{minerals},\ \text{water},\ \text{wind\_wave}\}\ \ (\text{P-00})
$$
$$
\mathcal U_k=\mathcal U_k^{LR}\cup\mathcal U_k^{S},\qquad \sum_{i\in\mathcal U_k}A_i=\Omega_k,\qquad |i\cap j|=0\ \ \forall\, i\neq j\in\mathcal U_k
$$
- \(\mathcal U^{S}\) is the Sasine remainder (S12): \(\Omega_k\) minus the union of Land Register extents. The Land Register covered 59.8% of Scotland in Feb 2026 (v2 changelog).
- Only \(k=\) surface is valued at launch. Foreshore and seabed are excluded (D11).
- Every value carries \(t_0\), its layer \(k\), and the vintage of each input (including `dz_vintage`).

### 2.2 Per-point routing (replaces \(Z_c\))
$$
U_i=\mathbb 1\big[\text{UR2022 class at the centroid of } i \text{ is urban/settlement}\big]\quad(\text{S9 } \texttt{stand-in:sg-ur2022};\ \text{used by S11 for pooling})
$$
- This is a stand-in until use and allocation (S6) and land type (S7) are available per point.
- \(U_i\) only picks the evidence route. It is not a rate. Both routes produce the same quantity: annual site rent in £/yr, with buildings and owner improvements excluded.

### 2.3 Urban and developable land (\(U_i=1\), or allocated for development under basis b)
$$
r_{b,i}=\begin{cases}\text{observed ground rent per m}^2 & \text{where rent evidence exists}\\[2pt] y^{*}\,v_b(x_i,u_i) & \text{otherwise}\end{cases}
$$
$$
\mathrm{SRV}^{raw}_i=A_i\;r_{b,i}\;g(A_i)\;\mu_i
$$
- **\(v_b\) is land capital value per m²**, for use \(u\) at location \(x\) on basis \(b\in\{a,b,c\}\). The recommendation is basis (b), consented or allocated use (D1).
- **How \(v_b\) is estimated, in order of preference:**
  1. land-only sales (S1);
  2. hedonic or land-share decomposition of full sales (S2, Rosen 1974; Davis & Heathcote 2007; Davis & Palumbo 2008);
  3. residual \((P-D)/L\) as a cross-check only (S3).
- Values are smoothed through the S11 location surface at data-zone level. The access model is used only to fill gaps.
- **\(y^{*}\) is a valuation input (S13).** It is the market rent-to-capital ratio. It is not a policy discount (D3: none on top).
- **Plot-size curve \(g\)** (D4):
$$
g(A^{ref})=1,\qquad \frac{dg}{dA}\le 0,\qquad \frac{d\,[A\,g(A)]}{dA}\ge0\ \ \Big(\text{equivalently } -1\le \tfrac{d\ln g}{d\ln A}\le0\Big)
$$
  "Stance plus remainder" is the piecewise special case \(A\,g(A)=\min(A,A^{ref})+\tfrac{r^{rem}}{r}\max(0,A-A^{ref})\).
- **Assembly factor:** \(\mu_i=1\) unless there is assembly or plottage evidence (D10).
- **Hope value:** \(h_i=\mathrm{SRV}^{(b\text{ or }c)}_i-\mathrm{SRV}^{(a)}_i\). It is stored separately and never added in.

### 2.4 Rural land (\(U_i=0\)), route D (FOP, RECOMMENDED; unsigned)
$$
\mathrm{SRV}^{raw}_i=\frac{I(t_0)}{I(2020)}\,(1-\beta)\sum_{q}A_{iq}\,\rho_q\qquad[A_{iq}\ \text{in ha},\ \rho_q\ \text{in 2020 £/ha/yr, gross of buildings}]
$$
$$
\rho_q=\exp(\theta_1-\theta_2\,n_q),\quad \theta_2\ge0\qquad(\text{ASSUMPTION: two-parameter monotonic curve, F2/F3})
$$
Calibration to the two published mean rents (2020 survey, S8 `stand-in:sg-dec-survey-rent-2020`). LFA is used only as a calibration label, never as a rate:
$$
\frac{\sum_q a^{L}_q\,\rho_q}{\sum_q a^{L}_q}=\bar\rho^{L}=28,\qquad \frac{\sum_q a^{N}_q\,\rho_q}{\sum_q a^{N}_q}=\bar\rho^{N}=143
$$
- **Solving for \(\theta_2\):** dividing the two conditions removes \(\theta_1\):
$$
\Phi(\theta_2)\equiv\frac{\sum_q \tilde a^{N}_q e^{-\theta_2 n_q}}{\sum_q \tilde a^{L}_q e^{-\theta_2 n_q}}=\frac{143}{28},
$$
  where \(\tilde a\) are the area shares.
- **Uniqueness:** \(\Phi(0)=1\). If the LFA class mix is worse than the non-LFA mix in the likelihood-ratio order (ASSUMPTION, to be checked on Data's measured \(a_q\)), then \(\Phi\) is strictly increasing. A unique \(\theta_2>0\) exists if \(143/28\) is below \(\lim\Phi\). \(\theta_1\) then follows from either condition.
- **Pending inputs:** \(a_q\) is Data's LCA-by-LFA area table (licence check pending). \(I\) is UNKNOWN (F9). \(\beta\) is UNKNOWN (F6). No value is proposed for \(\beta\); the default is 0, shown as illustrative.
- **Double-count guard:** \(\pi_f\) (0.20) never appears on route D or C.
- **Forestry, hill and sporting land with no rent series:** \(\mathrm{SRV}^{raw}_i=A_i\,y^{*}_{type}\,v_{type}\), from S8 sales.

### 2.5 Floor, totals, policy layer
$$
\mathrm{SRV}_i=\max(0,\mathrm{SRV}^{raw}_i)\ \ (\text{raw kept, flag if}<0;\ \text{D9}),\qquad T=\sum_{i}\mathrm{SRV}_i,\quad T^{raw}=\sum_i\mathrm{SRV}^{raw}_i
$$
$$
\mathrm{AGR}_i=\tau\;\mathrm{SRV}_i\;(1-\delta_i)\;\phi_t\qquad(\tau,\ \delta_i,\ \phi_t:\ \text{Laurie's choices; no values here})
$$
- \(\tau\) applies to **every** published figure (job 002), unlike the live code (§1.5).
- **Rounding (UNSIGNED PROPOSAL):** compute everything in full float64 precision, and round only the final £ once, to 2 dp. Use Python `round` (half to even on the binary value), as the live code does, so QA and the API keep penny parity. Whether to move to decimal half-up is for Engine and Laurie to decide.

### 2.6 Accuracy test (needs paid RoS sales; until then, aggregate checks only)
For held-out sales \(j\) with price \(P_j\) and prediction \(\hat P_j\) (land from §2.3–2.4 plus depreciated buildings), let \(R_j=\hat P_j/P_j\) and \(\tilde R=\operatorname{median}(R)\):
$$
\tilde R\in[0.90,1.10],\qquad \mathrm{COD}=\frac{100}{n\,\tilde R}\sum_j|R_j-\tilde R|,\qquad \mathrm{PRD}=\frac{\tfrac1n\sum_jR_j}{\sum_j\hat P_j/\sum_jP_j}\in[0.98,1.03]
$$
- COD targets: residential 5–15 (up to 20 in rural areas); vacant land 5–20, or up to 25 (IAAO *Standard on Ratio Studies* 2013, §5.4.1; copy in Data's `refs/`).
- All thresholds are D6, unsigned. Until hold-out sales exist, we publish ranges only and make no per-plot accuracy claim.

### 2.7 Uncertainty (no numbers asserted)
- **Log-additive structure (urban):** \(\ln\mathrm{SRV}=\ln A+\ln y^{*}+\ln v+\ln g+\ln\mu\). By the delta method, \(\operatorname{Var}(\ln\mathrm{SRV})\approx\sum_X\operatorname{Var}(\varepsilon_X)+2\sum_{X<Y}\operatorname{Cov}(\varepsilon_X,\varepsilon_Y)\).
  - The covariances matter. For example, \(y^{*}\) and \(v\) estimated from the same sales are negatively correlated. Location errors in \(v\) and \(g\) are correlated within a cell.
- **Residual leverage (live and cross-check route):** with \(v=(P-D)/L\) and site share \(s=(P-D)/P\),
$$
\frac{\partial\ln v}{\partial\ln P}=\frac1s,\qquad \frac{\partial\ln v}{\partial\ln D}=-\frac{1-s}{s}.
$$
  - A small \(s\) amplifies input error. ILLUSTRATIVE, using only the live numbers above: Glasgow's \(s=0.457\) gives leverage of about 2.2 on price error and about 1.2 on cost error. At the clamp floor \(s=0.15\), these become about 6.7 and 5.7.
  - This is why the residual is a cross-check, not the primary route.
- **Rural:**
  - sampling error in the two calibration means (survey standard errors UNKNOWN), carried through the Jacobian of \((\theta_1,\theta_2)\) with respect to \((\bar\rho^L,\bar\rho^N)\);
  - class misallocation in the 1:250k LCA map, which is material for small parcels;
  - error in the index ratio \(I(t_0)/I(2020)\);
  - error in \(\beta\), with \(\partial\ln\mathrm{SRV}/\partial\beta=-1/(1-\beta)\).
- **Propagation:** Monte Carlo over the ranges in Data's files (v2; scenario band in v1 §3), with correlated draws where inputs share a source. Report P10 and P90 for each unit and for \(T\).
  - A symbol with no range (UNKNOWN) is not given an invented one. It is reported as unpropagated.
  - Model error is separate from input error. It is estimated from hold-out ratio dispersion (COD) once §2.6 is possible.

### 2.8 Identification: how each unknown is pinned down

| Unknown | Estimator | Data (slot) | Check |
|---|---|---|---|
| \(y^{*}\) | median of paired rent/capital by use | S13 | stable across cells; no policy discount on top (D3) |
| \(v_b\) | vacant-sale comparison; hedonic or land-share split (Rosen 1974; Davis & Heathcote 2007; Davis & Palumbo 2008) | S1, S2, S11 | hold-out ratios (§2.6); residual cross-check (S3) |
| \(d\) (only for the cross-check and building deduction) | market extraction from sales (IAAO) | S2, S3 | sign and size against the SAA obsolescence candidate |
| \(g\) | regress \(\ln(\pounds/\text{m}^2)\) on \(\ln A\) within location cells; Albouy & Ehrlich (2013) about −0.6 (US) as a reference only | S1, S4, S5 | elasticity in [−1, 0] |
| \(\mu\) | assembly-sale premium; Brooks & Lutz (2016) 15–40% (Los Angeles) as a reference only | S1 | \(\mu=1\) unless evidenced (D10) |
| \(\theta_1,\theta_2\) | two-equation calibration (§2.4) | S7, S8, \(a_q\) | reproduces 28 and 143; \(\theta_2\ge0\) |
| \(I\), \(\beta\) | named Scottish rent series; rent-review evidence | S8 | F9, F6 |
| \(U_i\) | UR2022 lookup, later S6/S7 | S9, S11 | no council-wide switch |

### 2.9 Symbol table

| Symbol | Meaning | Units | Slot | Source | Status |
|---|---|---|---|---|---|
| \(t_0\) | valuation date | date | n/a | proposal 1 Apr 2025 | UNSIGNED PROPOSAL (D13) |
| \(k,\Omega_k\) | land layer, total area | n/a, m² | n/a | P-00 | UNSIGNED PROPOSAL |
| \(A_i\) | unit area | m² | S4, S12 | RoS LR and Sasine | live via INSPIRE WMS; target needs S12 |
| \(U_i\) | per-point urban indicator | 0/1 | S9/S11 | SG UR2022 | STAND-IN |
| \(v_b\) | land capital value | £/m² | S1, S2, S11 | sales | UNKNOWN (STAND-IN `sg-dz-sales-2023`) |
| \(y^{*}\) | capitalisation rate | 1/yr | S13 | paired rent/price | UNKNOWN (live 0.05 STAND-IN, unsourced) |
| \(g, A^{ref}\) | plot-size curve | n/a, m² | S5 | fitted | UNKNOWN |
| \(\mu_i\) | assembly factor | n/a | S1 | evidence | ASSUMPTION = 1 |
| \(b, h_i\) | basis, hope difference | n/a, £/yr | S6 | D1 | UNSIGNED PROPOSAL |
| \(\rho_q,\theta_1,\theta_2\) | class rent curve | £/ha/yr | S7, S8 | calibrated | ASSUMPTION (form); UNKNOWN (values) |
| \(a^L_q,a^N_q\) | class areas inside and outside the LFA | ha | S7 | measured, `lfa-lca/` (Data) | MEASURED; licence allows use; Hutton notice awaits Laurie |
| \(\bar\rho^L,\bar\rho^N\) | mean rents | £/ha/yr | S8 | 28, 143 (2020 survey) | STAND-IN |
| \(I\) | rent index | n/a | S8 | n/a | UNKNOWN (F9) |
| \(\beta\) | buildings deduction | share | S8 | n/a | UNKNOWN (F6) |
| \(\mathrm{SRV}_i,T\) | site rent, total | £/yr | n/a | output | n/a |
| \(\tau,\delta_i,\phi_t\) | rate, relief, phasing | share | policy | Laurie | UNKNOWN (policy) |
| \(\tau_{cap},\tau_{sc}\) | live rates | share | policy | `agr.yaml:217,232` = 1.0 | SIGNED (live) |
| \(F,L,\bar R,R_h,R_f,w_h,w_f,k_c,d,\sigma\) | live residual inputs | §1.7 | S3, S9 | `agr.yaml` | SIGNED; mostly unsourced |
| \(\pi_u,\pi_f\) | live factors | share | policy | `agr.yaml:210,212` | SIGNED; retired in target |
| \(V_{09},H,H_0,\lambda\) | live rural inputs | §1.7 | S8 | `agr.yaml:225`, `councils.json`, code | `agr.yaml` rows SIGNED; `councils.json` and code values LIVE, not covered by sign-off; P0-2 |
| \(Z_c,\mathcal R,\bar P_{rur}\) | live rural switch | n/a | n/a | `sources.yaml:28-34` | live; DEFECT |

---

## 3. Invariants for QA (mapped to M §5.4 HARD RULES)

| # | Rule (M §5.4) | Test on this equation |
|---|---|---|
| 1 | P-01 value ≥ 0 | \(\mathrm{SRV}_i\ge0\) for all \(i\); raw value stored and flagged |
| 2 | P-02 buildings don't move value | changing building attributes leaves \(\mathrm{SRV}_i\) unchanged on the comparison route |
| 3 | P-03 location moves value | two units in one council and different S11 cells get different \(r\) (fails live: \(e_c\) is flat) |
| 4 | P-04 amenity layer inert where sales are rich | in sales-rich cells, \(\mathrm{SRV}\) is unchanged when access inputs are removed |
| 5 | P-07 improvements and occupancy inert | no improvement or occupancy symbol enters §2.3–2.4 |
| 6 | P-15 coverage | \(\sum A_i=\Omega_k\) within tolerance; overlaps 0; \(\sum\mathrm{SRV}_i=T\) |
| 7 | P-16 once only | each unit, and each shared interest, appears in exactly one row (D12) |
| 8 | P-17 one date | a single \(t_0\) per release; index series named |
| 9 | P-18 policy-neutral valuation | changing \(\tau,\delta,\phi\) leaves every \(\mathrm{SRV}_i\) and the valuation hash unchanged |
| 10 | P-19 deterministic | same inputs give a byte-identical output with version and date stamps |

**Extra checks:**
- E1. The API matches this document to the penny (Part 1 now; Part 2 once built).
- E2. Double-count guard: \(\pi_f\) is absent on routes C and D, and no policy discount sits on \(y^{*}\).
- E3. \(\rho_q\) is non-increasing in class rank (\(\theta_2\ge0\)).
- E4. Calibration reproduces 28 and 143 (tolerance to be set by QA).
- E5. \(g\) is non-increasing, and \(A\,g(A)\) is non-decreasing.
- E6. The anchors £8,000.67 and £8.28 stay frozen until a signed change.

## 4. Open decisions (Laurie unless noted)
- **D13:** \(t_0\) (proposed 1 Apr 2025) and the uplift index.
- **F2/F3:** the shape of the rent curve.
- **F6:** \(\beta\).
- **F9:** the rent index \(I\).
- **D3:** confirm no discount on top of \(y^{*}\).
- **D10:** when \(\mu\neq1\).
- **D1:** basis.
- **D4:** form of \(g\).
- **D6:** accuracy thresholds.
- **D9:** the floor.
- **D11/D12:** scope.
- **Rounding rule** (Engine and Laurie, §2.5).
- **Fixing the \(Z_c\) defect** (replace with \(U_i\); BACKLOG P0-1/D0-1). This is a live-figure change, so it needs signing.
- **Fiscal-panel scale** rounding (Engine).
- **HPI base**, P0-2 (a live-figure change, needs signing).

## 5. References (each one checked to exist)
- Mirrlees, J. et al. (2011) *Tax by Design*, ch. 16 "The taxation of land and property", IFS/OUP. ifs.org.uk/books/16-taxation-land-and-property
- Dye, R.F. and England, R.W. (eds) (2009) *Land Value Taxation: Theory, Evidence, and Practice*. Lincoln Institute of Land Policy, ISBN 978-1-55844-185-9. (The brief's date of 2010 is corrected here to 2009.)
- Davis, M.A. and Heathcote, J. (2007) "The price and quantity of residential land in the United States", *Journal of Monetary Economics* 54(8), 2595–2620.
- Davis, M.A. and Palumbo, M.G. (2008) "The price of residential land in large US cities", *Journal of Urban Economics* 63(1).
- Rosen, S. (1974) "Hedonic prices and implicit markets", *Journal of Political Economy* 82(1).
- Albouy, D. and Ehrlich, G. (2013) "Metropolitan land values and housing productivity", NBER WP 18110.
- Brooks, L. and Lutz, B. (2016) "From today's city to tomorrow's city: an empirical investigation of urban land assembly", *AEJ: Economic Policy* 8(3).
- IAAO (2013) *Standard on Ratio Studies*; IAAO (2025) *Standard on Mass Appraisal of Real Property*.
- Scottish Land Commission (2018) *Land Value Tax: Policy Options for Scotland*, final report.
- In Data's `refs/` pack, not re-checked by me: Gloudemans and Almy (2011); McCluskey and Franzsen (2005).

---

## Addendum A. Price, rent and the charge (capitalisation link between the layers)

*Added 4 Oct 2026, 12:57, Policy & Economics. Proposal, unsigned. No figures.*

With annual rent \(R\), discount rate \(i\), expected rent growth \(g\) (\(i>g\)) and an annual land charge \(T\) already in force:

$$ P = \frac{R - T}{i - g} \quad\Longrightarrow\quad R = (i-g)\,P + T $$

- **Charge as a share of rent**, \(T = \tau R\): \(P = (1-\tau)R/(i-g)\). Price falls linearly in \(\tau\) and is zero at \(\tau = 1\).
- **Charge as a percentage of capital value**, \(T = tP\): \(P = R/(i-g+t)\). Price falls along a hyperbola and never reaches zero.
- **Use:** cross-check only (Engine spec). It never sets a figure, because (a) \(i-g\) is the unsourced \(y^{*}\), (b) prices also capitalise hope value, risk, reliefs and amenity (farmland rent/price is about 0.5%, Data S13), and (c) as \(\tau \to 1\), \(P \to 0\), so the check reduces to \(R = T\). Above a set charge share the engine values from rents only.

## Addendum B. Identifying the land share (validation beyond whole-property sales)

A held-out test on whole-property sales checks \(L + B\) only. It cannot detect offsetting errors in the land share \(s = L/(L+B)\). Separate checks on \(s\):
1. vacant-plot sales (needs paid RoS price-paid data; rare);
2. teardown sales, where price is close to land value (Dye & McMillen 2007, *Journal of Urban Economics*; **UNVERIFIED citation**). Needs demolition or warrant linkage, which is a licensed feed and Laurie's decision;
3. aggregate benchmarks: the ONS national balance sheet land value (UK only, no Scottish split) and Davis & Heathcote (2007, US). Cross-checks only.

Correlated inputs (for example \(P\) and \(C\) within a council) partly cancel in the residual \(P - C\), so full positive correlation can narrow the land range. Each correlated pair is run at \(\rho \in \{-1, 0, +1\}\) and the widest range is published until \(\rho\) is evidenced.


## Addendum C: definitions tightened (4 Oct 2026, after Data's inputs table)
- \(x_i\): the parcel's centroid as a point, used to look up every cell-based input (land cover, LCA, data zone). Cell inputs are area-weighted over the parcel only where the parcel crosses more than one cell. UNSIGNED PROPOSAL.
- \(u_i\): land use. Source not chosen. Candidates for Data: OS Open Zoomstack or OS MasterMap Topography where licensed, and Scottish Assessors non-domestic use classes. UNKNOWN.
- \(n_q\): LCA rank in the order 1, 2, 3.1, 3.2, 4.1, 4.2, 5.1, 5.2, 5.3, 6.1, 6.2, 6.3, 7, giving \(n_q = 1\ldots13\). The equal spacing is an ASSUMPTION (F2), to be tested against a free-rank fit.
- \(\Omega_k\) beyond surface land is defined in the rent ledger (`rent-ledger-2026-10-04.md`), not here.
- Data vintages: every published figure is pinned to the data release it was built from. Later revisions (such as HPI 106.6 to 107.6) are reported as measurement error and do not move a signed figure.

## Addendum D: forestry and the no-yield check (4 Oct 2026; UNSIGNED PROPOSAL)
- **QA invariant (adopted by Policy):** no S13 rate may appear among the inputs of any main-route farmland figure (R-03). QA tests this by tracing the inputs each figure actually used, not by reading the config.
- **Forestry site value without a market yield:** Data found no official series of forestry yields (S13-forestry is UNKNOWN). Proposed main route: the Faustmann land expectation value,
$$LEV=\frac{\sum_t (p_t Q_t - C_t)(1+r)^{T_{rot}-t}}{(1+r)^{T_{rot}}-1},$$
where \(T_{rot}\) is the rotation length (renamed so it doesn't clash with the published total \(T\)).
built from Forest Research timber prices (OGL), yield-class growth models and costs. Annual site rent is \(r\cdot LEV\). The discount rate \(r\) is still a policy input, so it is UNKNOWN and is shown as a range.
- **Cross-check and floor:** the farmland rent \(\rho_q\) for the same land-capability class, which is the land's next-best use. A forestry site rent below it is flagged for review.
- v1 has no live forestry value (`agr.yaml:224` is never read), so v1-settings mode leaves forestry out.
- **Display rule (proposed, 4 Oct 2026):** until measured costs and a link from land to yield class exist, forestry land reads "Not yet estimated", with no range shown on its own (QA D6). No central figure is proposed, because none can be sourced yet. Forest Research timber prices cover conifers only, so broadleaf woodland stays "Not yet estimated" even after that. The farmland floor is a check, not an estimate, and is never shown in its place.
