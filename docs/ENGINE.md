# Land engine

This is the record of 2 October 2026. The charge is the yearly rent of one whole registered parcel. The public pounds are unchanged. `data/config/agr.yaml` is unchanged. The live calculator is unchanged. The log of the sitting is `docs/engine/LOG.md`. The choice of the full Annual Ground Rent stays in `docs/DECISION.md` and is not reopened.

## The charge

The charge is the full Annual Ground Rent of one whole Registers of Scotland indicative parcel. It is a yearly rent. The building stays with the person who made it. Floor area is not the thing charged and is not shown. Wages, trade, and the building are not taxed. The return on an improvement stays with the person who paid for it. Hope value is not added. A gap between this rent and a price that includes hope is only a recorded difference. The 60 percent site share is not used. One cadastral unit, including a tenement steading, returns one yearly rent. Parcel rents are not added up to the national rent pool. Capture is 1.0.

A pound here is the signed-off research estimate. It is not an official rates bill, not this year's Scottish budget, and not the sum of the squares.

## The formula

Take the measured ground area of that one parcel, in square metres on British National Grid, and multiply by one signed intensity per square metre.

The council comes from the Land Register title seed. It does not come from a data zone, a ward, a portal, or a council rural flag. Land Capability for Agriculture code 888 is the urban class. Both published anchors are code 888, so neither anchor is a field, and the council rural flag does not choose the rate.

Where the existing authorised use is agriculture and the parcel is not code 888, the intensity is the signed agriculture rate and no other 2009 land-use capital. That rate is £4,094 per hectare, times the Scotland House Price Index factor 106.6/100, times the farmland Pickard factor 0.20, times the 5 percent yield. It is about £0.004364 per square metre per year, on the whole parcel. It does not rise with a particular improvement or with hope.

Where the signed path is urban, the intensity is the signed residual of the council on the title seed. Start from the March 2026 all-property average. Subtract the depreciated rebuild of one typical dwelling. Clamp only if the implied site share is outside 15 to 85 percent. Then apply the urban Pickard factor 0.70 and the 5 percent yield, and divide by the 280 square metre notional plot. The 85 square metre dwelling is only the building strip inside that rate. It is not the charge and it is not shown.

For Glasgow City the average is £184,281, the region factor is 1.05, and the blended rebuild is £2,037.50 per square metre, so the intensity is about £10.53315 per square metre per year. Glasgow G1 1BL has no mapped lower-land remainder, so the whole of about 760 square metres stays on that rate, near £8,001. Exactly 760 square metres at that intensity is £8,005.20. The parcel is not cut to 280 square metres. The public pound remains near £8,001.

Wick KW1 4AA is code 888 in a remote small town. Highland's rural flag does not set its rate, and code 888 does not select the agriculture rate. The published ground charge stays near £8.28 on about 1,897 square metres because the public pounds are not changed. That published pound is what the signed agriculture intensity produces on the same ground. Leaving it there is not a classification of Wick as a field, is not the rent of that small-town land, and is not the value the public made by making the location a town. The gap is only recorded. It is not added, and it does not switch the signed rule. Replacing £8.28 with the rent of that town land needs a new signed number. That replacement is a later decision for the user who accepts or rejects a formula. This formula does not sign one. The SLRG economist's sign-off of 8 June 2026 on the public pounds is left unchanged.

George's vacant-land test is the other later decision for the same user. A vacant site on the urban rate still has a land rent, with no building required. It is recorded. It is not given a pound, and it is not used to change the pounds.

An existing-use label, a confidence, and a data-zone name may be stored beside the parcel. The economist's objection list was empty. The unresolved Wick gap and the vacant-land test are answered by leaving both unsigned.

## Use

An existing authorised use and a confidence may be stored beside the whole Registers of Scotland INSPIRE parcel, keyed by the INSPIRE id. The label does not change the signed-off full Annual Ground Rent. The agriculture intensity applies only where that existing authorised use is agriculture and the parcel is not code 888. Everywhere else the signed urban intensity stands, and code 888 does not switch a parcel onto the agriculture rate.

The join is the share of cadastral ground. Polygons are cut against the parcel. A point is used only when that source has no polygon and the point falls inside the parcel. Floor area is never used and never shown. The building stays with the person who made it.

Every parcel still receives a class and a confidence. The base paint is residential inside an NRS settlement and agriculture outside it. Stronger evidence overpaints only the ground it covers, in this order: National Forest Inventory woodland as forestry; OS Open Greenspace as open space; an operational renewable-energy polygon, or a road or rail corridor, as infrastructure only where that polygon is the land itself rather than a line crossing it; then a PSGA or other OS-licensed OS NGD Land Use site, ignoring Unknown Use, or else the modal One Scotland Gazetteer class of UPRNs inside the parcel, counted without floor area; then the Scottish Vacant and Derelict Land Survey previous use, through the survey's own codes. A blank previous use paints urban vacant. Development potential does not paint. Last is a Spatial Hub planning polygon from any of the 34 planning authorities, and only where the decision is granted, or a certificate of lawfulness of existing use was issued, the permission has not expired, and no later granted change of use replaces it. The development type is read onto the Use Classes (Scotland) Order 1997 as amended by SSI 2023/35, as one class for the whole parcel: classes 1A and 3 to business and retail; classes 4 and 7 to business; classes 5 and 6 to industrial; classes 8, 8A and 9 and sui generis housing to residential; classes 10 and 11 to assembly or institutional. Pending, refused, and withdrawn applications do not paint.

The parcel class is the largest painted share. Confidence is high when a consent polygon is that majority, medium when the winner is the vacant-land previous use, a licensed site or address class, or a consent point, and low when the winner is cover or the settlement default. A consent point with no polygon sets the whole parcel only if every other paint is still the default. If no class has half the parcel and two non-default classes are both present, the class is mixed existing use. Mixed is a class. A small steading consent does not reclass the rest of a farm. For open ground, the NatureScot and Space Intelligence 2024 habitat map is used where its terms allow, otherwise the UKCEH Land Cover Map under its non-commercial terms: arable and improved grassland are agriculture, and heath, bog, and montane are agriculture as rough grazing. If neither licence fits the public site, forestry, open space, and the settlement default still cover every parcel. Sporting is used only when a licensed source or the title says sporting.

Housing Land Supply sites that are not completed, unbuilt energy consents, and vacant-land development potential are stored only as a hope difference. They never replace the class, and the difference is not added to the rent.

No open layer states the lawful use of every title. The planning feed records applications rather than the use that was already lawful. Many red lines do not match the cadastral parcel. East Ayrshire's polygons are buffered points. The Registers of Scotland parcel is an indicative ownership extent, not a full title plan. OS NGD land use and the One Scotland Gazetteer are licensed, not open, and OS leaves some sites as Unknown Use. The 2024 habitat map is not published as OGL. Cover shows what is on the ground rather than a consent. There is no open parcel register of sporting use. A blank previous-use code on vacant land is only a weak urban-vacant class, because an older lawful use can survive vacancy.

## Area

The area charged is the whole indicative parcel, measured in square metres on British National Grid, EPSG:27700. The building is not subtracted. Floor area is not used and is not shown. A field on the agriculture path is the agriculture intensity times that whole area. A city parcel with no mapped lower-land remainder is the urban intensity times that whole area. Glasgow G1 1BL is that case. It is not cut to the 280 square metre notional plot. That 280 square metres sits inside the urban intensity only. It is not a measured local median, and it is not forced onto either anchor.

A shared title is the rent of the whole piece, not one household bill. A tenement is one cadastral unit for the steading, including pertinents within 25 metres, however many flats have title sheets. A shared plot beyond that is its own cadastral unit. Several address points in one polygon do not divide the rent. Garden is land. It is not rooms and it is not extra dwellings.

The polygon is indicative, not the legal title, and Sasine land is missing, so the measured piece can still be wrong. A tenement click can return one flat's title number while the polygon is the whole steading. There is no open national field map, because the rural payments field map stays behind a login. The coarse capability sheet cannot mark a small poor patch, and the finer sheet does not cover the hills. A split of one title into stance and lower land, or a zero on poor land, is not used to cut either published anchor. Hope value is not added.

## Location

The rent grain stays the council on the title seed. Glasgow G1 1BL is Glasgow City, S12000049. Wick KW1 4AA is Highland, S12000017. The same seed can carry a 2022 Data Zone name beside the parcel. For these two anchors those names are S01017413 City Centre East - 06 and S01017958 Wick North - 01. The zone is not priced. A ward is not priced. A portal is not the council. Highland's rural flag is not the rate.

No open price below council is mix-adjusted. A zone or ward median still contains the building. The open sales table is still on 2011 Data Zones through 2023 and is not controlled for house type or size. The only zone comparison stored here is a difference, and it is not a multiplier: City Centre East - 05, S01010263, was £145,000 against a Glasgow City median of £173,000, and Wick North - 01, S01010782, was £81,500 on six sales against a Highland median of £203,000. Using the first ratio would cut about £8,001 by about a sixth. Using the second would cut about £8.28 by more than half. Neither cut is made.

A finer grain needs a licensed Registers of Scotland market-value sales extract with house type and the title seed. It may be used only if Glasgow G1 1BL is still near £8,001 and Wick KW1 4AA is still near £8.28. Until that test passes, every parcel in the council keeps the signed council intensity.

## Quality

Code 888, Urban, is not class 7 and is not a field. On the national Land Capability sheet, Glasgow G1 1BL at 259696, 665068 and Wick KW1 4AA at 336230, 951308 are both 888. A fragment coded 888 keeps the per-square-metre rent already published. It is not moved to hill, forestry, or zero.

The free James Hutton sheets can describe farmland, hill, and forestry on a parcel that is not code 888. Classes 1 to 5.3 share the one signed agriculture capital of £4,094 per hectare in 2009. Classes 6.1 to 6.3 share the signed £100 per hectare rough-land capital. Forestry on the National Forest Inventory, where the forestry capability is F1 to F4, was described at the signed £1,000 per hectare. Class 7 and land with no surplus were described at the signed marginal rent of zero. No free rent series can split those classes further and still average back to the signed-off pounds. Outside the improved lowlands the finer sheet is often missing, so much of the north depends on the coarse 1981 and 1988 maps, which are not being updated. The woodland inventory misses woods under 0.5 hectare.

This formula does not apply those other 2009 capitals, and it does not sum band rents into a new charge. Where the existing use is agriculture and the parcel is not code 888, the only intensity is the signed agriculture rate above. Trees, drains, fences, and buildings stay with the person who made them. Afforestation on bare land, and any other hope, is a difference that is recorded and not added. A missing polygon cannot wipe the charge.

## The floor

The charge does not go below zero. Land at the margin pays nothing, which is the signed marginal rent of 0. A payment to remote land, meant to draw people there, is not the charge. A settlement grant, a ferry, or a clinic can be spent out of the rent pool. That spending is not the parcel rent.

People in a remote place gain because their charge falls with the surplus, taxes on wages, trade, and buildings come off, and one person's share of the national pool is the same as in Glasgow. The research credit of £500 a year per person in Na h-Eileanan Siar, Orkney, Shetland, Highland, and Argyll and Bute stays that per-person knob. It is not a negative assessment and it does not scale with hectares. A cheque on the land would be bid into the price, and the largest holding would take the largest cheque.

## Henry George

The draft did not pass. The failing sentence said that Highland is rural, so Wick KW1 4AA stays on that field rate for about 1,897 square metres, near £8.28, even though the postcode is a remote small town and both anchors are code 888. That sentence is not the rule. Code 888 is the urban class. The field rate left on Wick is not the rent of that small-town land, and it is not the value the public made by making the location a town.

What does hold for Glasgow is the rent of the land. G1 1BL is the yearly rent of the whole parcel: ground area times the council residual after the depreciated dwelling is taken out of the rate. The building stays with the maker. Floor area is not charged. A vacant site on that urban rate still has a land rent, with no building required. The signed config excludes hope value and uses the existing authorised use. That difference is only recorded. Hope is not added. This check does not switch the signed rule or the public pounds, and it does not give the vacant site a new pound.

George was not asked to endorse the site. He is not recorded as having passed. Replacing the Wick pound, or pricing the vacant-land test, is a later decision for the user who accepts or rejects a formula.

## Adam Smith

Adam Smith passed. No failing sentence was returned. He is not recorded as requiring every other tax to be replaced, and he is not recorded as endorsing the site. The site nonetheless states the full Annual Ground Rent.

The charge he was given is ground-rent: the yearly rent of the ground of one whole registered parcel. Wages, trade, and the building are not taxed. The urban rate subtracts the depreciated dwelling and then falls on measured ground area only. The agriculture rate does not rise with a particular improvement or with hope, so the return on an improvement stays with the person who paid for it. A charge on that ground-rent should not raise the price of the produce of labour. A gap against a price that includes hope is only a recorded difference.

## Objections already tested

The economist's objection list was empty. No attack on it was turned into a new rate. The faults that were open to attack, if they were really in the formula, were these: garden counted as rooms; a tenement compared with one person; a rural house charged as a field; a city field charged as a house; house prices treated as if they were already land rent; the national pool treated as a sum of parcels; a scraped portal; a silent change to the signed-off figures. None of those was returned.

The same sitting defined a house, a tenement, a shop, a field, a hill, and a vacant urban site, and it defined a wrong answer for each. Those rows are tests. They are not a new public charge. A wrong house answer is a price, a rebuild cost, a charge on 85 or 280 square metres, a floor area on the screen, or a moved Glasgow pound. A wrong tenement answer is the house rent times the number of flats, a split by internal floor area, or several bills on one close. A wrong shop answer is the Glasgow house pound, a rateable value, or a portal price. A wrong field answer is the urban residual because a house stands on the farm, or a bill of £8.28 on any area other than the Wick anchor. A wrong hill answer is a positive full charge from a hoped-for turbine, plantation, or second home. A wrong vacant answer is the urban house intensity on vacant ground, or a pound given to George's vacant-land test. Derelict land is not the vacant row.

The two items the economist could not correct without a new signed number stay unresolved. The Wick gap is only recorded. The vacant-land test is only recorded. Neither is given a pound.

## What is not claimed

This formula does not claim that Wick is a field, that £8.28 is the rent of that small-town land, or that £8.28 is the value the public made by making the location a town. It does not sign a town-land intensity for Wick. It does not price a vacant site. It does not add hope, a zone median, or a ward median. It does not use the 60 percent site share. It does not show floor area. It does not cut Glasgow to 280 square metres. It does not tax wages, trade, or the building. It does not sum parcels into the national rent pool. It does not pay a negative charge on remote land. It does not reopen the full Annual Ground Rent. It does not scrape Zoopla, Rightmove, ESPC, OnTheMarket, or the Scottish Assessors portal. It does not say that Henry George or Adam Smith endorses the site. The Registers of Scotland polygon remains an indicative extent, not the legal title.

## Glasgow and Wick

The public checks are unchanged.

Glasgow G1 1BL, title SCT0007431917, stays near £8,001 a year on about 760 square metres. The signed urban intensity is about £10.53315 per square metre per year. The parcel is not cut to 280 square metres. Exactly 760 square metres at that intensity is £8,005.20, which is the same rate on that round area, not a new public pound.

Wick KW1 4AA, title SCT0003389903, stays near £8.28 a year on about 1,897 square metres. The parcel is code 888 in a remote small town. Highland's rural flag does not choose that rate. The published pound is what the signed agriculture intensity produces on the same ground. The gap to the rent of that town land is recorded and is not added.
