"""dz_residential_land stage 1: zone area and area inside NRS Census 2022 Settlements (EPSG:27700)."""
import geopandas as gpd, pandas as pd, json
from pathlib import Path
R=Path('/workspace/scotland-gis/raw'); W=Path('/workspace/scotland-gis/work')
s=gpd.read_file(R/'settlements/set22_p0.geojson')
if s.crs is None or s.crs.to_epsg()!=27700: s=s.set_crs(27700,allow_override=True)
s['geometry']=s.geometry.make_valid()
S=s.dissolve()  # union of settlements
qa={'settlements':len(s),'settlement_union_ha':round(float(S.area.sum()/1e4),1),'settlement_attr_area_ha':round(float(s.st_area_shape_.sum()/1e4),1)}
rows=[]
for v,f,c in [('DZ2011','SG_DataZoneBdry_2011/SG_DataZone_Bdry_2011.shp','DataZone'),('DZ2022','SG_DataZoneBdry_2022/SG_DataZone_Bdry_2022.shp','dzcode')]:
    z=gpd.read_file(R/f)[[c,'geometry']].rename(columns={c:'code'}); assert z.crs.to_epsg()==27700
    z['geometry']=z.geometry.make_valid(); z['zone_ha']=z.area/1e4
    ov=gpd.overlay(z[['code','geometry']],S[['geometry']],how='intersection',keep_geom_type=True)
    ov['settlement_ha']=ov.area/1e4; ov=ov.groupby('code').settlement_ha.sum()
    z['settlement_ha']=z.code.map(ov).fillna(0.0); z['settlement_ha']=z[['settlement_ha','zone_ha']].min(axis=1)
    z['vintage']=v; rows.append(pd.DataFrame(z.drop(columns='geometry')))
    qa[f'{v}_zones']=len(z); qa[f'{v}_zone_ha_total']=round(float(z.zone_ha.sum()),0); qa[f'{v}_settlement_ha_total']=round(float(z.settlement_ha.sum()),0)
    qa[f'{v}_zones_no_settlement']=int((z.settlement_ha==0).sum())
out=pd.concat(rows)[['code','vintage','zone_ha','settlement_ha']]
out.to_csv(W/'dz_settlement_ha.csv',index=False)
json.dump(qa,open(W/'qa_stage1.json','w'),indent=1); print(json.dumps(qa,indent=1))
