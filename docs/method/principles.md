> **Working design** (Scot-LAND, 4 Oct 2026). Copied unchanged from the team's working file `land-economics-principles-2026-10-04.md`.
> Where it mentions sign-off, pinned Glasgow and Wick figures or frozen files, those were the rules when it was written; they were lifted on 4 Oct 2026 while the engine is developed.

# Land-economics principles for Scot-LAND
*Policy & Economics, 4 Oct 2026, about 12:25 BST. A guide for Laurie, Engine, Data, QA and Comms. It changes no figure, contains no code, and nothing has been posted.*

**How to read this.**
- Each principle has an id (P-01 …), a plain statement, its sources, what it means for the engine, and a tag:
  - **HARD RULE**: QA can test it as an invariant on every branch.
  - **DEFAULT WITH EXCEPTIONS**: the normal pattern, with named cases where it can reverse.
  - **LAURIE'S CHOICE**: a value judgement or policy decision, not a fact. The engine computes the options and Laurie picks one.
- Quotes are given only where I read the wording at the source (4 Oct 2026). Otherwise I paraphrase.
- Every figure is either quoted from the cited source or already sits in a workspace file, which is named.
- **ASSUMPTION** marks my own judgement. "Unknown" means I don't know.
- The method spec is `engine-method-first-principles-2026-10-04.md`, which cites these ids. Input slots S1–S10 are Data's (`engine-inputs-proposal-v2-2026-10-04.md`).

---

## A. What land value is

**P-00 "Land" means land in the economic sense (added 4 Oct 2026, 12:35, for Laurie's sign-off).**
- *Statement.* Land is the third factor of production alongside labour and capital: every natural resource and opportunity that nobody made. That covers surface sites and their location, minerals, water, foreshore and seabed, and natural opportunities such as wind and wave sites. Anything people have made or added (buildings, drainage, fences, soil improvement) is capital, not land.
- *Sources.* Henry George, *Progress and Poverty* (1879), Book I ch. 2, where land is described as including "all natural materials, forces, and opportunities" (paraphrase; check the wording at the source before quoting it). Ricardo (1817) ch. 2, as in P-01.
- *Engine.* The map currently values only part of it: surface land, by location and land type. Foreshore and seabed are left out (D11). Minerals, water, and wind and wave rights are not valued yet. Each would be a separate layer with its own source, and none of them is in scope.
- *Tag.* **HARD RULE** for wording: no page or paper may say the map values all land in this sense. Whether and when to add the other layers is **LAURIE'S CHOICE**.

**P-01 Rent is what the land itself earns.**
- *Statement.* Rent is the payment for the land, not for anything built on it or put into it. It is a surplus over what the poorest land in use earns.
- *Sources.* Ricardo, *On the Principles of Political Economy and Taxation* (1817), ch. 2 "On Rent": rent is paid "for the use of its original and indestructible powers". https://www.econlib.org/book-chapters/chapter-ch-2-on-rent/
- *Engine.* Value only the land's own attributes: location, size, shape, capability and planning status. Land at the margin earns about nothing, so its site rent is never negative.
- *Tag.* **HARD RULE:** published site rental value ≥ 0. A raw negative from the model is flagged and never published as a negative. How to show contaminated or negative-value land is LAURIE'S CHOICE (D9 in the spec).

**P-02 Site value leaves out every improvement.**
- *Statement.* Land and buildings are separate tax bases. The land part is "one of the best taxes" and the building part "one of the worst".
- *Sources.*
  - Vickrey, quoted in the Mirrlees Review, *Tax by Design* (IFS, 2011), ch. 16 "The Taxation of Land and Property": the property tax is "a combination of one of the worst taxes – the part that is assessed on real estate improvements … and one of the best taxes – the tax on land or site value". https://ifs.org.uk/books/16-taxation-land-and-property
  - NZ Rating Valuations Act 1998 (land value as if "no improvements had been made"; review source [4]).
- *Engine.* On the ideal path, the site value of a land unit doesn't change if you change its building: floor area, age, condition or use. Today's residual stand-in breaks this, because it subtracts the building from the price, so its results must carry the stand-in label (`stand-in:residual-from-price`, Data S1).
- *Tag.* **HARD RULE** on the ideal path. QA test: change only the building inputs and the site value doesn't move. A residual stand-in result must be labelled.

**P-03 Location is what drives land value.**
- *Statement.* Land rent falls with distance and cost of access to markets, jobs and services. Users bid for location, and the highest bidder sets the rent.
- *Sources.*
  - von Thünen, *Der isolierte Staat* (1826). Rent falls with transport cost from the central market. Bibliographic record: https://www.thuenen.info/?page_id=724
  - Alonso, *Location and Land Use: Toward a General Theory of Land Rent* (Harvard University Press, 1964), the urban bid-rent model. DOI 10.4159/harvard.9780674730854
  - George, *Progress and Poverty* (1879), Book IV: the gains of material progress show up as rising rent. https://www.econlib.org/library/YPDBooks/George/grgPP.html
- *Engine.* Location needs its own fine-grained surface (Data S9), at data-zone or postcode level or finer. One rate per council is a stand-in.
- *Tag.* **HARD RULE** for the ideal engine. QA test: the £/m² moves with location inside a council, not only at council borders. Today's one-rate-per-council output fails this by design and must be labelled `stand-in:uk-hpi-la`.

**P-04 Count location once.**
- *Statement.* Sale prices already contain the value of access, amenity, transport and views. Adding an access or amenity score on top of a sales-derived value counts the same thing twice.
- *Sources.* Rosen, "Hedonic Prices and Implicit Markets", *Journal of Political Economy* 82(1), 1974, pp. 34–55 (prices are bundles of implicit attribute prices). https://doi.org/10.1086/260169. Applying this to double counting is **ASSUMPTION** (my reading).
- *Engine.* Access and amenity measures (jobs, transport, services, views) may only interpolate the location surface where sales are thin. They never act as an extra multiplier where sales exist.
- *Tag.* **HARD RULE.** QA test: in a sales-rich cell, removing the amenity layer leaves the value unchanged.

**P-05 Separating land from buildings uses evidence.**
- *Statement.* The land share of a property's value is estimated, not assumed. It varies a lot by place and over time.
- *Sources.*
  - Rosen (1974), above (the hedonic decomposition).
  - Davis & Palumbo, "The price of residential land in large US cities", *Journal of Urban Economics* 63(1), 2008, pp. 352–384. Across 46 US metros, land was "about 50 percent" of housing value by end-2004, "up from 32 percent in 1984". https://ideas.repec.org/a/eee/juecon/v63y2008i1p352-384.html
  - Ryan-Collins, Lloyd & Macfarlane, *Rethinking the Economics of Land and Housing* (Zed Books, 2017), on land as the missing factor in housing economics. https://www.bloomsbury.com/au/rethinking-the-economics-of-land-and-housing-9781786991195/
- *Engine.* Use land-only sales (S1) and a hedonic or land-share model on full sales (S2). Fixed shares or factors, such as 0.55, 0.70 and 0.20, are stand-ins.
- *Tag.* **DEFAULT WITH EXCEPTIONS.** The residual is allowed as a labelled cross-check. A fixed share is never the ideal.

## B. Why tax land, and what that implies for the valuation

**P-06 Unearned increment.**
- *Statement.* Much of the rise in land value comes from the growth of the community, not from the owner's effort.
- *Sources.* Mill, *Principles of Political Economy* (1848; 1871 edition), Book V, ch. II. Mill calls much of the increase in rent "unearned, and, as it were, accidental", and sees "no objection to declaring that the future increment of rent should be liable to special taxation". https://en.wikisource.org/wiki/Principles_of_Political_Economy_(J.S._Mill,_1871),_vol._2/Book_V,_Chapter_II
- *Engine.* The valuation layer reports the full site rent. How much of it to collect, and whether to tax only future increases as Mill proposed, sits in the policy layer.
- *Tag.* **LAURIE'S CHOICE** (capture share and transition).

**P-07 A land tax doesn't shrink the tax base or distort what gets built.**
- *Statement.* Land is fixed in supply. So a tax on its value, set without reference to how the owner uses it, doesn't change what or when the owner builds.
- *Sources.*
  - Mirrlees Review (2011), ch. 16: a "strong case for introducing a land value tax" (IFS chapter page above).
  - Tideman, "Taxing Land Is Better than Neutral: Land Taxes, Land Speculation, and the Timing of Development" (Lincoln Institute working paper, 1995; in *Land-Value Taxation*, Routledge, 2016, pp. 109–133). A tax that "does not vary with how land is used … does not alter the timing of development when markets are perfect". Taxes that vary with use or apply only to undeveloped land do alter it. https://cooperative-individualism.org/tideman-t-nicolaus_taxing-land-is-better-than-neutral-1995-jan.pdf
  - Gaffney, "The hidden taxable capacity of land: enough and to spare", *International Journal of Social Economics* 36(4), 2009, pp. 328–411: the land tax "has no excess burden". https://doi.org/10.1108/03068290910947930
- *Engine.* A land unit's value must not depend on what its holder builds, uses it for, or leaves empty. A current-use basis breaks this, because the value then follows the owner's choices.
- *Tag.* **HARD RULE** for the valuation output under any basis: the owner's improvements and occupancy never change the figure. Whether to adopt a current-use basis, which weakens neutrality, is **LAURIE'S CHOICE** (D1).

**P-08 Henry George theorem.**
- *Statement.* Under stated conditions, at the optimal city size, total land rents equal spending on pure local public goods.
- *Sources.* Arnott & Stiglitz, "Aggregate Land Rents, Expenditure on Public Goods, and Optimal City Size", *Quarterly Journal of Economics* 93(4), 1979, pp. 471–500. They find it "far more robust than has previously been suspected" but "still far from completely general". https://doi.org/10.2307/1884466
- *Engine.* National and council totals of site rent are meaningful aggregates, and the engine must be able to produce them (P-14). Comparing them with public spending is illustration only. It is not a test of the engine.
- *Tag.* **DEFAULT WITH EXCEPTIONS** (it holds only under its conditions).

**P-09 Public investment shows up in land value.**
- *Statement.* Roads, rail, schools and services raise the value of nearby land. Value-capture instruments recover part of that rise.
- *Sources.* Ingram & Hong (eds), *Value Capture and Land Policies* (Lincoln Institute, 2012). https://www.lincolninst.edu/publications/books/value-capture-land-policies/
- *Engine.* Effects of infrastructure enter through sales evidence at each revaluation (P-16). They are never added by hand (P-04).
- *Tag.* **DEFAULT WITH EXCEPTIONS.** Where a scheme is new and has no sales yet, flag the area. Don't guess the uplift.

**P-10 Who really pays, and why the output is a rent.**
- *Statement.* The classic view is that a tax on land rent falls wholly on the landlord and comes off the land price. Feldstein shows that it can be partly shifted, and the price of land may even rise.
- *Sources.*
  - Mill (1871), Book V, ch. III: "A tax on rent falls wholly on the landlord." https://en.wikisource.org/wiki/Principles_of_Political_Economy_%28J.S._Mill%2C_1871%29%2C_vol._2/Book_V%2C_Chapter_III
  - Feldstein, "The Surprising Incidence of a Tax on Pure Rent", *Journal of Political Economy* 85(2), 1977, pp. 349–360: the tax "is at least partly shifted". https://doi.org/10.1086/260566
  - SLC 2018 (review source [1]) on the "one-for-one" fall in price.
- *Engine.* Publish an annual site rental value estimated from pre-reform market evidence. Never feed the engine's own charge back into the prices it values from. How the burden would actually fall in Scotland is unknown.
- *Tag.* **HARD RULE** (output is annual rent; no feedback). The incidence question is open.

## C. What basis to value on

**P-11 Current use, or highest and best use.**
- *Statement.* Mass appraisal normally treats current use as the highest and best use. Valuing at the most profitable permitted use gives the incentive effect, but it is costly and open to challenge.
- *Sources.* IAAO, *Standard on Mass Appraisal* (2025); SLC 2018 (review §3, sources [5] and [1]).
- *Engine.* Compute current use, consented or allocated use, and highest and best permitted use for every land unit. Publish only the basis Laurie chooses.
- *Tag.* **LAURIE'S CHOICE** (D1).

**P-12 Hope value is kept separate.**
- *Statement.* Capital values include hope value, which is the price of the chance of a future consent (SLC 2018, review §1).
- *Engine.* Store `hope_difference` as its own field. Whether any of it is charged is a policy setting.
- *Tag.* **LAURIE'S CHOICE** (D1). **HARD RULE:** hope value is never folded silently into the current-use figure.

## D. Size, shape and the unit of valuation

**P-13 Value per m² falls as plots get bigger.**
- *Statement.* In US sales, value per acre has an elasticity of about −0.6 with lot size.
- *Sources.* Albouy & Ehrlich (2013), review source [7]. Figure as quoted in review §4.
- *Engine.* A plot-size curve fitted from Scottish sales (S1, S4, S5). Until it exists, the curve is `stand-in:policy-plot-size-rule`.
- *Tag.* **DEFAULT WITH EXCEPTIONS** (see P-14). Where no plottage applies, QA can check that £/m² doesn't rise with area at a fixed location.

**P-14 Plottage and assembly can reverse it.**
- *Statement.* Land being joined into a bigger site can sell at a premium.
- *Sources.* Brooks & Lutz, "From Today's City to Tomorrow's City: An Empirical Investigation of Urban Land Assembly", *AEJ: Economic Policy* 8(3), 2016, pp. 69–105: "to-be-assembled land in Los Angeles trades at a 15 to 40 percent premium". https://doi.org/10.1257/pol.20130399
- *Engine.* Value each land unit as it is held. Apply an assembly premium only where evidence or an allocation (S6) shows assembly. Whether to do so at all is **LAURIE'S CHOICE** (D10). Scottish evidence: unknown.
- *Tag.* **DEFAULT WITH EXCEPTIONS.**

**P-15 Every m² is covered exactly once.**
- *Statement.* Scotland's land area = the Land Register title units + the unmapped Sasine remainder, with no gaps and no overlaps. National and council totals add up from the units.
- *Sources.* An accounting requirement. It follows from SLC 2022's call to bring all land onto the roll (review source [2]), but this precise rule is **ASSUMPTION**.
- *Engine.* Overlapping title polygons are resolved before valuing, and the method is logged. The Sasine remainder is the land area minus the title extents. Foreshore and seabed are excluded unless Laurie decides otherwise (D11).
- *Tag.* **HARD RULE.** QA test: Σ unit areas = land area within a stated tolerance; overlap area = 0; Σ unit values = published totals.

**P-16 Value the land once, as if it carried no other interests.**
- *Statement.* Where several interests share one piece of land, such as a croft tenancy under an estate title or a long lease, the land is valued once, as if unencumbered.
- *Sources.* **ASSUMPTION** (method choice). It follows P-02 and P-15.
- *Engine.* One value per land unit. Splitting that value between the interests is a later policy question.
- *Tag.* **HARD RULE** (no land unit is valued twice). How to split is **LAURIE'S CHOICE** (D12).

## E. When and how well

**P-17 One valuation date for everything.**
- *Statement.* Every figure is valued as at one date, like the Assessors' tone date. Older evidence is indexed to that date.
- *Sources.* IAAO (review [5]) on annual review and reproducible models. The tone-date practice of Scottish Assessors: date not cited here (unknown in our files).
- *Engine.* Every result states the valuation date and the index used, by series and month.
- *Tag.* **HARD RULE.** QA test: all results in a release carry the same valuation date, and each one names its index.

**P-18 Keep valuation separate from policy.**
- *Sources.* SLC/WPI Economics 2025, lesson 3 (review source [3]).
- *Engine.* Changing a policy setting never changes the valuation output. Each layer carries its own version hash.
- *Tag.* **HARD RULE.** QA test: change only the policy config and the valuation hash and values stay the same.

**P-19 Same inputs, same answer.**
- *Statement.* Two land units with identical land attributes get identical values. Reruns are reproducible.
- *Sources.* IAAO (review [5]): models should be reproducible.
- *Engine.* Deterministic runs, with engine version, config hash and data vintages stamped on every result.
- *Tag.* **HARD RULE.**

**P-20 Accuracy and fairness have to be measured.**
- *Statement.* Mass valuations tend to be less sensitive to neighbourhood than market prices are, which shifts the burden between areas.
- *Sources.*
  - Avenancio-León & Howard, "The Assessment Gap: Racial Inequalities in Property Taxation", *QJE* 137(3), 2022, pp. 1383–1434: "Property assessments are less sensitive to neighborhood attributes than market prices are." https://doi.org/10.1093/qje/qjac009
  - IAAO ratio-study targets (median ratio, COD, PRD; review §7, source [6]).
- *Engine.* Run hold-out ratio studies with PRD and PRB, by council, by price decile and by location. This needs RoS sales (S2). Until then, the only checks are against council and data-zone averages and the SLC regional £/ha (Data v2, held-out section).
- *Tag.* **HARD RULE:** no per-plot accuracy claim is made without a hold-out against real sales. Which thresholds to adopt is **LAURIE'S CHOICE** (D6).

## F. Rural land

**P-21 Rural rent comes from capability and access.**
- *Statement.* Better land and land nearer markets earn more rent: Ricardo's differential rent and von Thünen's rings.
- *Sources.* Ricardo (1817), von Thünen (1826), above. Land Capability for Agriculture (Hutton; review [8]).
- *Engine.* Value rural land by capability class and land type (S7, S8), and by access and remoteness (S9). Use farm rents as direct rent evidence (review §5).
- *Tag.* **DEFAULT WITH EXCEPTIONS.** At a fixed location, a better LCA class is not valued lower. Exceptions: sporting, amenity and peri-urban hope value. Those show up in sales and are labelled.

## G. Fairness and transition (policy only)

**P-22 Ability to pay, and the transition.**
- *Statement.* Land-rich, cash-poor holders and sudden changes in value raise questions of fairness.
- *Sources.*
  - SLC 2018 (review [1]): deferral until sale or death, and phasing.
  - Mill (1871), Book V, ch. II: tax only the future increment, with the present market price "secured" to owners.
  - Oates & Schwab, "The Impact of Urban Land Taxation: The Pittsburgh Experience", *National Tax Journal* 50(1), 1997, pp. 1–21. https://ideas.repec.org/a/ntj/journl/v50y1997i1p1-21.html
  - Ryan-Collins et al. (2017), above.
- *Engine.* Nothing in the valuation layer. Reliefs, deferral and phasing go in the policy layer.
- *Tag.* **LAURIE'S CHOICE** (D7).

---

## Summary of tags
- **HARD RULE (QA invariants):** P-01, P-02 (ideal path), P-03 (ideal engine), P-04, P-07 (output side), P-10, P-12 (no silent folding), P-15, P-16, P-17, P-18, P-19, P-20 (no claim without hold-out).
- **DEFAULT WITH EXCEPTIONS:** P-05, P-08, P-09, P-13, P-14, P-21.
- **LAURIE'S CHOICE:** P-06, P-07 (basis), P-11, P-12, P-14 (assembly premium), P-16 (split), P-20 (thresholds), P-22, plus negative values (P-01) and foreshore and seabed (P-15).

## Unknowns
- The Assessors' current tone date (not in our files).
- Scottish evidence on plottage.
- How the burden of an Annual Ground Rent would actually fall in Scotland.
- The share of Scotland still on the Sasine register (Data v1 §1.2).
