#!/usr/bin/env python3
"""Scot-LAND Data Zones: build zone spine, people crosswalk, SIMD, CT bands, dwelling mix.
All inputs are open NRS / Scottish Government downloads in ../raw (see sources.md).
No numbers are invented: every value is read from a source file or derived by documented arithmetic.
"""
import re, json, csv, os, sys, argparse
from pathlib import Path
import numpy as np, pandas as pd, openpyxl

# ---------------------------------------------------------------- configuration (CLI > env var > default)
_ap = argparse.ArgumentParser(description="Build Scot-LAND Data Zones tables from raw NRS/SG downloads (run fetch.py first).")
_ap.add_argument("--root", default=os.environ.get("DZ_ROOT"), help="project root (env DZ_ROOT; default: parent of this script's folder)")
_ap.add_argument("--raw", default=os.environ.get("DZ_RAW"), help="raw input folder (env DZ_RAW; default: ROOT/raw)")
_ap.add_argument("--out", default=os.environ.get("DZ_OUT"), help="output folder (env DZ_OUT; default: ROOT/out)")
_ap.add_argument("--park-overlay", default=os.environ.get("DZ_PARK_OVERLAY"),
                 help="Scot-LAND GIS dz_park_overlay.csv (env DZ_PARK_OVERLAY; default: RAW/dz_park_overlay.csv)")
_args = _ap.parse_args()
ROOT = Path(_args.root).resolve() if _args.root else Path(__file__).resolve().parents[1]
RAW = Path(_args.raw).resolve() if _args.raw else ROOT / "raw"
OUT = Path(_args.out).resolve() if _args.out else ROOT / "out"
PARK_OVERLAY = Path(_args.park_overlay).resolve() if _args.park_overlay else RAW / "dz_park_overlay.csv"
REQUIRED = ["SIMD_2020v2_datazone_lookup_updated_2025.xlsx", "SIMD_2020v2_ranks.xlsx", "SIMD_2020v2_indicators.xlsx",
            "oa22_dz22_iz22/OA22_DZ22_IZ22.csv", "oa22_dz22_iz22/DZ22_Lookup.csv", "spd_lookups/Data Zone 2011 Lookup.csv",
            "spd_index/SmallUser.csv", "census_2022_index/Census_2022_Index/Postcode_To_OA.csv",
            "census_oa/UV101b - Usual resident population by sex by age (6).csv",
            "sape22_11.xlsx", "sape-2024-22dz-data.xlsx", "household-estimates-by-2011-data-zones.xlsx",
            "household-estimates-by-2022-data-zones-24-25.xlsx", "dwellings-estimate-by-2011-data-zones.xlsx",
            "dwelling-estimates-by-2022-data-zones-24-25.xlsx", "dgs_house_prices.csv", "dgs_ct_band_2022dz.csv",
            "dgs_ct_band_cgb_2011dz.csv", "dgs_dwellings_by_type.csv", "dgs_dwellings_by_rooms.csv"]
_missing = [f for f in REQUIRED if not (RAW / f).is_file()]
if _missing:
    sys.exit(f"ERROR: {len(_missing)} input file(s) missing under {RAW}:\n  " + "\n  ".join(_missing) + "\nRun: python3 scripts/fetch.py")
if not PARK_OVERLAY.is_file():
    sys.exit(f"ERROR: national park overlay not found at {PARK_OVERLAY}.\n"
             "It is produced by Scot-LAND GIS (data/processed/gis/dz_park_overlay.csv), not downloadable from a publisher.\n"
             "Set DZ_PARK_OVERLAY=/path/to/dz_park_overlay.csv or pass --park-overlay, or copy it to RAW/dz_park_overlay.csv "
             "(python3 scripts/fetch.py --park-overlay PATH does this and verifies its checksum).")
OUT.mkdir(parents=True, exist_ok=True)
print(f"ROOT={ROOT}\nRAW={RAW}\nOUT={OUT}\nPARK_OVERLAY={PARK_OVERLAY}", file=sys.stderr)
QA = {}
DZ11 = [f"S0{i}" for i in range(1006506, 1013482)]
DZ22 = [f"S0{i}" for i in range(1013482, 1020874)]
assert len(DZ11) == 6976 and len(DZ22) == 7392
CODE_RE = re.compile(r"^S0[0-9]{7}$")


def xlsx_table(path, sheet, header_startswith):
    """Read an NRS accessible-format sheet: find the header row, return DataFrame of S0 rows."""
    ws = openpyxl.load_workbook(path, read_only=True, data_only=True)[sheet]
    rows = list(ws.iter_rows(values_only=True))
    hi = next(i for i, r in enumerate(rows) if r and isinstance(r[0], str) and r[0].strip().startswith(header_startswith))
    hdr = [re.sub(r"\s+", " ", str(h)).strip() if h is not None else f"col{j}" for j, h in enumerate(rows[hi])]
    data = [r for r in rows[hi + 1:] if r and isinstance(r[0], str) and CODE_RE.match(r[0].strip())]
    df = pd.DataFrame(data, columns=hdr)
    df.iloc[:, 0] = df.iloc[:, 0].str.strip()
    return df


def num(s):
    return pd.to_numeric(s.replace({"[z]": np.nan, "[x]": np.nan, "-": 0}), errors="coerce")


# ---------------------------------------------------------------- hierarchy
simd_lk = pd.read_excel(RAW / "SIMD_2020v2_datazone_lookup_updated_2025.xlsx", sheet_name="SIMD 2020v2 DZ lookup data", dtype={"DZ": str, "IZcode": str, "LAcode": str})
simd_lk = simd_lk[simd_lk.DZ.str.match(CODE_RE, na=False)].copy()
assert len(simd_lk) == 6976 and set(simd_lk.DZ) == set(DZ11)

oa22 = pd.read_csv(RAW / "oa22_dz22_iz22/OA22_DZ22_IZ22.csv", dtype=str)
dz22_iz = oa22[["DZ22", "IZ22"]].drop_duplicates()
assert dz22_iz.DZ22.is_unique, "DZ22 must nest in exactly one IZ22"
assert set(dz22_iz.DZ22) == set(DZ22)
dz22_names = pd.read_csv(RAW / "oa22_dz22_iz22/DZ22_Lookup.csv", dtype=str, encoding="cp1252")
dz11_names = pd.read_csv(RAW / "spd_lookups/Data Zone 2011 Lookup.csv", dtype=str)

# population
sape11 = xlsx_table(RAW / "sape22_11.xlsx", "Table 1", "Data zone code")
sape11 = sape11[sape11["Sex"] == "Persons"]
sape22 = xlsx_table(RAW / "sape-2024-22dz-data.xlsx", "2024", "Data zone code")
sape22 = sape22[sape22["Sex"] == "Persons"]
assert len(sape11) == 6976 and len(sape22) == 7392

# households (occupied dwellings, Sept) & dwellings (Assessors, Dec)
hh11 = xlsx_table(RAW / "household-estimates-by-2011-data-zones.xlsx", "2025", "Data Zone code")
hh22 = xlsx_table(RAW / "household-estimates-by-2022-data-zones-24-25.xlsx", "2025", "Data Zone code")
dw11 = xlsx_table(RAW / "dwellings-estimate-by-2011-data-zones.xlsx", "2025", "Data Zone code")
dw22 = xlsx_table(RAW / "dwelling-estimates-by-2022-data-zones-24-25.xlsx", "2025", "Data Zone code")
for n, d, e in [("hh11", hh11, 6976), ("hh22", hh22, 7392), ("dw11", dw11, 6976), ("dw22", dw22, 7392)]:
    QA[f"rows_{n}_2025"] = len(d)
    assert d.iloc[:, 0].is_unique

# LA names/codes: CA2019 codes from NRS files (both vintages), cross-checked
la11 = sape11.set_index("Data zone code")[["Council area code", "Council area name"]]
la22 = sape22.set_index("Data zone code")[["Council area code", "Council area name"]]
la_simd = simd_lk.set_index("DZ")["LAcode"]
QA["dz2011_la_code_mismatch_simd_vs_nrs_sape"] = int((la_simd.reindex(la11.index) != la11["Council area code"]).sum())
hh11_la = hh11.set_index("Data Zone code")["Council area code"]
QA["dz2011_la_code_mismatch_hh_vs_sape"] = int((hh11_la.reindex(la11.index) != la11["Council area code"]).sum())
hh22_la = hh22.set_index("Data Zone code")["Council area code"]
QA["dz2022_la_code_mismatch_hh_vs_sape"] = int((hh22_la.reindex(la22.index) != la22["Council area code"]).sum())

# RoS price file (DZ2011)
ros = pd.read_csv(RAW / "dgs_house_prices.csv", dtype=str, usecols=["GeographyCode", "GeographyType", "DateCode", "Measurement", "Value"])
ros_dz = set(ros.loc[ros.GeographyType == "2011 Data Zones", "GeographyCode"])
absent_ros = sorted(set(DZ11) - ros_dz)
QA["ros_price_file_dz2011_present"] = len(ros_dz & set(DZ11))
QA["ros_price_file_dz2011_absent"] = absent_ros
QA["ros_price_file_years"] = [ros.DateCode.min(), ros.DateCode.max()]

# ---------------------------------------------------------------- crosswalk
spd = pd.read_csv(RAW / "spd_index/SmallUser.csv", dtype=str,
                  usecols=["Postcode", "DateOfDeletion", "SplitIndicator", "OutputArea2022Code", "DataZone2022Code", "DataZone2011Code",
                           "IntermediateZone2022Code", "IntermediateZone2011Code", "CouncilArea2019Code",
                           "CensusHouseholdCount2022", "CensusPopulationCount2022", "CensusPopulationCount2011"])
for c in ["CensusHouseholdCount2022", "CensusPopulationCount2022", "CensusPopulationCount2011"]:
    spd[c] = pd.to_numeric(spd[c])
# Census 2022 frozen postcode -> OA2022 index with postcode counts (NRS Census 2022 index), DZ2011 from SPD 2026/2 by postcode
cidx = pd.read_csv(RAW / "census_2022_index/Census_2022_Index/Postcode_To_OA.csv", dtype={"Postcode": str, "OutputArea2022Code": str})
spd_pc = spd[spd.CensusPopulationCount2022.notna() | spd.CensusHouseholdCount2022.notna()]
QA["spd_oa2022_differs_from_census_frozen_index_postcodes"] = int((spd_pc.set_index("Postcode").OutputArea2022Code != cidx.set_index("Postcode").OutputArea2022Code.reindex(spd_pc.Postcode)).sum())
chk_pc = cidx.merge(spd_pc[["Postcode", "CensusPopulationCount2022", "CensusHouseholdCount2022"]], on="Postcode", how="left")
QA["postcodes_census_index_households_ne_spd"] = int((chk_pc.HouseholdCount != chk_pc.CensusHouseholdCount2022).sum())
QA["postcodes_census_index_hhpop_ne_spd_usual_residents"] = int((chk_pc.PopulationCount != chk_pc.CensusPopulationCount2022).sum())
pc = cidx.rename(columns={"PopulationCount": "hh_pop_2022", "HouseholdCount": "households_2022"}).merge(
    spd_pc[["Postcode", "DataZone2011Code", "DataZone2022Code"]], on="Postcode", how="left")   # spd_pc is unique by postcode
assert len(pc) == len(cidx) and pc.Postcode.is_unique
QA["census_postcodes_without_spd_dz2011"] = int(pc.DataZone2011Code.isna().sum())
assert pc.DataZone2011Code.notna().all()
QA["census2022_postcodes"] = len(pc)
QA["census2022_postcode_household_population_total"] = int(pc.hh_pop_2022.sum())
QA["census2022_postcode_households_total"] = int(pc.households_2022.sum())
QA["spd_postcode_usual_residents_total_(incl_communal)"] = int(spd_pc.CensusPopulationCount2022.sum())
pc = pc.merge(oa22.rename(columns={"OA22": "OutputArea2022Code", "DZ22": "dz2022_oa"}), on="OutputArea2022Code", how="left")
assert pc.dz2022_oa.notna().all()
QA["postcodes_spd_current_dz2022_differs_from_census_frozen_oa"] = int((pc.dz2022_oa != pc.DataZone2022Code).sum())
QA["postcodes_spd_current_dz2022_differs_hh_pop"] = int(pc.loc[pc.dz2022_oa != pc.DataZone2022Code, "hh_pop_2022"].sum())

# QA only: Census 2022 OA household residents (UV101b) vs postcode household population summed to OA
rows = list(csv.reader(open(RAW / "census_oa/UV101b - Usual resident population by sex by age (6).csv", encoding="utf-8-sig")))
assert rows[4][22] == "Lives in a household" and rows[5][22] == "All people" and rows[6][22] == "Total"
assert rows[4][43] == "Lives in a communal establishment" and rows[6][43] == "Total" and rows[6][1] == "Total"
def iv(x):
    return 0 if x in ("-", "") else int(x)
uv = pd.DataFrame([(r[0], iv(r[1]), iv(r[22]), iv(r[43])) for r in rows[7:] if r and CODE_RE.match(r[0] or "")],
                  columns=["OutputArea2022Code", "oa_usual_res", "oa_hh_res", "oa_ce_res"])
assert len(uv) == 46363, len(uv)
QA["census2022_oa_household_residents_total_UV101b"] = int(uv.oa_hh_res.sum())
QA["census2022_oa_communal_residents_total_UV101b"] = int(uv.oa_ce_res.sum())
oa_cmp = pc.groupby("OutputArea2022Code").hh_pop_2022.sum().reindex(uv.OutputArea2022Code).fillna(0).values - uv.oa_hh_res.values
QA["oa_postcode_hhpop_vs_UV101b_abs_diff"] = {"oas_equal": int((oa_cmp == 0).sum()), "max_abs": int(np.abs(oa_cmp).max()), "mean_abs": round(float(np.abs(oa_cmp).mean()), 3)}
QA["census_oas_without_postcodes"] = int(len(set(uv.OutputArea2022Code) - set(pc.OutputArea2022Code)))
pc["hhres"] = pc.hh_pop_2022


cw = pc.groupby(["DataZone2011Code", "dz2022_oa"], as_index=False).hhres.sum().rename(columns={"DataZone2011Code": "dz2011", "dz2022_oa": "dz2022", "hhres": "basis_count"})
cw = cw[cw.basis_count > 0].copy()
cw["method"] = "pop_hhres_2022"
missing11 = sorted(set(DZ11) - set(cw.dz2011))
QA["dz2011_with_zero_2022_household_residents"] = missing11
# fallback for DZ2011 zones with no 2022 household residents: code route via their (terminated) postcodes,
# weighted on Census 2011 postcode population; contributes 0 to any DZ2022's people (reverse weight 0)
fb = spd[spd.DataZone2011Code.isin(missing11) & spd.CensusPopulationCount2011.notna()].drop_duplicates("Postcode").copy()
fb = fb.merge(oa22.rename(columns={"OA22": "OutputArea2022Code", "DZ22": "dz2022"}), on="OutputArea2022Code", how="left")
fb = fb.groupby(["DataZone2011Code", "dz2022"], as_index=False).CensusPopulationCount2011.sum().rename(columns={"DataZone2011Code": "dz2011", "CensusPopulationCount2011": "basis_count"})
fb["method"] = "fallback_census2011_pop_terminated_postcodes"
QA["fallback_rows"] = fb.to_dict("records")
cw = pd.concat([cw, fb], ignore_index=True)
cw["weight"] = cw.basis_count / cw.groupby("dz2011").basis_count.transform("sum")
main = cw.method == "pop_hhres_2022"
cw["reverse_weight"] = 0.0
cw.loc[main, "reverse_weight"] = cw.loc[main, "basis_count"] / cw[main].groupby("dz2022").basis_count.transform("sum")
cw = cw.sort_values(["dz2011", "dz2022"]).reset_index(drop=True)
main = cw.method == "pop_hhres_2022"
# validation
s1 = cw.groupby("dz2011").weight.sum(); s2 = cw.groupby("dz2022").reverse_weight.sum()
QA["cw_rows"] = len(cw)
QA["cw_dz2011_covered"] = int(cw.dz2011.nunique()); QA["cw_dz2022_covered"] = int(cw.dz2022.nunique())
assert set(cw.dz2011) == set(DZ11) and set(cw.dz2022) == set(DZ22)
QA["cw_max_abs_dev_weight_sum"] = float((s1 - 1).abs().max()); QA["cw_max_abs_dev_reverse_sum"] = float((s2 - 1).abs().max())
assert QA["cw_max_abs_dev_weight_sum"] < 1e-6 and QA["cw_max_abs_dev_reverse_sum"] < 1e-6
n22_per11 = cw.groupby("dz2011").dz2022.nunique(); n11_per22 = cw[main].groupby("dz2022").dz2011.nunique()
cw["_n22"] = cw.dz2011.map(n22_per11); cw["_n11"] = cw.dz2022.map(n11_per22).fillna(0)
QA["cw_one_to_one_pairs"] = int(((cw._n22 == 1) & (cw._n11 == 1)).sum())
QA["cw_dz2011_split_(maps_to_>1_dz2022)"] = int((n22_per11 > 1).sum())
QA["cw_dz2011_wholly_in_one_dz2022"] = int((n22_per11 == 1).sum())
QA["cw_dz2022_merged_(draws_from_>1_dz2011)"] = int((n11_per22 > 1).sum())
QA["cw_dz2022_from_single_dz2011"] = int((n11_per22 == 1).sum())
# materiality: ignoring slivers < 2% of either side
mat = cw[(cw.weight >= 0.02) | (cw.reverse_weight >= 0.02)]
QA["cw_material_(>=2%)_dz2011_split"] = int((mat.groupby("dz2011").dz2022.nunique() > 1).sum())
QA["cw_material_(>=2%)_dz2022_merged"] = int((mat[mat.reverse_weight >= 0.02].groupby("dz2022").dz2011.nunique() > 1).sum())
QA["cw_dz2011_max_weight_>=0.98"] = int((cw.groupby("dz2011").weight.max() >= 0.98).sum())
QA["cw_dz2022_max_reverse_>=0.98"] = int((cw[main].groupby("dz2022").reverse_weight.max() >= 0.98).sum())
QA["cw_basis_total_hhres"] = round(float(cw.loc[main, "basis_count"].sum()), 3)
cw_out = cw[["dz2011", "dz2022", "weight", "reverse_weight", "method", "basis_count"]].copy()
cw_out["basis_count"] = cw_out.basis_count.round(4)
cw_out.to_csv(OUT / "dz_crosswalk_people.csv", index=False, float_format="%.15g")

# ---------------------------------------------------------------- zone spine
def spine(vintage, codes, names, iz, la, pop, pop_year, hh, dw):
    d = pd.DataFrame({"code": codes})
    d["vintage"] = vintage
    d["name"] = d.code.map(names)
    d["iz_code"] = d.code.map(iz)
    d["la_code"] = d.code.map(la["Council area code"]); d["la_name"] = d.code.map(la["Council area name"])
    d["population"] = d.code.map(pop).astype("Int64"); d["pop_year"] = pop_year
    d["households"] = d.code.map(hh).astype("Int64"); d["hh_year"] = 2025
    d["dwellings"] = d.code.map(dw).astype("Int64"); d["dw_year"] = 2025
    return d

sp11 = spine(2011, DZ11, dz11_names.set_index("DataZone2011Code").DataZone2011Name, simd_lk.set_index("DZ").IZcode, la11,
             num(sape11.set_index("Data zone code")["Total population"]), 2022,
             num(hh11.set_index("Data Zone code")["Occupied dwellings"]), num(hh11.set_index("Data Zone code")["Total number of dwellings"]))
sp11["in_ros_price_file"] = sp11.code.isin(ros_dz)
sp22 = spine(2022, DZ22, dz22_names.set_index("DZ22").DZ22Name, dz22_iz.set_index("DZ22").IZ22, la22,
             num(sape22.set_index("Data zone code")["Total population"]), 2024,
             num(hh22.set_index("Data Zone code")["Occupied dwellings"]), num(hh22.set_index("Data Zone code")["Total number of dwellings"]))
sp22["in_ros_price_file"] = pd.NA   # RoS price file is published on DZ2011 only
for sp, hh in [(sp11, hh11), (sp22, hh22)]:
    h = hh.set_index("Data Zone code")
    tot = num(h["Total number of dwellings"]).reindex(sp.code).values
    vac = num(h[next(c for c in h.columns if c.startswith("Vacant dwellings") and "%" not in c)]).reindex(sp.code).values
    sec = num(h["Second homes"]).reindex(sp.code).values
    with np.errstate(divide="ignore", invalid="ignore"):
        sp["vacant_share"] = np.where(tot > 0, vac / tot, np.nan).round(6)
        sp["second_home_share"] = np.where(tot > 0, sec / tot, np.nan).round(6)
    sp["share_year"] = 2025
# IZ cross-check against SPD postcode index (2011)
spd_iz11 = spd.groupby("DataZone2011Code").IntermediateZone2011Code.agg(lambda x: x.mode().iat[0])
QA["dz2011_iz_mismatch_simd_vs_spd"] = int((sp11.set_index("code").iz_code != spd_iz11.reindex(sp11.code)).sum())
spd_iz22 = spd.groupby("DataZone2022Code").IntermediateZone2022Code.agg(lambda x: x.mode().iat[0])
QA["dz2022_iz_mismatch_nrs_oa_lookup_vs_spd"] = int((sp22.set_index("code").iz_code != spd_iz22.reindex(sp22.code)).sum())
spd_la11 = spd.groupby("DataZone2011Code").CouncilArea2019Code.agg(lambda x: x.mode().iat[0])
QA["dz2011_la_mismatch_vs_spd"] = int((sp11.set_index("code").la_code != spd_la11.reindex(sp11.code)).sum())
spd_la22 = spd.groupby("DataZone2022Code").CouncilArea2019Code.agg(lambda x: x.mode().iat[0])
QA["dz2022_la_mismatch_vs_spd"] = int((sp22.set_index("code").la_code != spd_la22.reindex(sp22.code)).sum())
# IZ->LA nesting
for sp, v in [(sp11, 2011), (sp22, 2022)]:
    QA[f"iz{v}_count"] = int(sp.iz_code.nunique()); QA[f"la_count_{v}"] = int(sp.la_code.nunique())
    QA[f"iz{v}_spanning_>1_la"] = int((sp.groupby("iz_code").la_code.nunique() > 1).sum())

def flags(r):
    f = []
    if r.vintage == 2011 and r.in_ros_price_file is False:
        f.append("absent_from_ros_price_file")
    if r.vintage == 2011 and r.code in missing11:
        f.append("no_census2022_household_residents")
    if pd.notna(r.population) and r.population == 0:
        f.append("population_zero")
    for c in ["population", "households", "dwellings"]:
        if pd.isna(r[c]):
            f.append(f"{c}_missing")
    # team rule v0.7
    if r.dw_year == 2025 and pd.notna(r.dwellings) and r.dwellings == 0:
        f.append("zero_dwellings")
    if (pd.notna(r.population) and pd.notna(r.households) and r.pop_year != r.dw_year
            and (r.population < 0.5 * r.households or (r.households == 0 and r.population > 0))):
        f.append("pop_dwellings_mismatch")
    return ";".join(f)

zs = pd.concat([sp11, sp22], ignore_index=True)
zs["in_ros_price_file"] = zs.in_ros_price_file.astype("boolean")
zs["flags"] = zs.apply(flags, axis=1).fillna("").astype(str)   # always a string; "" = no flags
_fl = lambda t: sorted(f"{c}/{v}" for c, v, x in zip(zs["code"], zs["vintage"], zs["flags"]) if t in x.split(";"))
QA["spine_zero_dwellings"] = _fl("zero_dwellings"); QA["spine_pop_dwellings_mismatch"] = _fl("pop_dwellings_mismatch")
assert QA["spine_zero_dwellings"] == ["S01010206/2011", "S01010226/2011", "S01010227/2011"], QA["spine_zero_dwellings"]
assert QA["spine_pop_dwellings_mismatch"] == ["S01010227/2011", "S01011598/2011"], QA["spine_pop_dwellings_mismatch"]  # S01010227: pop 1 (mid-2022), 0 households (2025)
zs = zs[["code", "vintage", "name", "iz_code", "la_code", "la_name", "population", "pop_year", "households", "hh_year", "dwellings", "dw_year", "vacant_share", "second_home_share", "share_year", "in_ros_price_file", "flags"]]
zs.to_csv(OUT / "zone_spine.csv", index=False)
for v in (2011, 2022):
    z = zs[zs.vintage == v]
    QA[f"spine_{v}_rows"] = len(z)
    QA[f"spine_{v}_population_total"] = int(z.population.sum()); QA[f"spine_{v}_households_total"] = int(z.households.sum()); QA[f"spine_{v}_dwellings_total"] = int(z.dwellings.sum())
    QA[f"spine_{v}_nulls"] = {c: int(z[c].isna().sum()) for c in ["iz_code", "la_code", "population", "households", "dwellings"]}
    QA[f"spine_{v}_flag_counts"] = z["flags"].str.split(";").explode().replace("", np.nan).dropna().value_counts().to_dict()

# ---------------------------------------------------------------- SIMD
simd = pd.DataFrame({
    "code": simd_lk.DZ, "vintage": 2011,
    "simd_rank": simd_lk.SIMD2020v2_Rank, "simd_vigintile": simd_lk.SIMD2020v2_Vigintile,
    "simd_decile": simd_lk.SIMD2020v2_Decile, "simd_quintile": simd_lk.SIMD2020v2_Quintile,
    "income_rank": simd_lk.SIMD2020v2_Income_Domain_Rank, "employment_rank": simd_lk.SIMD2020_Employment_Domain_Rank,
    "education_rank": simd_lk.SIMD2020_Education_Domain_Rank, "health_rank": simd_lk.SIMD2020_Health_Domain_Rank,
    "access_rank": simd_lk.SIMD2020_Access_Domain_Rank, "crime_rank": simd_lk.SIMD2020_Crime_Domain_Rank,
    "housing_rank": simd_lk.SIMD2020_Housing_Domain_Rank,
    "simd_population_2017": simd_lk.Population, "simd_working_age_population_2017": simd_lk.Working_Age_Population,
}).sort_values("code")
for c in ["simd_rank", "simd_vigintile", "simd_decile", "simd_quintile", "simd_population_2017", "simd_working_age_population_2017"]:
    simd[c] = pd.to_numeric(simd[c], errors="coerce").astype("Int64")
# domain ranks keep official tied half-ranks (e.g. 5955.5), so they stay numeric
QA["simd_domain_half_ranks"] = {c: int((simd[c] % 1 != 0).sum()) for c in ["income_rank", "employment_rank", "education_rank", "health_rank", "access_rank", "crime_rank", "housing_rank"]}
QA["simd_null_cells"] = {c: int(n) for c, n in simd.isna().sum().items() if n}
rk = pd.read_excel(RAW / "SIMD_2020v2_ranks.xlsx", sheet_name="SIMD 2020v2 ranks", dtype={"Data_Zone": str}).set_index("Data_Zone")
chk = simd.set_index("code")
pairs = {"simd_rank": "SIMD2020v2_Rank", "income_rank": "SIMD2020v2_Income_Domain_Rank", "employment_rank": "SIMD2020_Employment_Domain_Rank",
         "education_rank": "SIMD2020_Education_Domain_Rank", "health_rank": "SIMD2020_Health_Domain_Rank", "access_rank": "SIMD2020_Access_Domain_Rank",
         "crime_rank": "SIMD2020_Crime_Domain_Rank", "housing_rank": "SIMD2020_Housing_Domain_Rank"}
QA["simd_rank_mismatch_lookup_vs_ranks_file"] = {a: int((chk[a] != rk[b].reindex(chk.index)).sum()) for a, b in pairs.items()}
QA["simd_rank_is_permutation_1_6976"] = bool(sorted(simd.simd_rank) == list(range(1, 6977)))
# deciles consistent with ranks (decile counts)
QA["simd_decile_counts"] = {str(k): int(v) for k, v in simd.simd_decile.value_counts().sort_index().items()}
QA["simd_quintile_counts"] = {str(k): int(v) for k, v in simd.simd_quintile.value_counts().sort_index().items()}
simd.to_csv(OUT / "simd2020v2_dz2011.csv", index=False)

m = cw[main][["dz2011", "dz2022", "reverse_weight"]].merge(simd[["code", "simd_decile", "simd_quintile"]], left_on="dz2011", right_on="code")
dec = m.pivot_table(index="dz2022", columns="simd_decile", values="reverse_weight", aggfunc="sum", fill_value=0).reindex(columns=range(1, 11), fill_value=0)
qui = m.pivot_table(index="dz2022", columns="simd_quintile", values="reverse_weight", aggfunc="sum", fill_value=0).reindex(columns=range(1, 6), fill_value=0)
dec.columns = [f"decile_{c}_share" for c in dec.columns]; qui.columns = [f"quintile_{c}_share" for c in qui.columns]
s22 = pd.concat([dec, qui], axis=1).reindex(DZ22)
s22.index.name = "code"; s22 = s22.reset_index(); s22.insert(1, "vintage", 2022)
s22["modal_decile"] = dec.reindex(DZ22).values.argmax(axis=1) + 1
s22["modal_decile_share"] = dec.reindex(DZ22).values.max(axis=1)
s22["n_dz2011_sources"] = s22.code.map(n11_per22).astype(int)
s22["method"] = "crosswalk_pop_hhres_2022_reverse_weight"
QA["simd22_rows"] = len(s22)
QA["simd22_max_dev_decile_sum"] = float((s22[[f"decile_{i}_share" for i in range(1, 11)]].sum(axis=1) - 1).abs().max())
QA["simd22_max_dev_quintile_sum"] = float((s22[[f"quintile_{i}_share" for i in range(1, 6)]].sum(axis=1) - 1).abs().max())
QA["simd22_zones_single_decile_(share>=0.999)"] = int((s22.modal_decile_share >= 0.999).sum())
s22.to_csv(OUT / "simd2020v2_on_dz2022.csv", index=False, float_format="%.15g")

# ---------------------------------------------------------------- SIMD 2020v2 access-domain indicators (raw minutes), DZ2011 only
ind = pd.read_excel(RAW / "SIMD_2020v2_indicators.xlsx", sheet_name="Data", dtype={"Data_Zone": str})
ind = ind[ind.Data_Zone.str.match(CODE_RE, na=False)]
ACC = ["drive_petrol", "drive_GP", "drive_post", "drive_primary", "drive_retail", "drive_secondary", "PT_GP", "PT_post", "PT_retail"]
acc = pd.DataFrame({"code": ind.Data_Zone.values, "vintage": 2011})
for c in ACC:
    acc[c] = pd.to_numeric(ind[c].values, errors="raise")
bb_raw = ind["Broadband"].values
acc["broadband"] = pd.to_numeric(pd.Series(bb_raw).replace("*", np.nan), errors="raise").values   # proportion 0-1 of premises without superfast broadband
acc["flags"] = np.where(pd.Series(bb_raw).astype(str).eq("*"), "dz2011_only_not_crosswalked;broadband_suppressed_in_source", "dz2011_only_not_crosswalked")
acc = acc.sort_values("code")
assert len(acc) == 6976 and set(acc.code) == set(DZ11) and acc.code.is_unique
QA["access_rows"] = len(acc)
QA["access_codes_in_spine"] = int(acc.code.isin(zs[zs.vintage == 2011].code).sum())
QA["access_nulls"] = {c: int(acc[c].isna().sum()) for c in ACC + ["broadband"]}
QA["access_broadband_suppressed_codes"] = acc.loc[acc.broadband.isna(), "code"].tolist()
QA["access_minutes_range"] = {c: [round(float(acc[c].min()), 3), round(float(acc[c].max()), 3)] for c in ACC}
QA["access_broadband_range"] = [float(acc.broadband.min()), float(acc.broadband.max())]
acc.to_csv(OUT / "simd2020v2_access_indicators_dz2011.csv", index=False, float_format="%.15g")

# ---------------------------------------------------------------- CT bands A-H (all years)
BANDS = list("ABCDEFGH")
def ct_from(path, years, vintage):
    out = []
    for y in years:
        t = xlsx_table(path, str(y), "Data Zone code")
        bc = {b: next(c for c in t.columns if re.fullmatch(rf"Council Tax band: ?{b}", c)) for b in BANDS}
        d = pd.DataFrame({"code": t.iloc[:, 0], "vintage": vintage, "year": y})
        for b in BANDS:
            d[f"band_{b.lower()}"] = num(t[bc[b]]).astype("Int64")
        d["total_dwellings"] = num(t["Total number of dwellings"]).astype("Int64")
        out.append(d)
    return pd.concat(out, ignore_index=True)
ct11 = ct_from(RAW / "dwellings-estimate-by-2011-data-zones.xlsx", range(2005, 2026), 2011)
ct22 = ct_from(RAW / "dwelling-estimates-by-2022-data-zones-24-25.xlsx", [2024, 2025], 2022)
ct = pd.concat([ct11, ct22], ignore_index=True)
assert not ct.duplicated(["code", "vintage", "year"]).any()
bsum = ct[[f"band_{b.lower()}" for b in BANDS]].sum(axis=1)
QA["ct_rows"] = len(ct); QA["ct_rows_by_vintage_year"] = ct.groupby(["vintage"]).year.agg(["min", "max", "count"]).to_dict("index")
QA["ct_rows_band_sum_ne_total"] = int((bsum != ct.total_dwellings).sum())
QA["ct_band_sum_ne_total_max_abs"] = int((bsum - ct.total_dwellings).abs().max())
QA["ct_codes_per_vintage_year_min_max"] = ct.groupby(["vintage", "year"]).code.nunique().agg(["min", "max"]).to_dict()
# reconcile with data.gov.scot grouped "Summary" datasets
def recon(path, vintage, gtype):
    s = pd.read_csv(path, dtype=str)
    s = s[s.GeographyType == gtype]
    s["Value"] = pd.to_numeric(s.Value)
    p = s.pivot_table(index=["GeographyCode", "DateCode"], columns="Council Tax Band", values="Value", aggfunc="first").reset_index()
    p["year"] = p.DateCode.astype(int)
    c = ct[ct.vintage == vintage].copy()
    c["AC"] = c.band_a + c.band_b + c.band_c; c["DE"] = c.band_d + c.band_e; c["FH"] = c.band_f + c.band_g + c.band_h
    j = c.merge(p, left_on=["code", "year"], right_on=["GeographyCode", "year"], how="inner")
    r = {"matched_rows": len(j), "years": sorted(j.year.unique().tolist())}
    for a, b in [("AC", "Bands A-C"), ("DE", "Bands D-E"), ("FH", "Bands F-H"), ("total_dwellings", "Total Dwellings")]:
        r[f"mismatch_{a}"] = int((j[a].astype(float) != j[b]).sum())
    return r
QA["ct_recon_vs_dgs_summary_2022dz"] = recon(RAW / "dgs_ct_band_2022dz.csv", 2022, "2022 Data Zones")
QA["ct_recon_vs_dgs_summary_cgb_2011dz"] = recon(RAW / "dgs_ct_band_cgb_2011dz.csv", 2011, "2011 Data Zones")
ct.rename(columns={"year": "count_year"}).to_csv(OUT / "dwellings_ct_band.csv", index=False)

# ---------------------------------------------------------------- dwelling mix fallback (DZ2011, 2014-2017)
def dgs_long(path, cat, keep):
    s = pd.read_csv(path, dtype=str)
    s = s[(s.GeographyType == "2011 Data Zones") & (s.Measurement == "Count")]
    s["Value"] = pd.to_numeric(s.Value)
    p = s.pivot_table(index=["GeographyCode", "DateCode"], columns=cat, values="Value", aggfunc="first").reset_index()
    return p.rename(columns=keep)
ty = dgs_long(RAW / "dgs_dwellings_by_type.csv", "Type Of Dwelling",
              {"All": "type_all", "Detached": "type_detached", "Semi-Detached": "type_semi_detached", "Terraced": "type_terraced", "Flats": "type_flat", "Unknown": "type_unknown"})
ro = dgs_long(RAW / "dgs_dwellings_by_rooms.csv", "Number Of Rooms", {**{str(i): f"rooms_{i}" for i in range(1, 10)}, "10+": "rooms_10_plus", "Unknown": "rooms_unknown"})
mix = ty.merge(ro, on=["GeographyCode", "DateCode"], how="outer").rename(columns={"GeographyCode": "code", "DateCode": "year"})
mix["year"] = mix.year.astype(int); mix.insert(1, "vintage", 2011)
cols = ["type_all", "type_detached", "type_semi_detached", "type_terraced", "type_flat", "type_unknown"] + [f"rooms_{i}" for i in range(1, 10)] + ["rooms_10_plus", "rooms_unknown"]
for c in cols:
    mix[c] = mix[c].astype("Int64")
mix["status"] = "historic_fallback_dz2011_only"
mix = mix[["code", "vintage", "year"] + cols + ["status"]].sort_values(["year", "code"])
QA["mix_rows"] = len(mix); QA["mix_codes_per_year"] = mix.groupby("year").code.nunique().to_dict()
QA["mix_type_parts_ne_all"] = int((mix[cols[1:6]].sum(axis=1) != mix.type_all).sum())
QA["mix_rooms_sum_ne_type_all"] = int((mix[cols[6:]].sum(axis=1) != mix.type_all).sum())
# cross-check 2017 vs NRS xlsx 2017 sheet
x = xlsx_table(RAW / "dwellings-estimate-by-2011-data-zones.xlsx", "2017", "Data Zone code").set_index("Data Zone code")
m17 = mix[mix.year == 2017].set_index("code")
xc = {"type_detached": "Type of dwelling: Detached", "type_semi_detached": "Type of dwelling: Semidetached", "type_terraced": "Type of dwelling: Terraced",
      "type_flat": "Type of dwelling: Flat", "type_unknown": "Type of dwelling: Unknown", "rooms_1": "Number of rooms in dwelling: 1", "rooms_unknown": "Number of rooms in dwelling: Unknown"}
QA["mix_2017_mismatch_vs_nrs_xlsx"] = {a: int((m17[a].astype(float) != num(x[b]).reindex(m17.index)).sum()) for a, b in xc.items()}
seven = m17[["rooms_7", "rooms_8", "rooms_9", "rooms_10_plus"]].sum(axis=1)
QA["mix_2017_mismatch_vs_nrs_xlsx"]["rooms_7_plus"] = int((seven.astype(float) != num(x["Number of rooms in dwelling: 7+"]).reindex(m17.index)).sum())
mix.rename(columns={"year": "count_year"}).to_csv(OUT / "nrs_dwelling_mix_2011_fallback.csv", index=False)

# misc QA facts
QA["sape_2011dz_mid2022_scotland"] = QA["spine_2011_population_total"]
QA["simd_lookup_la_codes_sample"] = sorted(simd_lk.LAcode.unique().tolist())[:40]
json.dump(QA, open(OUT / "qa_results.json", "w"), indent=2, default=str)

# ---------------------------------------------------------------- dwellings by year (long) - NRS council-tax household & dwelling estimates
HHCOLS = {"Total number of dwellings": "dwellings_total", "Occupied dwellings": "occupied", "Vacant dwellings": "vacant",
          "Second homes": "second_homes", "Long-term empty dwellings": "long_term_empty",
          "Unoccupied dwellings exempt from paying Council Tax": "unoccupied_exempt", "Occupied dwellings exempt from paying Council Tax": "occupied_exempt",
          "Dwellings with a 'single adult' Council Tax discount": "single_adult_discount"}
HH_SRC = {2011: "household-estimates-by-2011-data-zones.xlsx", 2022: "household-estimates-by-2022-data-zones-24-25.xlsx"}
HH_YEARS = {2011: list(range(2014, 2026)), 2022: [2024, 2025]}
def hh_years(vintage):
    out = []
    for y in HH_YEARS[vintage]:
        t = xlsx_table(RAW / HH_SRC[vintage], str(y), "Data Zone code")
        d = pd.DataFrame({"code": t.iloc[:, 0], "vintage": vintage, "year": y})
        for src, dst in HHCOLS.items():
            col = next(c for c in t.columns if re.sub(r"\s*\[Note \d+\]", "", c).strip() == src)
            d[dst] = num(t[col]).astype("Int64")
        d["source_file"] = HH_SRC[vintage]; d["source_sheet"] = str(y)
        out.append(d)
    return pd.concat(out, ignore_index=True)
hhy = pd.concat([hh_years(2011), hh_years(2022)], ignore_index=True)
assert not hhy.duplicated(["code", "vintage", "year"]).any()
grid = pd.concat([pd.MultiIndex.from_product([DZ11, [2011], HH_YEARS[2011]], names=["code", "vintage", "year"]).to_frame(index=False),
                  pd.MultiIndex.from_product([DZ22, [2022], HH_YEARS[2022]], names=["code", "vintage", "year"]).to_frame(index=False)], ignore_index=True)
dwy = ct[["code", "vintage", "year", "total_dwellings"]].rename(columns={"total_dwellings": "assessor_dwellings_dec"})
dby = grid.merge(hhy, on=["code", "vintage", "year"], how="left").merge(dwy, on=["code", "vintage", "year"], how="left")
with np.errstate(divide="ignore", invalid="ignore"):
    tot = dby.dwellings_total.astype(float)
    dby["vacant_share"] = (dby.vacant.astype(float) / tot).where(tot > 0).round(6)
    dby["second_home_share"] = (dby.second_homes.astype(float) / tot).where(tot > 0).round(6)
def dflags(r):
    f = []
    if pd.isna(r.dwellings_total): f.append("ctax_estimates_missing_for_zone_year")
    if pd.isna(r.assessor_dwellings_dec): f.append("assessor_dwellings_missing_for_zone_year")
    if r.dwellings_total == 0: f.append("zero_dwellings")
    return ";".join(f)
dby["flags"] = dby.apply(dflags, axis=1).fillna("").astype(str)   # always a string; "" = no flags
dby = dby[["code", "vintage", "year", "dwellings_total", "occupied", "vacant", "second_homes", "long_term_empty", "unoccupied_exempt", "occupied_exempt",
           "single_adult_discount", "vacant_share", "second_home_share", "assessor_dwellings_dec", "source_file", "source_sheet", "flags"]]
dby.rename(columns={"year": "count_year"}).to_csv(OUT / "dwellings_by_year.csv", index=False)
QA["dby_rows"] = len(dby)
QA["dby_occupied_plus_vacant_plus_second_ne_total"] = int((dby.occupied + dby.vacant + dby.second_homes != dby.dwellings_total).sum())
QA["dby_flag_counts"] = dby["flags"].str.split(";").explode().replace("", np.nan).dropna().value_counts().to_dict()
QA["dby_2025_totals"] = {f"{v}": {c: int(dby[(dby.vintage == v) & (dby.year == 2025)][c].sum()) for c in ["dwellings_total", "occupied", "vacant", "second_homes", "assessor_dwellings_dec"]} for v in (2011, 2022)}
cov = []
for v, yrs in [(2011, range(2005, 2026)), (2022, range(2005, 2026))]:
    for y in yrs:
        cov.append({"vintage": v, "year": y,
                    "ctax_split_published": y in HH_YEARS[v], "ctax_source": f"{HH_SRC[v]} sheet '{y}'" if y in HH_YEARS[v] else "",
                    "assessor_ct_band_published": bool(((ct.vintage == v) & (ct.year == y)).any()),
                    "assessor_source": (f"dwellings-estimate-by-2011-data-zones.xlsx sheet '{y}'" if v == 2011 else f"dwelling-estimates-by-2022-data-zones-24-25.xlsx sheet '{y}'") if ((ct.vintage == v) & (ct.year == y)).any() else ""})
pd.DataFrame(cov).rename(columns={"year": "count_year"}).to_csv(OUT / "dwellings_by_year_coverage.csv", index=False)

# ---------------------------------------------------------------- planning authority lookup
park = pd.read_csv(PARK_OVERLAY, dtype={"code": str, "park_code": str})
park["vintage"] = park.vintage.astype(str).str.replace("DZ", "", regex=False).astype(int)  # GIS overlay: accepts 2011/2022 or legacy DZ2011/DZ2022
QA["park_overlay_rows"] = len(park)
for v in (2011, 2022):
    pv = park[park.vintage == v]
    QA[f"park_hh_totals_{v}"] = pv.groupby("park_code").hh_in_park.sum().to_dict()
assert QA["park_hh_totals_2011"] == {"S21000002": 6835, "S21000003": 8518} == QA["park_hh_totals_2022"]
QA["park_overlay_zones_not_in_spine"] = int((~park.set_index(["code", "vintage"]).index.isin(zs.set_index(["code", "vintage"]).index)).sum())
QA["zones_in_both_parks"] = int((park.groupby(["code", "vintage"]).park_code.nunique() > 1).sum())
LLT, CNP = "S21000002", "S21000003"
rows = []
sp_idx = zs.set_index(["code", "vintage"])
pg = {k: g for k, g in park.groupby(["code", "vintage"])}
for (code, v), r in sp_idx.iterrows():
    la, lan = r.la_code, r.la_name
    g = pg.get((code, v))
    park_share = 0.0
    if g is not None:
        for _, p in g.iterrows():
            sh = float(p.hh_share)
            park_share += sh
            if p.park_code == LLT:
                rows.append((code, v, LLT, p.park_name, LLT, p.park_name, sh, float(p.area_share), int(p.hh_in_park), int(p.hh_total),
                             "park_split_census2022_postcode_households" if sh < 0.9999 or float(p.area_share) < 0.9999 else "wholly_in_park",
                             "LLTNP is plan-making and deciding planning authority" + ("; area overlap but no Census 2022 household points in park" if sh == 0 else "")))
            else:
                rows.append((code, v, CNP, p.park_name, la, lan, sh, float(p.area_share), int(p.hh_in_park), int(p.hh_total),
                             "park_split_census2022_postcode_households" if sh < 0.9999 or float(p.area_share) < 0.9999 else "wholly_in_park",
                             "CNPA writes the Local Development Plan; host council decides most applications, CNPA calls in larger ones" + ("; area overlap but no Census 2022 household points in park" if sh == 0 else "")))
    rest = round(1.0 - park_share, 12)
    if rest > 1e-9 or g is None:
        hh_total = int(g.hh_total.iloc[0]) if g is not None else None
        rows.append((code, v, la, lan, la, lan, rest if g is not None else 1.0, None if g is None else max(0.0, 1.0 - float(g.area_share.sum())),
                     None if g is None else hh_total - int(g.hh_in_park.sum()), hh_total,
                     "council_outside_park" if g is None else "park_split_census2022_postcode_households", "council is plan-making and deciding authority"))
pa = pd.DataFrame(rows, columns=["code", "vintage", "plan_making_authority", "plan_making_authority_name", "deciding_authority", "deciding_authority_name",
                                 "share", "area_share", "hh_2022", "hh_2022_zone_total", "method", "note"])
pa["hh_2022"] = pa.hh_2022.astype("Int64"); pa["hh_2022_zone_total"] = pa.hh_2022_zone_total.astype("Int64")
assert not pa.duplicated(["code", "vintage", "plan_making_authority"]).any()
ssum = pa.groupby(["code", "vintage"]).share.sum()
QA["pa_rows"] = len(pa); QA["pa_zones"] = int(len(ssum)); QA["pa_max_dev_share_sum"] = float((ssum - 1).abs().max())
assert QA["pa_max_dev_share_sum"] < 1e-9 and len(ssum) == 6976 + 7392
QA["pa_method_counts"] = {f"{k[0]}:{k[1]}": int(n) for k, n in pa.groupby(["vintage", "method"]).size().items()}
QA["pa_park_hh_check"] = {f"{v}": pa[(pa.vintage == v) & pa.plan_making_authority.isin([LLT, CNP])].groupby("plan_making_authority").hh_2022.sum().astype(int).to_dict() for v in (2011, 2022)}
QA["pa_distinct_plan_making_authorities"] = {f"{v}": int(pa[pa.vintage == v].plan_making_authority.nunique()) for v in (2011, 2022)}
pa.to_csv(OUT / "dz_planning_authority.csv", index=False, float_format="%.15g")

json.dump(QA, open(OUT / "qa_results.json", "w"), indent=2, default=str)
print("DONE")
