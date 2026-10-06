"""dz_residential_land stage 2a (INTERNAL): per RoS INSPIRE county file, find parcels containing >=1
residential UPRN (domestic EPC OSG_REFERENCE_NUMBER joined to OS Open UPRN points).
Writes work/inspire_res/<county>.parquet (parcel geometry - internal only, never published) and
work/inspire_res/<county>_uprn_in.parquet (UPRNs falling inside any parcel of that county)."""
import sys, json, geopandas as gpd, pandas as pd, numpy as np, shapely
from pathlib import Path
B=Path('/workspace/scotland-gis'); O=B/'work/inspire_res'
pts=pd.read_parquet(B/'work/res_uprn.parquet')
def run(c):
    if (O/f'{c}.json').exists(): return
    p=gpd.read_file(f'/vsizip/{B}/raw/inspire/{c}.zip/{c}_bng.shp',columns=['inspireid'])
    assert p.crs.to_epsg()==27700
    bad=~p.geometry.is_valid; p.loc[bad,'geometry']=p.geometry[bad].make_valid()
    p['area_m2']=p.area
    x0,y0,x1,y1=p.total_bounds
    q=pts[(pts.x>=x0)&(pts.x<=x1)&(pts.y>=y0)&(pts.y<=y1)]
    q=gpd.GeoDataFrame(q,geometry=gpd.points_from_xy(q.x,q.y),crs=27700)
    j=gpd.sjoin(q[['uprn','geometry']],p[['geometry']],predicate='within',how='inner')
    cnt=j.groupby('index_right').uprn.nunique()
    r=p.loc[cnt.index].copy(); r['n_uprn']=cnt.values; r['county']=c
    r.to_parquet(O/f'{c}.parquet')
    pd.DataFrame({'uprn':j.uprn.unique()}).to_parquet(O/f'{c}_uprn_in.parquet')
    qa=dict(county=c,parcels=len(p),parcel_ha=float(p.area_m2.sum()/1e4),invalid_fixed=int(bad.sum()),
            res_parcels=len(r),res_parcel_ha=float(r.area_m2.sum()/1e4),uprn_in_bbox=len(q),uprn_in_parcel=int(j.uprn.nunique()))
    json.dump(qa,open(O/f'{c}.json','w')); print(qa,flush=True)
for c in sys.argv[1:]: run(c)
