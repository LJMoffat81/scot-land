"""No open sub-zone dwelling counts (incl. unoccupied) exist for 2022 -> sensitivity bounds instead.
For each split zone row: occupied dwellings are distributed like Census 2022 households (the published share);
the zone's unoccupied dwellings (Scot-LAND Data Zones dwellings_by_year, count_year 2025 = NRS Sept 2025 council-tax: dwellings_total - occupied) are put either all outside (lower) or all inside (upper)."""
import pandas as pd, numpy as np, json, sys
sys.path.insert(0,'/workspace/scotland-gis/scripts')
from zone_rules import check_codes, dwellings_2025, dwellings_flag, DW_SOURCE
from pathlib import Path
O=Path('/workspace/scotland-gis/out'); A=O/'alt'
H=dwellings_2025().rename(columns={'dwellings_total':'dw','occupied':'occ','second_homes':'second','vacant':'vac'})[['code','vintage','dw','occ','second','vac']]
qa={}
def bounds(df,share):
    m=df.merge(H,on=['code','vintage'],how='left',validate='m:1')
    U=(m.dw-m.occ).clip(lower=0)
    m['dwellings_total_2025']=m.dw.astype('Int64'); m['dw_unoccupied_2025']=U.astype('Int64'); m['second_homes_2025']=m.second.astype('Int64')
    m['dwellings_flag']=dwellings_flag(m.dw); m['dwellings_source']=DW_SOURCE
    # missing count -> bounds left blank (never filled from another year); zero count -> household share kept (no dwellings to split)
    m['dwelling_share_lower']=np.where(m.dw.isna(),np.nan,np.where(m.dw>0,m[share]*m.occ/m.dw,m[share]))
    m['dwelling_share_upper']=np.clip(np.where(m.dw.isna(),np.nan,np.where(m.dw>0,(m[share]*m.occ+U)/m.dw,m[share])),None,1)
    m['max_shift']=np.maximum(m[share]-m.dwelling_share_lower,m.dwelling_share_upper-m[share])
    return m.drop(columns=['dw','occ','second','vac'])
b=pd.read_csv(O/'dz_brma_share.csv',dtype={'code':str}); check_codes(b)
n=b.groupby(['code','vintage']).brma_id.transform('size'); bs=b[n>1].copy()
bb=bounds(bs,'household_share'); bb['method']='bounds_unoccupied_all_out_vs_all_in'
# Georgist v0.5 rule: split zones use midpoint of dwelling bounds; half the gap -> uncertainty band
bb['share_mid_raw']=(bb.dwelling_share_lower+bb.dwelling_share_upper)/2
bb['share_halfwidth']=(bb.dwelling_share_upper-bb.dwelling_share_lower)/2
bb['share_mid']=bb.share_mid_raw/bb.groupby(['code','vintage']).share_mid_raw.transform('sum')
adj=(bb.share_mid-bb.share_mid_raw).abs()
qa['brma_mid_raw_zone_sum_range']=[round(float(x),6) for x in bb.groupby(['code','vintage']).share_mid_raw.sum().agg(['min','max'])]
qa['brma_mid_max_abs_renorm_adjustment']=round(float(adj.max()),6)
qa['brma_mid_rows_adjusted_gt_1e-12']=int((adj>1e-12).sum())
qa['brma_mid_zones_adjusted']=int(bb.loc[adj>1e-12,['code','vintage']].drop_duplicates().shape[0])
qa['brma_mid_max_renorm_row']=bb.loc[adj.idxmax(),['code','vintage','brma_id','share_mid_raw','share_mid']].astype(str).to_dict()
qa['brma_mid_max_abs_sum_err']=float((bb.groupby(['code','vintage']).share_mid.sum()-1).abs().max())
qa['brma_halfwidth_quantiles']={k:round(float(bb.share_halfwidth.quantile(k)),4) for k in [.5,.9,1]}
bb[['code','vintage','brma_id','brma_name','household_share','dwelling_share_lower','dwelling_share_upper','share_mid','share_mid_raw','share_halfwidth','max_shift','dwellings_total_2025','dw_unoccupied_2025','second_homes_2025','dwellings_flag','method','dwellings_source']].pipe(lambda x:(check_codes(x),x)[1]).to_csv(A/'dz_brma_share_dwelling_bounds.csv',index=False,float_format='%.15g')
qa['brma_split_rows']=len(bb); qa['brma_split_zones']=int(bb[['code','vintage']].drop_duplicates().shape[0])
qa['brma_max_shift_quantiles']={k:round(float(bb.max_shift.quantile(k)),4) for k in [.5,.9,.99,1]}
qa['brma_zones_max_shift_gt_0.05']=int(bb.loc[bb.max_shift>0.05,['code','vintage']].drop_duplicates().shape[0])
p=pd.read_csv(O/'dz_park_overlay.csv',dtype={'code':str}); check_codes(p)
pb=bounds(p,'hh_share'); pb['method']='bounds_unoccupied_all_out_vs_all_in'
full=pb.area_share>=0.9999
pb.loc[full,['dwelling_share_lower','dwelling_share_upper']]=1.0; pb.loc[full,'max_shift']=0.0; pb.loc[full,'method']='zone_wholly_inside_park'
pb=pb.rename(columns={'dwelling_share_lower':'dw_share_lower','dwelling_share_upper':'dw_share_upper'})
pb['share_mid']=(pb.dw_share_lower+pb.dw_share_upper)/2  # not renormalised: in-park vs out
pb['share_halfwidth']=(pb.dw_share_upper-pb.dw_share_lower)/2
pb[['code','vintage','park_code','park_name','area_share','hh_share','dw_share_lower','dw_share_upper','share_mid','share_halfwidth','max_shift','dwellings_total_2025','dw_unoccupied_2025','second_homes_2025','dwellings_flag','method','dwellings_source']].pipe(lambda x:(check_codes(x),x)[1]).to_csv(A/'dz_park_overlay_dwelling_bounds.csv',index=False,float_format='%.15g')
part=pb[(pb.hh_share>0)&(pb.hh_share<1)]
qa['park_rows']=len(pb); qa['park_rows_partially_inhabited_in_park(0<hh_share<1)']=len(part)
for (v,pc),g in part.groupby(['vintage','park_code']):
    qa[f'park_{v}_{pc}_partial_rows']=len(g); qa[f'park_{v}_{pc}_median_max_shift']=round(float(g.max_shift.median()),4); qa[f'park_{v}_{pc}_max_max_shift']=round(float(g.max_shift.max()),4)
# park totals: in-park dwellings lower/upper
for v in [2011,2022]:
    g=pb[pb.vintage==v]
    for pc,gg in g.groupby('park_code'):
        dwt=gg.dwellings_total_2025.astype(float)
        lo=(gg.dw_share_lower*dwt).sum(); hi=(gg.dw_share_upper*dwt).sum()
        qa[f'park_{v}_{pc}_in_park_dwellings_bounds']=[round(float(lo)),round(float(hi))]
        qa[f'park_{v}_{pc}_in_park_dwellings_mid']=round(float((gg.share_mid*dwt).sum()))
        qa[f'park_{v}_{pc}_in_park_dwellings_mid_halfwidth']=round(float((gg.share_halfwidth*dwt).sum()))
qa['dwellings_source']=DW_SOURCE
qa['rows_flagged']={f:{'brma':int((bb.dwellings_flag==f).sum()),'park':int((pb.dwellings_flag==f).sum())} for f in ['missing_count_2025','zero_dwellings_2025']}
json.dump(qa,open(A/'qa_alt_dwelling_bounds.json','w'),indent=1); print(json.dumps(qa,indent=1))
