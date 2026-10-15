"""UX-10 built-up display mask (EPSG:27700). Display only: never changes any figure.
mask = union(NRS Census 2022 Settlement2022 -- chosen source, OGL v3) U 50 m buffers of OS Open UPRN points outside settlements,
dissolved, simplified 10 m (topology-preserving), then 2 m buffers unioned round any UPRN left outside. dz2022_masked = DZ2022 ∩ mask for zones with UPRNs.
Inputs (raw downloads), default R=/workspace/scotland-gis/raw:
  settlements/set22_p0.geojson  <- WFS https://maps.gov.scot/server/services/NRS/Census2022/MapServer/WFSServer
                                    typeName CEN2022:Settlement2022 (outputFormat GEOJSON, srsName EPSG:27700)
  SG_DataZoneBdry_2022/SG_DataZone_Bdry_2022.shp <- https://maps.gov.scot/ATOM/shapefiles/SG_DataZoneBdry_2022.zip
  uprn/osopenuprn_202609.csv    <- OS Open UPRN 2026-09 (OS Data Hub)
Usage: python build_builtup_mask.py [RAW_DIR] [OUT_DIR]"""
import sys, json, hashlib, datetime, numpy as np, geopandas as gpd, duckdb, shapely
from pathlib import Path
R=Path(sys.argv[1] if len(sys.argv)>1 else '/workspace/scotland-gis/raw'); O=Path(sys.argv[2] if len(sys.argv)>2 else Path(__file__).parent); O.mkdir(exist_ok=True)
s=gpd.read_file(R/'settlements/set22_p0.geojson').to_crs(27700); assert len(s)==503
z=gpd.read_file(R/'SG_DataZoneBdry_2022/SG_DataZone_Bdry_2022.shp')[['dzcode','geometry']].rename(columns={'dzcode':'code'})
assert z.crs.to_epsg()==27700 and z.code.nunique()==7392
z['geometry']=z.geometry.make_valid()
S=shapely.union_all(shapely.make_valid(s.geometry.values))
x0,y0,x1,y1=z.total_bounds
cache=O/'.uprn_xy_cache.npz'  # derived cache of Scottish-bbox UPRN coords (not committed)
if cache.exists(): c=np.load(cache); X,Y=c['x'],c['y']
else:
    con=duckdb.connect(); con.execute("SET memory_limit='300MB'; SET threads=2")
    xy=con.sql(f"select X_COORDINATE x,Y_COORDINATE y from read_csv_auto('{R}/uprn/osopenuprn_202609.csv') where x between {x0} and {x1} and y between {y0} and {y1}").fetchnumpy()
    X=np.asarray(xy['x'],float); Y=np.asarray(xy['y'],float); del xy; np.savez(cache,x=X,y=Y)
print('uprn',len(X),flush=True)
tree=shapely.STRtree(z.geometry.values); shapely.prepare(S)
CH=200_000; dzi=np.full(len(X),-1); out=np.zeros(len(X),bool)
for i in range(0,len(X),CH):  # chunked PIP
    P=shapely.points(X[i:i+CH],Y[i:i+CH]); pi,gi=tree.query(P,predicate='intersects')
    d=np.full(len(P),-1); d[pi[::-1]]=gi[::-1]; dzi[i:i+CH]=d  # boundary ties: first match
    out[i:i+CH]=(d>=0)&~shapely.intersects(S,P)
sc=dzi>=0; dz_with=set(z.code.values[np.unique(dzi[sc])])
qa={'uprn_scotland':int(sc.sum()),'uprn_outside_settlements':int(out.sum())}
# outside points deduped to 5 m grid (shift <=3.6 m, well inside the 50 m buffer)
G=np.unique(np.round(np.c_[X[out],Y[out]]/5)*5,axis=0); print('outside pts',len(G),flush=True)
T=10_000; tiles={}  # 10 km tiles; each point goes to every tile its 50 m buffer touches; pieces clipped to tile
kx0=np.floor((G[:,0]-50)/T).astype(int); kx1=np.floor((G[:,0]+50)/T).astype(int)
ky0=np.floor((G[:,1]-50)/T).astype(int); ky1=np.floor((G[:,1]+50)/T).astype(int)
keys=set(zip(kx0,ky0))|set(zip(kx1,ky1))|set(zip(kx0,ky1))|set(zip(kx1,ky0))
sx0,sy0,sx1,sy1=shapely.bounds(S)
keys|={(i,j) for i in range(int(sx0//T),int(sx1//T)+1) for j in range(int(sy0//T),int(sy1//T)+1)}
for n,(i,j) in enumerate(sorted(keys)):
    box=shapely.box(i*T,j*T,(i+1)*T,(j+1)*T)
    sel=(kx0<=i)&(kx1>=i)&(ky0<=j)&(ky1>=j)
    g=[shapely.intersection(S,box)]
    if sel.any(): g.append(shapely.union_all(shapely.buffer(shapely.points(G[sel]),50,quad_segs=4)))
    piece=shapely.intersection(shapely.union_all(g).simplify(10,preserve_topology=True),box)
    piece=shapely.make_valid(piece)
    if not piece.is_empty: tiles[(i,j)]=piece
    if n%200==0: print('tile',n,len(keys),flush=True)
while len(tiles)>1:  # quadtree dissolve: merge 2x2 tile blocks level by level (seams are local)
    grp={}
    for (i,j),g in tiles.items(): grp.setdefault((i//2,j//2),[]).append(g)
    tiles={k:shapely.union_all(v) for k,v in grp.items()}; print('dissolve level',len(tiles),flush=True)
M=next(iter(tiles.values()))
M=shapely.make_valid(M)
if M.geom_type!='MultiPolygon': M=shapely.MultiPolygon([g for g in shapely.get_parts(M) if g.geom_type=='Polygon'])
shapely.prepare(M); Xs,Ys=X[sc],Y[sc]
miss=~np.concatenate([shapely.intersects(M,shapely.points(Xs[i:i+CH],Ys[i:i+CH])) for i in range(0,len(Xs),CH)])
qa['uprn_patched_2m']=int(miss.sum()); print('patch',miss.sum(),flush=True)
if miss.any():  # post-simplification repair: 2 m buffers round points the 10 m simplify cut off
    M=shapely.make_valid(shapely.union_all([M,shapely.union_all(shapely.buffer(shapely.points(Xs[miss],Ys[miss]),2,quad_segs=4))]))
    if M.geom_type!='MultiPolygon': M=shapely.MultiPolygon([g for g in shapely.get_parts(M) if g.geom_type=='Polygon'])
mask=gpd.GeoDataFrame({'name':['map_builtup_mask']},geometry=[M],crs=27700)
print('mask done',flush=True)
parts=shapely.get_parts(M); ptree=shapely.STRtree(parts)
zm=z[z.code.isin(dz_with)].copy()
def clip(g):  # intersect zone only with mask parts that touch it
    idx=ptree.query(g,predicate='intersects')
    return shapely.make_valid(shapely.union_all(shapely.intersection(parts[idx],g))) if len(idx) else shapely.Polygon()
zm['geometry']=[clip(g) for g in zm.geometry.values]
zm['geometry']=zm.geometry.apply(lambda g: shapely.MultiPolygon([p for p in shapely.get_parts(g) if p.geom_type=='Polygon']) if g.geom_type not in('Polygon','MultiPolygon') else g)
print('dz clip done',flush=True)
zm=zm[~zm.geometry.is_empty]
shapely.prepare(M); Xs,Ys=X[sc],Y[sc]; inside=np.concatenate([shapely.intersects(M,shapely.points(Xs[i:i+CH],Ys[i:i+CH])) for i in range(0,len(Xs),CH)])
scot=float(z.area.sum())  # zones tile Scotland
qa.update({'dz2022_total':7392,'dz2022_with_uprn':len(dz_with),'dz2022_masked_rows':len(zm),
 'dz_with_uprn_missing_masked_geom':sorted(dz_with-set(zm.code)),'masked_codes_unique':bool(zm.code.is_unique),
 'masked_codes_subset_of_dz2022':bool(set(zm.code)<=set(z.code)),'uprn_inside_mask_pct':round(100*inside.mean(),4),
 'uprn_outside_mask':int((~inside).sum()),'mask_area_ha':round(M.area/1e4,1),'scotland_area_ha':round(scot/1e4,1),
 'mask_area_pct_scotland':round(100*M.area/scot,3),'mask_polygons':len(M.geoms),'build_date':datetime.date.today().isoformat()})
for p in O.glob('*.gpkg'): p.unlink()
mask.to_file(O/'map_builtup_mask.gpkg',layer='map_builtup_mask',driver='GPKG')
zm[['code','geometry']].to_file(O/'dz2022_masked.gpkg',layer='dz2022_masked',driver='GPKG')
for n,g in (('map_builtup_mask',mask),('dz2022_masked',zm[['code','geometry']])):
    g.to_crs(4326).to_file(O/f'{n}.4326.geojson',driver='GeoJSON',COORDINATE_PRECISION=6)
qa['files']={p.name:{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(O.glob('*')) if p.suffix in('.gpkg','.geojson')}
json.dump(qa,open(O/'qa_builtup_mask.json','w'),indent=1); print(json.dumps(qa,indent=1))
