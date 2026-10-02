# Registers of Scotland — research data enquiry (template)

Use this when requesting a pilot extract for Scot-LAND.

---

**Subject:** Research data enquiry — residential sales for AGR residual pilot (Glasgow Ward 18 / Glasgow City)

Dear Registers of Scotland data team,

We are developing **Scot-LAND**, an open **Annual Ground Rent (AGR)** research and education tool for the Scottish Land Revenue Group (SLRG). The tool estimates site-only rental values using a professional residual method (market value less depreciated replacement cost of improvements), aligned with published SLRG/Wightman methodology.

We would like to obtain a **licensed research extract** of completed residential property transactions to:

1. Validate residual land-value estimates against local sales evidence  
2. Pilot sales-comparable residual extraction for **Glasgow City**, ideally focusing on or including **Glasgow Ward 18 (East Centre)**  
3. Assess feasibility of mass-appraisal techniques (e.g. open-source OpenAVMKit) without scraping commercial property portals  

**Preferred fields (where available):**

- Sale/completion price and date  
- Property type and new-build flag  
- Postcode and/or coordinates / UPRN  
- Floor area (and plot area if held)  
- Tenure  
- Any unique record identifier  

**Use:** Non-commercial research and public education map; we will not scrape Zoopla/Rightmove and will not republish individual personal data beyond licence terms.

**Outputs:** Methodology documentation, aggregate statistics, and model validation for SLRG. Individual addresses will be handled per your licence and UK GDPR.

Please advise on available products, open data options, research licensing, costs, and lead times.

Kind regards,  
[Name]  
[Organisation / SLRG]  
[Email]  
[Phone]

---

After receipt:

1. Store under `data/licensed/` with `LICENSE.txt`  
2. Convert if needed: `python -m etl.convert_sales_csv ...`  
3. Validate: `python -m etl.ingest_sales --path ... --require-production`  
4. Name file `data/licensed/sales.jsonl` for auto-load by `ValuationService.default()`  
