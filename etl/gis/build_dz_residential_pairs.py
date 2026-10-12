"""INTERNAL: residential UPRN x residential parcel containment pairs, keyed by inspireid (no row-order dependence).
Output work/uprn_parcel_pairs.parquet: uprn, inspireid, area_m2, n_uprn (residential UPRNs in that parcel)."""
import glob, geopandas as gpd, pandas as pd
from pathlib import Path
W=Path('/workspace/scotland-gis/work')
r=pd.concat([gpd.read_parquet(f) for f in sorted(glob.glob(str(W/'inspire_res/[A-Z][A-Z][A-Z].parquet')))]).reset_index(drop=True)
assert not r.inspireid.duplicated().any()
pts=pd.read_parquet(W/'res_uprn.parquet')
P=gpd.GeoDataFrame(pts[['uprn']],geometry=gpd.points_from_xy(pts.x,pts.y),crs=27700)
j=gpd.sjoin(P,r[['inspireid','area_m2','n_uprn','geometry']],predicate='within')
j[['uprn','inspireid','area_m2','n_uprn']].to_parquet(W/'uprn_parcel_pairs.parquet')
print('pairs',len(j),'uprns',j.uprn.nunique())
