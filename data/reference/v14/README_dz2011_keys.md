# DZ2011 key set (6,976 Data Zone 2011 codes)

`dz2011_keys.json`: sorted JSON array of the 6,976 Scottish Data Zone 2011 codes (S01006506 to S01013481).
Codes only; no values.

Source: Scottish Government, Data Zone Boundaries 2011
(https://maps.gov.scot/ATOM/shapefiles/SG_DataZoneBdry_2011.zip, fetched 3 Nov 2026,
zip sha256 846950b7dc74fdedc8a6c5c3d9fd9c5afeca3477a103505b590613bc9704bed8).
File sha256 2611c9e701d9affef34680be2a0d9bbc14468ddbc5241f353819f9ee59849874 (pinned in
`backend/scripts/build_v14_check_inputs.py` as DZ2011_KEYS_SHA256).

Licence: Open Government Licence v3.0 — Contains public sector information licensed under the
Open Government Licence v3.0. Contains Scottish Government and Ordnance Survey data
© Crown copyright and database right 2026.

Used by the 2024 check-inputs join (`--dz2011-keys`, STEP8-DZ2011-KEYING): the builder zones must be an
exact subset of this set, ur6 must cover exactly this set and is then restricted to the builder zones.
Check 6 stays keyed on DZ2022. Also available to DZ-HEATMAP as the DZ2011 code list.
