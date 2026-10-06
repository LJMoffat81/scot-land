"""dz_residential_land final assembly + QA (incl. official dwellings-per-hectare comparison, mask_too_big flags)."""
import pandas as pd, numpy as np, json, hashlib, sys
sys.path.insert(0,'/workspace/scotland-gis/scripts'); from zone_rules import check_codes, dwellings_2025
from pathlib import Path
B=Path('/workspace/scotland-gis'); R=B/'raw'; W=B/'work'; OUT=B/'out'
d=pd.read_csv(W/'dz_residential_stage2.csv')
d['vintage']=d.vintage.map({'DZ2011':2011,'DZ2022':2022}).astype(int)   # team rule: integer vintage
RANGE={2011:('S01006506','S01013481'),2022:('S01013482','S01020873')}
assert all(((g.code>=RANGE[v][0])&(g.code<=RANGE[v][1])).all() for v,g in d.groupby('vintage')), 'code out of official range'
assert d.groupby('vintage').size().to_dict()=={2011:6976,2022:7392}
# Dwelling denominator (team rule): Data Zones dwellings_by_year.csv dwellings_total, count_year 2025, same vintage
dw=dwellings_2025()[['code','vintage','dwellings_total']].rename(columns={'dwellings_total':'dwellings_total_2025'})   # shared team rule
d=d.merge(dw,on=['code','vintage'],how='left',validate='1:1'); assert d.dwellings_total_2025.notna().all()
# Official NRS dwellings + dwellings per hectare (whole-zone area), December 2025, same vintage as the zone
off=[]
for v,f in [(2022,'dwelling-estimates-by-2022-data-zones-24-25.xlsx'),(2011,'dwellings-estimate-by-2011-data-zones.xlsx')]:
    x=pd.read_excel(R/f,sheet_name='2025',header=4)
    x=x.rename(columns={'Data Zone code':'code','Total number of dwellings':'assessor_dwellings_dec2025','Dwellings per hectare':'official_dph_2025'})
    x=x[x.code.astype(str).str.match(r'^S01\d{6}$')][['code','assessor_dwellings_dec2025','official_dph_2025']]; x['vintage']=v; off.append(x)
off=pd.concat(off); d=d.merge(off,on=['code','vintage'],how='left',validate='1:1')
assert d.official_dph_2025.notna().all()
# slivers from boundary misalignment (<0.01 ha = 100 m2) are zeroed so they cannot create absurd densities
SLIVER=0.01
for col in ['settlement_ha','residential_parcel_ha']:
    sl=(d[col]>0)&(d[col]<SLIVER); d.loc[sl,col]=0.0; d.loc[sl,'method_flags']+=f';{col}_sliver_lt_0.01ha_zeroed'
d.loc[(d.residential_parcel_ha==0)&~d.method_flags.str.contains('no_residential_parcel'),'method_flags']+=';no_residential_parcel'
d.loc[d.share_res_uprn_in_parcels<0.5,'method_flags']+=';low_parcel_coverage_lt0.5'
# Georgist team rule: zones with 0 dwellings in 2025 get residential land NA (valued via vacant/derelict + housing land supply layers)
zero=d.dwellings_total_2025==0
d['residential_parcel_ha_before_zero_rule']=d.residential_parcel_ha
d.loc[zero,['settlement_ha','residential_parcel_ha']]=np.nan
d.loc[zero,'method_flags']+=';zero_dwellings'
# EPC UPRNs persist for demolished stock (no open demolition flag; OS Open UPRN keeps the points): flag zones where they exceed dwellings
exc=(d.n_res_uprn>1.25*d.dwellings_total_2025)
d.loc[exc,'method_flags']+=';res_uprn_exceeds_dwellings'
d['res_uprn_exceeds_dwellings']=exc
d['nrs_implied_zone_ha']=d.assessor_dwellings_dec2025/d.official_dph_2025
for m,col in [('settlement','settlement_ha'),('parcel','residential_parcel_ha')]:
    d[f'dph_{m}']=np.where(d[col]>0,d.dwellings_total_2025/d[col].where(d[col]>0),np.nan)
    # ours is compared at the official's 2-dp precision; no mask (0 ha) -> flag left blank (mask absent, not too big)
    f=(d[f'dph_{m}'].round(2)<=d.official_dph_2025)
    d[f'mask_too_big_{m}']=f.where(d[col]>0).astype('boolean')
    # diagnostic: pure area test (mask >= NRS whole-zone area), free of the numerator mismatch (CT Sept vs assessor Dec)
    d[f'area_test_{m}']=(d[col]>=d.nrs_implied_zone_ha*0.999).where(d[col]>0).astype('boolean')
cols=['code','vintage','zone_ha','settlement_ha','residential_parcel_ha','n_res_parcels','n_res_uprn','share_res_uprn_in_parcels',
      'capped_parcels_n','capped_ha','method_flags','res_uprn_exceeds_dwellings','dwellings_total_2025','official_dph_2025','dph_settlement','dph_parcel',
      'mask_too_big_settlement','mask_too_big_parcel']
o=d[cols].sort_values(['vintage','code'])
for c in ['zone_ha','settlement_ha','residential_parcel_ha','capped_ha']: o[c]=o[c].round(4)
for c in ['dph_settlement','dph_parcel']: o[c]=o[c].round(3)
o['share_res_uprn_in_parcels']=o.share_res_uprn_in_parcels.round(4)
check_codes(o); OUT.mkdir(exist_ok=True); o.to_csv(OUT/'dz_residential_land.csv',index=False)
# ---------- QA ----------
qa={}
for v,g in d.groupby('vintage'):
    q={}
    q['zones']=len(g); q['zone_ha']=round(g.zone_ha.sum()); q['settlement_ha']=round(g.settlement_ha.sum()); q['residential_parcel_ha']=round(g.residential_parcel_ha.sum())
    q['dwellings_total_2025']=int(g.dwellings_total_2025.sum())
    q['national_dph_settlement']=round(g.dwellings_total_2025.sum()/g.settlement_ha.sum(),2)
    q['national_dph_parcel']=round(g.dwellings_total_2025.sum()/g.residential_parcel_ha.sum(),2)
    q['national_official_dph_wholezone']=round(g.dwellings_total_2025.sum()/g.zone_ha.sum(),3)
    q['zone_area_vs_nrs_implied_median_ratio']=round(float((g.zone_ha/g.nrs_implied_zone_ha).median()),4)
    for m,col in [('settlement','settlement_ha'),('parcel','residential_parcel_ha')]:
        x=g[g[col]>0]; q[f'dph_{m}_quantiles']={str(p):round(float(x[f'dph_{m}'].quantile(p)),1) for p in [.05,.25,.5,.75,.95,.99]}
        q[f'zones_no_{m}_mask']=int((g[col]==0).sum())
        q[f'mask_too_big_{m}_n']=int(g[f'mask_too_big_{m}'].sum())
        q[f'area_test_mask_ge_zone_{m}_n']=int(g[f'area_test_{m}'].sum())
        q[f'flag_and_area_test_both_{m}_n']=int((g[f'mask_too_big_{m}']&g[f'area_test_{m}']).sum())
        fl=g[g[f'mask_too_big_{m}']==True].assign(mask_share=lambda t:t[col]/t.zone_ha, ratio=lambda t:t[f'dph_{m}']/t.official_dph_2025)
        q[f'mask_too_big_{m}_mask_share_of_zone_quantiles']={str(p):round(float(fl.mask_share.quantile(p)),4) for p in [.05,.5,.95]} if len(fl) else {}
        q[f'mask_too_big_{m}_worst']=fl.sort_values('ratio').head(8)[['code','zone_ha',col,'dwellings_total_2025','official_dph_2025',f'dph_{m}','ratio']].round(3).to_dict('records')
    ar=g.nrs_implied_zone_ha/g.zone_ha
    q['official_area_base_differs_gt5pct_zones']=int(((ar<0.95)|(ar>1.05)).sum())
    q['mask_too_big_settlement_where_official_area_differs_gt5pct']=int((g.mask_too_big_settlement&((ar<0.95)|(ar>1.05))).sum())
    q['mask_too_big_parcel_where_official_area_differs_gt5pct']=int((g.mask_too_big_parcel&((ar<0.95)|(ar>1.05))).sum())
    q['zones_low_parcel_coverage_lt0.5']=int((g.share_res_uprn_in_parcels<0.5).sum())
    q['zones_n_res_parcels_0']=int((g.n_res_parcels==0).sum())
    q['zones_settlement_ge_99pct_of_zone']=int((g.settlement_ha>=0.99*g.zone_ha).sum())
    sp=pd.read_csv('/workspace/scotland-datazones/data/processed/datazones/zone_spine.csv',usecols=['code','vintage','name','la_name'])
    gg=g.merge(sp,on=['code','vintage'],how='left')
    gl=gg[(gg.la_name=='Glasgow City')&(gg.residential_parcel_ha>0)].sort_values('official_dph_2025',ascending=False).head(3)
    ru=gg[(gg.residential_parcel_ha>0)&(gg.zone_ha>5000)&(gg.dwellings_total_2025>0)].sort_values('official_dph_2025').iloc[[0,len(gg[(gg.residential_parcel_ha>0)&(gg.zone_ha>5000)])//2]]
    keepc=['code','name','la_name','zone_ha','settlement_ha','residential_parcel_ha','dwellings_total_2025','official_dph_2025','dph_settlement','dph_parcel','share_res_uprn_in_parcels']
    q['sanity_glasgow_densest']=gl[keepc].round(3).to_dict('records'); q['sanity_rural']=ru[keepc].round(3).to_dict('records')
    q['zero_dwellings_zones']=g[g.dwellings_total_2025==0].code.tolist()
    q['residential_parcel_ha_before_zero_rule']=round(float(g.residential_parcel_ha_before_zero_rule.sum()),2)
    q['residential_parcel_ha_after_zero_rule']=round(float(g.residential_parcel_ha.sum()),2)
    q['res_uprn_exceeds_dwellings_n']=int(g.res_uprn_exceeds_dwellings.sum())
    q['res_uprn_exceeds_dwellings_worst']=g[g.res_uprn_exceeds_dwellings].assign(r=lambda t:t.n_res_uprn/t.dwellings_total_2025.where(t.dwellings_total_2025>0)).sort_values('r',ascending=False).head(8)[['code','n_res_uprn','dwellings_total_2025','residential_parcel_ha_before_zero_rule']].round(2).to_dict('records')
    q['zones_no_residential_parcel_but_dwellings>=10']=int(((g.residential_parcel_ha==0)&(g.dwellings_total_2025>=10)).sum())
    q['res_uprn_in_parcels_share_national']=round(float((g.share_res_uprn_in_parcels*g.n_res_uprn).sum()/g.n_res_uprn.sum()),4)
    q['res_uprn_per_dwelling_national']=round(g.n_res_uprn.sum()/g.dwellings_total_2025.sum(),4)
    q['share_res_uprn_in_parcels_zone_quantiles']={str(p):round(float(g.share_res_uprn_in_parcels.quantile(p)),3) for p in [.05,.25,.5,.75]}
    q['parcel_ha_gt_settlement_ha_zones']=int((g.residential_parcel_ha>g.settlement_ha).sum())
    qa[v]=q
json.dump(qa,open(OUT/'qa_dz_residential_land.json','w'),indent=1,default=str)
print(json.dumps(qa,indent=1,default=str)); print(len(o),'rows')
