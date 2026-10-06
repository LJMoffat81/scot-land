"""epc_dz_rollup: latest domestic EPC per property (SEPCR BUILDING_REFERENCE_NUMBER), joined to DZ2011/DZ2022 via NRS SPD postcode."""
import duckdb, pandas as pd, numpy as np, json, sys
sys.path.insert(0,'/workspace/scotland-gis/scripts')
from zone_rules import check_codes, dwellings_2025, dwellings_flag, DW_SOURCE, VINT
from pathlib import Path
W=Path('/workspace/scotland-gis/work'); O=Path('/workspace/scotland-gis/out')
con=duckdb.connect(str(W/'epc.duckdb')); con.execute("SET threads=6; SET memory_limit='5GB'")
con.execute("DELETE FROM hist WHERE BUILDING_REFERENCE_NUMBER='Property_UPRN'")
qa={}
qa['raw_rows']=con.execute("select count(*) from hist").fetchone()[0]
qa['raw_rows_rejected_by_parser']=6
# --- latest certificate per property ---
con.execute("""CREATE OR REPLACE TABLE latest AS
SELECT * EXCLUDE rn FROM (
  SELECT *, row_number() OVER (PARTITION BY BUILDING_REFERENCE_NUMBER
     ORDER BY (HISTORIC='False') DESC, try_cast(LODGEMENT_DATE AS DATE) DESC NULLS LAST,
              try_cast(INSPECTION_DATE AS DATE) DESC NULLS LAST, REPORT_REFERENCE_NUMBER DESC NULLS LAST,
              -- deterministic final tie-break: RRN is blank on tied rows and exact ties exist (e.g. BRN 1000022660)
              POSTCODE, PROPERTY_TYPE, BUILT_FORM, CONSTRUCTION_AGE_BAND, TOTAL_FLOOR_AREA) rn
  FROM hist) WHERE rn=1""")
qa['properties_latest_cert']=con.execute("select count(*) from latest").fetchone()[0]
# normalised postcode
con.execute("""ALTER TABLE latest ADD COLUMN pc VARCHAR;
UPDATE latest SET pc = CASE WHEN length(regexp_replace(upper(coalesce(POSTCODE,'')),'[^A-Z0-9]','','g')) BETWEEN 5 AND 7
  THEN substr(regexp_replace(upper(POSTCODE),'[^A-Z0-9]','','g'),1,length(regexp_replace(upper(POSTCODE),'[^A-Z0-9]','','g'))-3)||' '||right(regexp_replace(upper(POSTCODE),'[^A-Z0-9]','','g'),3) END""")
# --- SPD postcode lookup (one row per base postcode) ---
spd=pd.read_parquet(W/'spd.parquet')
spd['base']=np.where(spd.SplitIndicator=='Y',spd.Postcode.str[:-1],spd.Postcode).astype(str)
spd['live']=spd.DateOfDeletion.isna()
spd['intro']=pd.to_datetime(spd.DateOfIntroduction,format='%d/%m/%Y %H:%M:%S',errors='coerce')
spd['hh']=spd.CensusHouseholdCount2022.fillna(0)
# split parts: choose the part with most 2022 households (NRS 'A' part = most delivery points) ; among duplicate records prefer live, then latest introduced
spd=spd.sort_values(['base','live','hh','intro'],ascending=[True,False,False,False])
multi=spd.groupby('base').agg(n11=('DataZone2011Code','nunique'),n22=('DataZone2022Code','nunique'),split=('SplitIndicator',lambda s:(s=='Y').any()))
lk=spd.drop_duplicates('base')[['base','DataZone2011Code','DataZone2022Code','live']]
lk=lk.merge(multi,left_on='base',right_index=True)
con.register('lk_df',lk); con.execute("CREATE OR REPLACE TABLE lk AS SELECT * FROM lk_df")
con.execute("""CREATE OR REPLACE TABLE j AS SELECT l.*, k.DataZone2011Code dz11, k.DataZone2022Code dz22, k.live pc_live,
   (k.n11>1) amb11, (k.n22>1) amb22 FROM latest l LEFT JOIN lk k ON l.pc=k.base""")
r=con.execute("""select count(*) n, sum((pc is null)::int) bad_pc, sum((dz22 is null)::int) unmatched,
   sum((dz22 is null and pc is not null)::int) unmatched_valid_format,
   sum((dz22 is not null and not pc_live)::int) matched_to_deleted_pc,
   sum((amb11)::int) amb11, sum((amb22)::int) amb22,
   sum((dz22 is null and DATA_ZONE_2011 is not null)::int) unmatched_with_epc_dz11
   from j""").df().iloc[0].to_dict()
qa.update({k:int(v) for k,v in r.items()})
qa['unmatched_postcode_rate_pct']=round(100*qa['unmatched']/qa['n'],3)
# QA: agreement of postcode-derived DZ2011 with the EPC's own DATA_ZONE_2011 field
a=con.execute("""select count(*) n, sum((dz11=split_part(DATA_ZONE_2011,' ',1))::int) agree from j where dz11 is not null and DATA_ZONE_2011 like 'S01%'""").fetchone()
qa['dz11_agreement_with_EPC_DATA_ZONE_2011_pct']=round(100*a[1]/a[0],2); qa['dz11_agreement_base_n']=int(a[0])
# --- features ---
d=con.execute("""select dz11, dz22, PROPERTY_TYPE pt, BUILT_FORM bf, CONSTRUCTION_AGE_BAND ab,
   case when try_cast(TOTAL_FLOOR_AREA as double) between 10 and 1500 then try_cast(TOTAL_FLOOR_AREA as double) end tfa,
   try_cast(LODGEMENT_DATE as date) ld from j where dz22 is not null""").df()
PT={'House':'house','Flat':'flat','Bungalow':'bungalow','Maisonette':'maisonette','Park home':'park_home'}
BF={'Detached':'detached','Semi-Detached':'semi_detached','Mid-Terrace':'mid_terrace','End-Terrace':'end_terrace','Enclosed Mid-Terrace':'enclosed_mid_terrace','Enclosed End-Terrace':'enclosed_end_terrace'}
AB={'before 1919':'pre1919','1919-1929':'1919_1929','1930-1949':'1930_1949','1950-1964':'1950_1964','1965-1975':'1965_1975','1976-1983':'1976_1983','1984-1991':'1984_1991','1992-1998':'1992_1998','1999-2002':'1999_2002','2003-2007':'2003_2007','2008 onwards':'2008_on'}
d['pt']=d.pt.map(PT).fillna('unknown'); d['bf']=d.bf.map(BF).fillna('unknown'); d['ab']=d.ab.map(AB).fillna('unknown')
cut=pd.Timestamp('2026-07-01')-pd.DateOffset(years=10)
d['recent']=pd.to_datetime(d.ld)>=cut
qa['tfa_valid_pct']=round(100*d.tfa.notna().mean(),2)
DW=dwellings_2025()  # team rule: Data Zones dwellings_total, count_year 2025, same vintage; never filled from another year
dw={v:DW[DW.vintage==VINT[v]].set_index('code').dwellings_total for v in ['DZ2011','DZ2022']}
import geopandas as gpd
allz={'DZ2011':gpd.read_file('/workspace/scotland-gis/raw/SG_DataZoneBdry_2011/SG_DataZone_Bdry_2011.shp',ignore_geometry=True).DataZone,
      'DZ2022':gpd.read_file('/workspace/scotland-gis/raw/SG_DataZoneBdry_2022/SG_DataZone_Bdry_2022.shp',ignore_geometry=True).dzcode}
out=[]
for v,col in [('DZ2011','dz11'),('DZ2022','dz22')]:
    g=d.groupby(col)
    t=pd.DataFrame({'cert_count':g.size()})
    for name,mp,pref in [('pt',PT,'pt_'),('bf',BF,'bf_'),('ab',AB,'age_')]:
        cats=list(mp.values())+['unknown']
        ct=pd.crosstab(d[col],d[name]).reindex(columns=cats,fill_value=0)
        sh=ct.div(ct.sum(axis=1),axis=0); sh.columns=[pref+c+'_share' for c in cats]
        t=t.join(sh)
    t['tfa_n']=g.tfa.count()
    t['tfa_median_m2']=g.tfa.median(); t['tfa_q1_m2']=g.tfa.quantile(.25); t['tfa_q3_m2']=g.tfa.quantile(.75)
    t['tfa_iqr_m2']=t.tfa_q3_m2-t.tfa_q1_m2
    t['share_lodged_last_10y']=g.recent.mean()
    t=t.reindex(allz[v]); t.index.name='code'
    t['cert_count']=t.cert_count.fillna(0).astype(int)
    t['dwellings_total_2025']=dw[v].reindex(t.index).astype('Int64')
    t['dwellings_flag']=dwellings_flag(t.dwellings_total_2025)
    t['dwellings_source']=DW_SOURCE
    t['coverage_share']=np.where(t.dwellings_total_2025.fillna(0)>0,t.cert_count/t.dwellings_total_2025.astype(float),np.nan)
    sup=t.cert_count<5
    stat_cols=[c for c in t.columns if c.endswith('_share') and c!='coverage_share']+['tfa_median_m2','tfa_q1_m2','tfa_q3_m2','tfa_iqr_m2','share_lodged_last_10y','tfa_n']
    t.loc[sup,stat_cols]=np.nan
    tsup=(~sup)&(t.tfa_n<5); t.loc[tsup,['tfa_median_m2','tfa_q1_m2','tfa_q3_m2','tfa_iqr_m2']]=np.nan
    t['suppressed']=sup
    t.loc[sup,'cert_count']=np.nan; t.loc[sup,'coverage_share']=np.nan
    t['vintage']=VINT[v]
    qa[f'{v}_zones_flagged_missing_count_2025']=sorted(t.index[t.dwellings_flag=='missing_count_2025'])
    qa[f'{v}_zones_flagged_zero_dwellings_2025']=sorted(t.index[t.dwellings_flag=='zero_dwellings_2025'])
    qa[f'{v}_zones']=len(t); qa[f'{v}_zones_suppressed_lt5']=int(sup.sum())
    qa[f'{v}_zones_zero_certs']=int((d.groupby(col).size().reindex(allz[v]).fillna(0)==0).sum())
    qa[f'{v}_certs_assigned']=int(g.size().sum())
    qa[f'{v}_codes_not_in_boundary_file']=sorted(set(d[col])-set(allz[v]))
    cs=t.coverage_share.dropna()
    qa[f'{v}_coverage_share_quantiles']={k:round(float(cs.quantile(k)),3) for k in [0,.05,.25,.5,.75,.95,1]}
    qa[f'{v}_zones_coverage_gt1']=int((cs>1).sum()); qa[f'{v}_zones_coverage_gt1.2']=int((cs>1.2).sum())
    qa[f'{v}_national_coverage']=round(t.cert_count.sum()/t.dwellings_total_2025.sum(),4)
    qa[f'{v}_dwellings_total_2025_sum']=int(t.dwellings_total_2025.sum())
    qa[f'{v}_zones_dwellings_zero']=int((t.dwellings_total_2025==0).sum())
    for pref in ['pt_','bf_','age_']:
        s=t[[c for c in t.columns if c.startswith(pref)]].sum(axis=1)[~sup]; qa[f'{v}_{pref}shares_max_sum_err']=float((s-1).abs().max())
    out.append(t.reset_index())
R=pd.concat(out)
front=['code','vintage','cert_count','dwellings_total_2025','dwellings_flag','coverage_share','suppressed']
R=R[front+[c for c in R.columns if c not in front+['dwellings_source']]+['dwellings_source']]
R['vintage']=R.vintage.astype(int); check_codes(R)
R['cert_count']=R.cert_count.astype('Int64'); R['tfa_n']=R.tfa_n.astype('Int64')
R.to_csv(O/'epc_dz_rollup.csv',index=False,float_format='%.6g')
qa['rows']=len(R)
json.dump(qa,open(O/'qa_epc.json','w'),indent=1,default=str)
print(json.dumps(qa,indent=1,default=str))
