"""Build dz_brma_share and dz_park_overlay. All geometry in EPSG:27700."""
import pandas as pd, geopandas as gpd, numpy as np, sys
sys.path.insert(0,'/workspace/scotland-gis/scripts')
from zone_rules import check_codes, VINT
from pathlib import Path
R=Path('/workspace/scotland-gis/raw'); O=Path('/workspace/scotland-gis/out'); O.mkdir(exist_ok=True)
CRS=27700
spd=pd.read_parquet('/workspace/scotland-gis/work/spd.parquet')
hh=spd[spd.CensusHouseholdCount2022>0].copy()
pts=gpd.GeoDataFrame(hh,geometry=gpd.points_from_xy(hh.GridReferenceEasting,hh.GridReferenceNorthing),crs=CRS)

zones={
 'DZ2011':gpd.read_file(R/'SG_DataZoneBdry_2011/SG_DataZone_Bdry_2011.shp')[['DataZone','geometry']].rename(columns={'DataZone':'code'}),
 'DZ2022':gpd.read_file(R/'SG_DataZoneBdry_2022/SG_DataZone_Bdry_2022.shp')[['dzcode','geometry']].rename(columns={'dzcode':'code'}),
}
zcol={'DZ2011':'DataZone2011Code','DZ2022':'DataZone2022Code'}
for v,z in zones.items():
    assert z.crs.to_epsg()==CRS; z['geometry']=z.geometry.make_valid()

# ---------------- BRMA ----------------
brma=gpd.read_file(R/'SG_BroadRentalMarketAreas_2009/SG_BroadRentalMarketAreas_2009.shp')[['BRMA','BRMAName','geometry']]
assert brma.crs.to_epsg()==CRS and len(brma)==18
brma['geometry']=brma.geometry.make_valid()
pj=gpd.sjoin(pts,brma,how='left',predicate='within')
pj=pj[~pj.index.duplicated(keep='first')]  # guard against points exactly on shared edges
miss=pj.BRMA.isna()
qa={'hh_postcodes':len(pts),'hh_total':float(pts.CensusHouseholdCount2022.sum()),
    'points_outside_all_brma':int(miss.sum()),'hh_outside_all_brma':float(pj.loc[miss,'CensusHouseholdCount2022'].sum())}
if miss.any():  # coastal points just off the BRMA coastline -> nearest BRMA
    near=gpd.sjoin_nearest(pts.loc[miss[miss].index],brma,how='left',distance_col='dist_m')
    near=near[~near.index.duplicated()]
    pj.loc[near.index,['BRMA','BRMAName']]=near[['BRMA','BRMAName']].values
    qa['nearest_snap_max_dist_m']=float(near.dist_m.max())
out=[]
for v,z in zones.items():
    t=pj.groupby([zcol[v],'BRMA','BRMAName']).CensusHouseholdCount2022.sum().reset_index()
    t.columns=['code','brma_id','brma_name','hh']
    t['household_share']=t.hh/t.groupby('code').hh.transform('sum')
    t['method']='postcode_hh2022_points'; t['vintage']=VINT[v]
    nohh=sorted(set(z.code)-set(t.code))
    if nohh:
        zz=z[z.code.isin(nohh)]
        ov=gpd.overlay(zz,brma,how='intersection',keep_geom_type=True)
        ov['a']=ov.area
        ov=ov.groupby(['code','BRMA','BRMAName']).a.sum().reset_index()
        ov['household_share']=ov.a/ov.groupby('code').a.transform('sum')
        ov=ov.rename(columns={'BRMA':'brma_id','BRMAName':'brma_name'}); ov['hh']=0
        ov['method']='area_share_fallback_no_hh_points'; ov['vintage']=VINT[v]
        t=pd.concat([t,ov[t.columns]])
    qa[f'{v}_zones']=t.code.nunique(); qa[f'{v}_fallback_zones']=nohh
    qa[f'{v}_zones_split_across_brma']=int((t.groupby('code').size()>1).sum())
    s=t.groupby('code').household_share.sum(); qa[f'{v}_max_abs_sum_error']=float((s-1).abs().max())
    out.append(t)
b=pd.concat(out)
b=b[['code','vintage','brma_id','brma_name','household_share','hh','method']].rename(columns={'hh':'hh2022_weight'})
b=b.sort_values(['vintage','code','brma_id'])
b['vintage']=b.vintage.astype(int); check_codes(b); assert not b.duplicated(['code','vintage','brma_id']).any()
b.to_csv(O/'dz_brma_share.csv',index=False,float_format='%.12g')
qa['rows']=len(b)
# QA: postcode zone code vs point-in-polygon zone
for v,z in zones.items():
    pz=gpd.sjoin(pts[[zcol[v],'CensusHouseholdCount2022','geometry']],z,how='left',predicate='within')
    pz=pz[~pz.index.duplicated()]
    mism=pz[zcol[v]]!=pz.code
    qa[f'{v}_pc_centroid_outside_assigned_zone_pct_hh']=round(100*pz.loc[mism,'CensusHouseholdCount2022'].sum()/pz.CensusHouseholdCount2022.sum(),3)
pd.Series(qa,dtype=object).to_json(O/'qa_brma.json',indent=1)
print(pd.Series(qa,dtype=object).to_string())

# ---------------- Parks ----------------
cg=gpd.read_file(R/'SG_CairngormsNationalPark_2010/SG_CairngormsNationalPark_2010.shp')
ll=gpd.read_file(R/'SG_LochLomondTrossachsNationalPark_2002/SG_LochLomondTrossachsNationalPark_2002.shp')
parks=pd.concat([gpd.GeoDataFrame({'park_code':['S21000003'],'park_name':['Cairngorms National Park']},geometry=[cg.geometry.union_all()],crs=CRS),
                 gpd.GeoDataFrame({'park_code':['S21000002'],'park_name':['Loch Lomond and The Trossachs National Park']},geometry=[ll.geometry.union_all()],crs=CRS)])
parks['geometry']=parks.geometry.make_valid()
pq={'park_area_km2':dict(zip(parks.park_code,(parks.area/1e6).round(1)))}
pp=gpd.sjoin(pts,parks,how='left',predicate='within'); pp=pp[~pp.index.duplicated()]
# QA vs NRS SPD NationalPark2010Code
agree=(pp.park_code.fillna('none')==pp.NationalPark2010Code.fillna('none'))
pq['hh_postcodes_park_flag_disagree_with_SPD']=int((~agree).sum())
pq['hh_in_park_by_points']=pp.groupby('park_code').CensusHouseholdCount2022.sum().to_dict()
pq['hh_in_park_by_SPD_flag']=hh.groupby('NationalPark2010Code').CensusHouseholdCount2022.sum().to_dict()
rows=[]
for v,z in zones.items():
    z=z.copy(); z['zone_area']=z.area
    ov=gpd.overlay(z,parks,how='intersection',keep_geom_type=True)
    ov['ia']=ov.area
    ov=ov.groupby(['code','park_code','park_name','zone_area']).ia.sum().reset_index()
    ov=ov[ov.ia>0]
    ov['area_share']=(ov.ia/ov.zone_area).clip(upper=1.0)
    tot=hh.groupby(zcol[v]).CensusHouseholdCount2022.sum()
    inp=pp.dropna(subset=['park_code']).groupby([zcol[v],'park_code']).CensusHouseholdCount2022.sum()
    ov['hh_total']=ov.code.map(tot).fillna(0)
    ov['hh_in_park']=[inp.get((c,p),0.0) for c,p in zip(ov.code,ov.park_code)]
    ov['hh_share']=np.where(ov.hh_total>0,ov.hh_in_park/ov.hh_total.where(ov.hh_total>0),ov.area_share)
    ov['method']=np.where(ov.hh_total>0,'postcode_hh2022_points','area_share_fallback_no_hh_points')
    ov['intersect_area_m2']=ov.ia.round(1)
    ov['vintage']=VINT[v]
    # zones with household points inside the park but zero overlap area (centroid tolerance) -> report
    stray=set(c for (c,p) in inp.index)-set(ov.code)
    pq[f'{v}_zones_with_park_hh_but_no_polygon_overlap']=sorted(stray)
    pq[f'{v}_rows']=len(ov); pq[f'{v}_fully_inside(area_share>=0.9999)']=int((ov.area_share>=0.9999).sum())
    pq[f'{v}_slivers(<0.1%_area,0_hh_in_park)']=int(((ov.area_share<0.001)&(ov.hh_in_park==0)).sum())
    pq[f'{v}_rows_by_park']=ov.park_code.value_counts().to_dict()
    pq[f'{v}_hh_in_park_sum']=ov.groupby('park_code').hh_in_park.sum().to_dict()
    rows.append(ov)
P=pd.concat(rows)[['code','vintage','park_code','park_name','area_share','hh_in_park','hh_total','hh_share','method','intersect_area_m2']]
P=P.sort_values(['vintage','park_code','code']); P['vintage']=P.vintage.astype(int); check_codes(P); assert not P.duplicated(['code','vintage','park_code']).any()
P.to_csv(O/'dz_park_overlay.csv',index=False,float_format='%.10g')
pd.Series(pq,dtype=object).to_json(O/'qa_park.json',indent=1)
print(pd.Series(pq,dtype=object).to_string())
