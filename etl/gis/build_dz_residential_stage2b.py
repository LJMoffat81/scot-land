"""dz_residential_land stage 2b: apply size cap, assign residential parcels to DZ2011 + DZ2022 zones,
union overlapping parcels within each zone (intersection-area method), and write zone totals only.
Parcel geometry stays in work/ (internal; OS INSPIRE end-user licence)."""
import glob, json, geopandas as gpd, pandas as pd, numpy as np, shapely
from pathlib import Path
B=Path('/workspace/scotland-gis'); R=B/'raw'; W=B/'work'
CAP_HA=2.0          # parcels above this are capped (dropped) ...
DENSE_M2_PER_UPRN=1000.0  # ... unless they carry >=1 residential UPRN per 1,000 m2 (estate / multi-unit titles)
r=pd.concat([gpd.read_parquet(f) for f in sorted(glob.glob(str(W/'inspire_res/[A-Z][A-Z][A-Z].parquet')))]).reset_index(drop=True)
r['ha']=r.area_m2/1e4; r['m2pu']=r.area_m2/r.n_uprn
r['capped']=(r.ha>CAP_HA)&(r.m2pu>DENSE_M2_PER_UPRN)
r['big_exempt']=(r.ha>CAP_HA)&~r.capped
keep=r[~r.capped].copy(); cap=r[r.capped].copy()
pairs=pd.read_parquet(W/'uprn_parcel_pairs.parquet')   # from build_dz_residential_pairs.py, keyed by inspireid
in_kept=set(pairs.loc[pairs.inspireid.isin(set(keep.inspireid)),'uprn'])
pts=pd.read_parquet(W/'res_uprn.parquet'); pts['in_parcel']=pts.uprn.isin(in_kept)
P=gpd.GeoDataFrame(pts,geometry=gpd.points_from_xy(pts.x,pts.y),crs=27700)
for d in (keep,cap): d['pos']=d.geometry.representative_point()
st=pd.read_csv(W/'dz_settlement_ha.csv')
qa={'cap_ha':CAP_HA,'dense_exemption_m2_per_uprn':DENSE_M2_PER_UPRN,'res_parcels_total':len(r),'res_parcels_ha_total':round(r.ha.sum()),
    'capped_parcels_n':int(r.capped.sum()),'capped_ha':round(cap.ha.sum()),'capped_uprn_sum':int(cap.n_uprn.sum()),
    'big_exempt_n':int(r.big_exempt.sum()),'big_exempt_ha':round(r.ha[r.big_exempt].sum()),
    'kept_parcels_n':len(keep),'kept_parcels_ha_sum_overlapping':round(keep.ha.sum()),
    'res_uprn_total':len(pts),'res_uprn_in_kept_parcel':int(pts.in_parcel.sum())}
out=[]
for v,f,c in [('DZ2011','SG_DataZoneBdry_2011/SG_DataZone_Bdry_2011.shp','DataZone'),('DZ2022','SG_DataZoneBdry_2022/SG_DataZone_Bdry_2022.shp','dzcode')]:
    z=gpd.read_file(R/f)[[c,'geometry']].rename(columns={c:'code'}); z['geometry']=z.geometry.make_valid()
    # union area by zone: clip kept parcels to zones, then union pieces per zone (removes stacked/overlapping titles)
    j=gpd.sjoin(keep[['geometry']],z[['code','geometry']],predicate='intersects')
    zg=z.set_index('code').geometry
    pieces=shapely.intersection(j.geometry.values, zg.loc[j.code].values)
    pc=gpd.GeoDataFrame({'code':j.code.values},geometry=pieces,crs=27700)
    ua=pc.groupby('code').geometry.apply(lambda s: shapely.union_all(s.values).area/1e4)
    def cnt(df,col=None):
        g=gpd.sjoin(gpd.GeoDataFrame(df.drop(columns='geometry'),geometry=df.pos,crs=27700),z[['code','geometry']],predicate='within')
        return g.groupby('code').size() if col is None else g.groupby('code')[col].sum()
    n_res=cnt(keep); n_cap=cnt(cap); ha_cap=cnt(cap,'ha')
    pu=gpd.sjoin(P[['uprn','in_parcel','geometry']],z[['code','geometry']],predicate='within')
    nu=pu.groupby('code').size(); ni=pu.groupby('code').in_parcel.sum()
    o=st[st.vintage==v].set_index('code')
    o['residential_parcel_ha']=ua.reindex(o.index).fillna(0.0)
    o['n_res_parcels']=n_res.reindex(o.index).fillna(0).astype(int)
    o['n_res_uprn']=nu.reindex(o.index).fillna(0).astype(int)
    o['share_res_uprn_in_parcels']=(ni.reindex(o.index)/nu.reindex(o.index))
    o['capped_parcels_n']=n_cap.reindex(o.index).fillna(0).astype(int)
    o['capped_ha']=ha_cap.reindex(o.index).fillna(0.0)
    o['method_flags']=('settlement_mask=NRS_settlements_2022_intersection;parcel_residential_uprn=RoS_INSPIRE_2026-08+EPC_OSG_UPRN;'
                       f'area=intersection_union_per_zone;counts=point_on_surface;cap>{CAP_HA:g}ha_unless_<= {DENSE_M2_PER_UPRN:g}m2_per_res_uprn').replace(' ','')
    o.loc[o.n_res_parcels.eq(0)&o.residential_parcel_ha.gt(0),'method_flags']+=';area_from_parcels_centred_in_neighbour_zone'
    o.loc[o.residential_parcel_ha.eq(0),'method_flags']+=';no_residential_parcel'
    out.append(o.reset_index())
    qa[f'{v}_residential_parcel_ha_total']=round(float(o.residential_parcel_ha.sum()))
    qa[f'{v}_res_uprn_located']=int(nu.sum())
pd.concat(out).to_csv(W/'dz_residential_stage2.csv',index=False)
json.dump(qa,open(W/'qa_stage2.json','w'),indent=1); print(json.dumps(qa,indent=1))
