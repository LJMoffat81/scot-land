"""Step 2 of epc_dz_rollup: append recent10_* columns built only from certificates lodged 1 Jul 2016 - 30 Jun 2026.
Latest certificate per property (BUILDING_REFERENCE_NUMBER) WITHIN the window. Same postcode->zone lookup (table lk from step 1)."""
import duckdb, pandas as pd, numpy as np, json, sys
sys.path.insert(0,'/workspace/scotland-gis/scripts')
from zone_rules import check_codes, VINT
from pathlib import Path
W=Path('/workspace/scotland-gis/work'); O=Path('/workspace/scotland-gis/out')
con=duckdb.connect(str(W/'epc.duckdb')); con.execute("SET threads=6; SET memory_limit='5GB'")
qa={'window':'LODGEMENT_DATE 2016-07-01..2026-06-30 inclusive'}
con.execute("""CREATE OR REPLACE TABLE latest_r AS
SELECT * EXCLUDE rn FROM (
  SELECT *, row_number() OVER (PARTITION BY BUILDING_REFERENCE_NUMBER
     ORDER BY try_cast(LODGEMENT_DATE AS DATE) DESC, (HISTORIC='False') DESC,
              try_cast(INSPECTION_DATE AS DATE) DESC NULLS LAST, REPORT_REFERENCE_NUMBER DESC NULLS LAST,
              -- deterministic final tie-break: RRN is blank on tied rows and exact ties exist (e.g. BRN 1000022660)
              POSTCODE, PROPERTY_TYPE, BUILT_FORM, CONSTRUCTION_AGE_BAND, TOTAL_FLOOR_AREA) rn
  FROM hist WHERE try_cast(LODGEMENT_DATE AS DATE) BETWEEN DATE '2016-07-01' AND DATE '2026-06-30') WHERE rn=1""")
qa['properties_with_cert_in_window']=con.execute("select count(*) from latest_r").fetchone()[0]
qa['hist_rows_outside_window_future_dated(>2026-06-30)']=con.execute("select count(*) from hist where try_cast(LODGEMENT_DATE as date)>DATE '2026-06-30'").fetchone()[0]
con.execute("""CREATE OR REPLACE TABLE jr AS SELECT l.*, k.DataZone2011Code dz11, k.DataZone2022Code dz22 FROM
 (SELECT *, CASE WHEN length(regexp_replace(upper(coalesce(POSTCODE,'')),'[^A-Z0-9]','','g')) BETWEEN 5 AND 7
  THEN substr(regexp_replace(upper(POSTCODE),'[^A-Z0-9]','','g'),1,length(regexp_replace(upper(POSTCODE),'[^A-Z0-9]','','g'))-3)||' '||right(regexp_replace(upper(POSTCODE),'[^A-Z0-9]','','g'),3) END pc FROM latest_r) l
 LEFT JOIN lk k ON l.pc=k.base""")
n,un=con.execute("select count(*), sum((dz22 is null)::int) from jr").fetchone()
qa['unmatched']=int(un); qa['unmatched_postcode_rate_pct']=round(100*un/n,3)
# cross-check against the published 'valid EPC' file (table cur loaded during v1 QA)
try:
    qa['valid_file_properties']=con.execute("select count(distinct brn) from cur").fetchone()[0]
    qa['valid_file_properties_in_recent10']=con.execute("select count(distinct c.brn) from cur c join latest_r l on l.BUILDING_REFERENCE_NUMBER=c.brn").fetchone()[0]
except Exception as e: qa['valid_file_check']=str(e)
d=con.execute("""select dz11, dz22, PROPERTY_TYPE pt, BUILT_FORM bf, CONSTRUCTION_AGE_BAND ab,
   case when try_cast(TOTAL_FLOOR_AREA as double) between 10 and 1500 then try_cast(TOTAL_FLOOR_AREA as double) end tfa
   from jr where dz22 is not null""").df()
PT={'House':'house','Flat':'flat','Bungalow':'bungalow','Maisonette':'maisonette','Park home':'park_home'}
BF={'Detached':'detached','Semi-Detached':'semi_detached','Mid-Terrace':'mid_terrace','End-Terrace':'end_terrace','Enclosed Mid-Terrace':'enclosed_mid_terrace','Enclosed End-Terrace':'enclosed_end_terrace'}
AB={'before 1919':'pre1919','1919-1929':'1919_1929','1930-1949':'1930_1949','1950-1964':'1950_1964','1965-1975':'1965_1975','1976-1983':'1976_1983','1984-1991':'1984_1991','1992-1998':'1992_1998','1999-2002':'1999_2002','2003-2007':'2003_2007','2008 onwards':'2008_on'}
d['pt']=d.pt.map(PT).fillna('unknown'); d['bf']=d.bf.map(BF).fillna('unknown'); d['ab']=d.ab.map(AB).fillna('unknown')
qa['tfa_valid_pct']=round(100*d.tfa.notna().mean(),2)
base=pd.read_csv(O/'epc_dz_rollup.csv',dtype={'code':str})
base=base[[c for c in base.columns if not c.startswith('recent10_')]]
parts=[]
for v,col in [('DZ2011','dz11'),('DZ2022','dz22')]:
    g=d.groupby(col); t=pd.DataFrame({'cert_count':g.size()})
    for name,mp,pref in [('pt',PT,'pt_'),('bf',BF,'bf_'),('ab',AB,'age_')]:
        cats=list(mp.values())+['unknown']
        ct=pd.crosstab(d[col],d[name]).reindex(columns=cats,fill_value=0)
        sh=ct.div(ct.sum(axis=1),axis=0); sh.columns=[pref+c+'_share' for c in cats]; t=t.join(sh)
    t['tfa_n']=g.tfa.count(); t['tfa_median_m2']=g.tfa.median(); t['tfa_q1_m2']=g.tfa.quantile(.25); t['tfa_q3_m2']=g.tfa.quantile(.75)
    t['tfa_iqr_m2']=t.tfa_q3_m2-t.tfa_q1_m2
    codes=base.loc[base.vintage==VINT[v],'code']
    t=t.reindex(codes.values); t.index.name='code'
    t['cert_count']=t.cert_count.fillna(0)
    dw=base.loc[base.vintage==VINT[v]].set_index('code').dwellings_total_2025.astype(float)  # Data Zones count_year 2025; NaN stays NaN (flagged in step 1)
    t['coverage_share']=np.where(dw.reindex(t.index).fillna(0)>0,t.cert_count/dw.reindex(t.index),np.nan)
    sup=t.cert_count<5
    stat=[c for c in t.columns if c not in ('cert_count',)]
    t.loc[sup,stat]=np.nan; t.loc[sup,'cert_count']=np.nan
    t.loc[(~sup)&(t.tfa_n<5),['tfa_median_m2','tfa_q1_m2','tfa_q3_m2','tfa_iqr_m2']]=np.nan
    t['suppressed']=sup.values
    qa[f'{v}_zones_suppressed_lt5']=int(sup.sum()); qa[f'{v}_suppressed_codes']=sorted(t.index[sup])
    qa[f'{v}_certs_assigned']=int(g.size().sum())
    cs=t.coverage_share.dropna(); qa[f'{v}_recent10_coverage_quantiles']={k:round(float(cs.quantile(k)),3) for k in [0,.05,.25,.5,.75,.95,1]}
    qa[f'{v}_national_recent10_coverage']=round(float(t.cert_count.sum()/dw.sum()),4)
    for pref in ['pt_','bf_','age_']:
        s=t[[c for c in t.columns if c.startswith(pref)]].sum(axis=1)[~sup]; qa[f'{v}_{pref}max_sum_err']=float((s-1).abs().max())
    t.columns=['recent10_'+c for c in t.columns]; t['vintage']=VINT[v]
    parts.append(t.reset_index())
Rr=pd.concat(parts)
out=base.merge(Rr,on=['code','vintage'],how='left',validate='1:1')
assert len(out)==len(base)
out['dwellings_total_2025']=out.dwellings_total_2025.astype('Int64'); check_codes(out)
for c in ['recent10_cert_count','recent10_tfa_n']: out[c]=out[c].astype('Int64')
# move dwellings_source to the end
out=out[[c for c in out.columns if c!='dwellings_source']+['dwellings_source']]
out.to_csv(O/'epc_dz_rollup.csv',index=False,float_format='%.6g')
# shift diagnostics: recent10 vs all-time mix
for v in ['DZ2011','DZ2022']:
    o=out[(out.vintage==VINT[v])&(~out.recent10_suppressed.astype(bool))]
    qa[f'{v}_median_abs_diff_flat_share_recent_vs_all']=round(float((o.recent10_pt_flat_share-o.pt_flat_share).abs().median()),4)
    qa[f'{v}_median_abs_diff_tfa_median_recent_vs_all_m2']=round(float((o.recent10_tfa_median_m2-o.tfa_median_m2).abs().median()),2)
qa['rows']=len(out); qa['columns']=len(out.columns)
json.dump(qa,open(O/'qa_epc_recent10.json','w'),indent=1,default=str); print(json.dumps(qa,indent=1,default=str))
