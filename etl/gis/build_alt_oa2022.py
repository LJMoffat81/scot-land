"""Robustness/licence-clean alternative: Census 2022 OA household counts placed at NRS OA2022 population-weighted centroids."""
import pandas as pd, geopandas as gpd, numpy as np, json, sys
sys.path.insert(0,'/workspace/scotland-gis/scripts')
from zone_rules import check_codes, VINT
from pathlib import Path
R=Path('/workspace/scotland-gis/raw'); O=Path('/workspace/scotland-gis/out/alt'); O.mkdir(parents=True,exist_ok=True)
oa=pd.read_csv(R/'oa22_pwc.csv',dtype={'code':str})
oa=oa[oa.HHcount>0]
pts=gpd.GeoDataFrame(oa,geometry=gpd.points_from_xy(oa.easting.astype(float),oa.northing.astype(float)),crs=27700)
spd=pd.read_parquet('/workspace/scotland-gis/work/spd.parquet')
oa2dz22=spd.drop_duplicates('OutputArea2022Code').set_index('OutputArea2022Code').DataZone2022Code
pts['DZ2022']=pts.code.map(oa2dz22)
z11=gpd.read_file(R/'SG_DataZoneBdry_2011/SG_DataZone_Bdry_2011.shp')[['DataZone','geometry']]
z22=gpd.read_file(R/'SG_DataZoneBdry_2022/SG_DataZone_Bdry_2022.shp')[['dzcode','geometry']]
j=gpd.sjoin(pts,z11,predicate='within',how='left'); j=j[~j.index.duplicated()]
j=gpd.sjoin_nearest(pts.loc[j.index[j.DataZone.isna()]],z11) if j.DataZone.isna().any() else None
pp=gpd.sjoin(pts,z11,predicate='within',how='left'); pp=pp[~pp.index.duplicated()]
if j is not None: pp.loc[j.index,'DataZone']=j.DataZone.values
pts['DZ2011']=pp.DataZone
brma=gpd.read_file(R/'SG_BroadRentalMarketAreas_2009/SG_BroadRentalMarketAreas_2009.shp')[['BRMA','BRMAName','geometry']]
b=gpd.sjoin(pts.drop(columns=[c for c in ['index_right'] if c in pts]),brma,predicate='within',how='left'); b=b[~b.index.duplicated()]
m=b.BRMA.isna()
if m.any():
    n=gpd.sjoin_nearest(pts.loc[m[m].index],brma); n=n[~n.index.duplicated()]; b.loc[n.index,['BRMA','BRMAName']]=n[['BRMA','BRMAName']].values
qa={'oa_points':len(pts),'hh':int(pts.HHcount.sum()),'oa_outside_brma_snapped':int(m.sum())}
prim=pd.read_csv('/workspace/scotland-gis/out/dz_brma_share.csv')
out=[]
for v,zz,col in [('DZ2011',z11.rename(columns={'DataZone':'code'}),'DZ2011'),('DZ2022',z22.rename(columns={'dzcode':'code'}),'DZ2022')]:
    t=b.groupby([col,'BRMA','BRMAName']).HHcount.sum().reset_index(); t.columns=['code','brma_id','brma_name','hh']
    t['household_share']=t.hh/t.groupby('code').hh.transform('sum'); t['method']='oa2022_hh_pwc_points'
    nohh=sorted(set(zz.code)-set(t.code))
    if nohh:
        ov=gpd.overlay(zz[zz.code.isin(nohh)],brma,how='intersection'); ov['a']=ov.area
        ov=ov.groupby(['code','BRMA','BRMAName']).a.sum().reset_index(); ov['household_share']=ov.a/ov.groupby('code').a.transform('sum')
        ov=ov.rename(columns={'BRMA':'brma_id','BRMAName':'brma_name'}); ov['hh']=0; ov['method']='area_share_fallback_no_hh_points'
        t=pd.concat([t,ov[t.columns]])
    t['vintage']=VINT[v]; out.append(t)
    qa[f'{v}_fallback_zones']=len(nohh); qa[f'{v}_max_sum_err']=float((t.groupby('code').household_share.sum()-1).abs().max())
    c=prim[prim.vintage==VINT[v]].merge(t,on=['code','brma_id'],how='outer',suffixes=('_pc','_oa')).fillna({'household_share_pc':0,'household_share_oa':0})
    dd=(c.household_share_pc-c.household_share_oa).abs()
    qa[f'{v}_max_abs_diff_vs_postcode']=round(float(dd.max()),4); qa[f'{v}_zones_diff_gt_0.05']=int(c.loc[dd>0.05,'code'].nunique())
    qa[f'{v}_zones_split_oa']=int((t.groupby('code').size()>1).sum())
A=pd.concat(out)[['code','vintage','brma_id','brma_name','household_share','hh','method']].rename(columns={'hh':'hh2022_weight'}).sort_values(['vintage','code','brma_id'])
A['vintage']=A.vintage.astype(int); check_codes(A); assert not A.duplicated(['code','vintage','brma_id']).any()
A.to_csv(O/'dz_brma_share_oa2022.csv',index=False,float_format='%.12g')
json.dump(qa,open(O/'qa_alt_oa2022.json','w'),indent=1); print(json.dumps(qa,indent=1))
