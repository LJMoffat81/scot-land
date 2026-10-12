"""QA for the 6 Oct 2026 team-rule rebuild of GIS-owned files (staged copies)."""
import pandas as pd, numpy as np, json, sys, hashlib
sys.path.insert(0,'/workspace/scotland-gis/scripts')
from zone_rules import check_codes, NZONES
G='/workspace/scotland-gis/data/processed/gis/'
KEYS={'epc_dz_rollup.csv':['code','vintage'],'dz_brma_share.csv':['code','vintage','brma_id'],'dz_park_overlay.csv':['code','vintage','park_code'],
 'alt/dz_brma_share_oa2022.csv':['code','vintage','brma_id'],'alt/dz_brma_share_dwelling_bounds.csv':['code','vintage','brma_id'],'alt/dz_park_overlay_dwelling_bounds.csv':['code','vintage','park_code']}
qa={}
for f,k in KEYS.items():
    d=pd.read_csv(G+f,dtype={'code':str},low_memory=False)
    check_codes(d); assert not d.duplicated(k).any(), f
    r={'rows':len(d),'sha8':hashlib.sha256(open(G+f,'rb').read()).hexdigest()[:8],'vintage_dtype':str(d.vintage.dtype),'zones_by_vintage':d.groupby('vintage').code.nunique().to_dict(),'old_cols_present':[c for c in d.columns if 'nrs' in c]}
    if f in ('dz_brma_share.csv','alt/dz_brma_share_oa2022.csv'):
        r['zone_counts_complete']=r['zones_by_vintage']=={2011:6976,2022:7392}
        r['max_abs_sum_err']=float((d.groupby(['code','vintage']).household_share.sum()-1).abs().max())
    if f=='alt/dz_brma_share_dwelling_bounds.csv':
        r['max_abs_sum_err_share_mid']=float((d.groupby(['code','vintage']).share_mid.sum()-1).abs().max())
        r['lower_le_hh_le_upper']=bool(((d.dwelling_share_lower<=d.household_share+1e-12)&(d.household_share<=d.dwelling_share_upper+1e-12)).all())
    if 'dwellings_flag' in d: r['dwellings_flag']=d.dwellings_flag.fillna('').value_counts().to_dict(); r['flagged']=d.loc[d.dwellings_flag.notna(),['code','vintage','dwellings_flag']].drop_duplicates().values.tolist()
    if 'dwellings_total_2025' in d and f=='epc_dz_rollup.csv':
        for v,g in d.groupby('vintage'):
            r[f'{v}_dwellings_total_2025_sum']=int(g.dwellings_total_2025.sum())
            r[f'{v}_coverage_all']=round(g.cert_count.sum()/g.dwellings_total_2025.sum(),4)
            r[f'{v}_coverage_recent10']=round(g.recent10_cert_count.sum()/g.dwellings_total_2025.sum(),4)
        assert r['2011_dwellings_total_2025_sum']==2757376 and r['2022_dwellings_total_2025_sum']==2757323
        r['dwellings_source']=d.dwellings_source.unique().tolist()
    if f=='alt/dz_park_overlay_dwelling_bounds.csv':
        for (v,pc),g in d.groupby(['vintage','park_code']):
            dw=g.dwellings_total_2025.astype(float)
            r[f'{v}_{pc}_mid_pm_half']=[round(float((g.share_mid*dw).sum())),round(float((g.share_halfwidth*dw).sum()))]
            r[f'{v}_{pc}_bounds']=[round(float((g.dw_share_lower*dw).sum())),round(float((g.dw_share_upper*dw).sum()))]
    qa[f]=r
json.dump(qa,open(G+'qa_team_rules_gis.json','w'),indent=1,default=str); print(json.dumps(qa,indent=1,default=str))
