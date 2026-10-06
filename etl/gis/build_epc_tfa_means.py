"""Step 3 of epc_dz_rollup: mean / sum of floor area (10-1500 m2), plus house vs flat means, for all-time (latest cert) and recent10 sets.
Reads tables j (step 1) and jr (step 2) from work/epc.duckdb."""
import duckdb, pandas as pd, numpy as np, json, sys
sys.path.insert(0,'/workspace/scotland-gis/scripts')
from zone_rules import check_codes, VINT
from pathlib import Path
W=Path('/workspace/scotland-gis/work'); O=Path('/workspace/scotland-gis/out')
con=duckdb.connect(str(W/'epc.duckdb'),read_only=True)
base=pd.read_csv(O/'epc_dz_rollup.csv',dtype={'code':str})
NEW_SUFFIX=('tfa_mean_m2','tfa_sum_m2','tfa_mean_house_m2','tfa_n_house','tfa_mean_flat_m2','tfa_n_flat')
base=base[[c for c in base.columns if not any(c in (s,'recent10_'+s) for s in NEW_SUFFIX)]]
qa={}
GROUP={'House':'house','Bungalow':'house','Flat':'flat','Maisonette':'flat'}
parts={}
for tag,tbl,pref in [('all','j',''),('recent10','jr','recent10_')]:
    d=con.execute(f"""select dz11, dz22, PROPERTY_TYPE pt,
        case when try_cast(TOTAL_FLOOR_AREA as double) between 10 and 1500 then try_cast(TOTAL_FLOOR_AREA as double) end tfa
        from {tbl} where dz22 is not null""").df()
    d['grp']=d.pt.map(GROUP)
    out=[]
    for v,col in [('DZ2011','dz11'),('DZ2022','dz22')]:
        g=d.dropna(subset=['tfa']).groupby(col).tfa
        t=pd.DataFrame({'tfa_mean_m2':g.mean(),'tfa_sum_m2':g.sum(),'_n':g.count()})
        for grp in ['house','flat']:
            gg=d[(d.grp==grp)&d.tfa.notna()].groupby(col).tfa
            t[f'tfa_n_{grp}']=gg.count(); t[f'tfa_mean_{grp}_m2']=gg.mean()
        t=t.reindex(base.loc[base.vintage==VINT[v],'code'].values); t.index.name='code'
        for grp in ['house','flat']:
            t[f'tfa_n_{grp}']=t[f'tfa_n_{grp}'].fillna(0)
            t.loc[t[f'tfa_n_{grp}']<5,f'tfa_mean_{grp}_m2']=np.nan
        b=base[base.vintage==VINT[v]].set_index('code')
        # consistency with existing tfa_n (count of certs with valid floor area)
        chk=b[pref+'tfa_n'].dropna()
        qa[f'{tag}_{v}_tfa_n_matches_existing']=bool((t._n.reindex(chk.index).fillna(0).astype(int)==chk.astype(int)).all())
        sup=b[pref+'suppressed'].astype(bool) | (t._n.fillna(0)<5)
        t.loc[sup,['tfa_mean_m2','tfa_sum_m2','tfa_mean_house_m2','tfa_mean_flat_m2']]=np.nan
        t.loc[b[pref+'suppressed'].astype(bool),['tfa_n_house','tfa_n_flat']]=np.nan
        qa[f'{tag}_{v}_zones_mean_blank']=int(t.tfa_mean_m2.isna().sum())
        qa[f'{tag}_{v}_house_mean_present']=int(t.tfa_mean_house_m2.notna().sum()); qa[f'{tag}_{v}_flat_mean_present']=int(t.tfa_mean_flat_m2.notna().sum())
        qa[f'{tag}_{v}_national_mean_m2']=round(float(t.tfa_sum_m2.sum()/t._n[~sup].sum()),2)
        qa[f'{tag}_{v}_median_of_zone_means_m2']=round(float(t.tfa_mean_m2.median()),2)
        qa[f'{tag}_{v}_mean_minus_median_median_m2']=round(float((t.tfa_mean_m2-b[pref+'tfa_median_m2']).median()),2)
        m=t.tfa_mean_m2.notna(); qa[f'{tag}_{v}_sum_equals_mean_x_n_maxerr']=float((t.tfa_sum_m2[m]-t.tfa_mean_m2[m]*t._n[m]).abs().max())
        t=t.drop(columns='_n')
        t.columns=[pref+c for c in t.columns]; t['vintage']=VINT[v]; out.append(t.reset_index())
    parts[tag]=pd.concat(out)
res=base.merge(parts['all'],on=['code','vintage'],how='left',validate='1:1').merge(parts['recent10'],on=['code','vintage'],how='left',validate='1:1')
for c in res.columns:
    if c.endswith('tfa_n_house') or c.endswith('tfa_n_flat'): res[c]=res[c].astype('Int64')
for c in ['cert_count','tfa_n','recent10_cert_count','recent10_tfa_n','dwellings_total_2025']: res[c]=res[c].astype('Int64')
res=res[[c for c in res.columns if c!='dwellings_source']+['dwellings_source']]
assert len(res)==len(base)==14368
check_codes(res); assert not res.duplicated(['code','vintage']).any()
for c in ['tfa_sum_m2','recent10_tfa_sum_m2']: res[c]=res[c].map(lambda x: '' if pd.isna(x) else f'{x:.2f}')  # full precision for sums
res.to_csv(O/'epc_dz_rollup.csv',index=False,float_format='%.6g')
qa['rows']=len(res); qa['columns']=len(res.columns)
json.dump(qa,open(O/'qa_epc_tfa_means.json','w'),indent=1); print(json.dumps(qa,indent=1))
