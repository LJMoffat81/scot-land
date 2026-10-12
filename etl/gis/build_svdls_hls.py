"""Build SVDLS (vacant & derelict) and HLS (housing land supply) site layers + Data Zone rollups.
Master list: gov.scot SVDLS Site Register 2025 (points, hectares).  Geometry order per site
(room decision — Spatial Hub survey > RoS title outline > point; tagged geom_provenance):
  a) spatialhub_polygon / spatialhub_buffer  → geometry_source spatialhub_survey
     (Spatial Hub VDL polygon matched on local authority + site_code)
  b) ros_inspire_outline  → geometry_source ros_title_outline
     (RoS INSPIRE title containing the grid ref, area within +/-30% of register ha; INTERNAL)
  c) point_sized          → geometry_source point
     (circle at the grid ref with area = register ha)
Canonical tags/precedence: backend/layers/svdls_geometry.py
Cross-list duplicates: HLS polygon overlapping an SVDLS site by >=50% of the smaller shape -> flagged both ways.
Zone rollups: area-of-overlap allocation (footprint_area) to DZ2011 + DZ2022, point-on-surface/nearest fallback.
All geometry EPSG:27700.  vintage = integer 2011 / 2022."""
import json, re, glob, numpy as np, pandas as pd, geopandas as gpd, shapely, pyogrio
from pathlib import Path
B=Path('/workspace/scotland-gis'); R=B/'raw'; O=B/'out'; W=B/'work/svdls'; W.mkdir(parents=True,exist_ok=True)
CRS=27700; TOL=0.30; DUP=0.50; REF_YEAR=2025
qa={}

# ---------------- register ----------------
raw=pd.read_excel(R/'svdls/SVDLS_2025_Register.ods',sheet_name='Site_Register',engine='odf',header=None,dtype=str)
hdr=raw.index[raw.iloc[:,0].astype(str).str.strip().eq('Planning Authority')][0]
reg=raw.iloc[hdr+1:].copy(); reg.columns=[str(c).strip() for c in raw.iloc[hdr]]
reg=reg[reg['Site Code'].notna()].reset_index(drop=True)
reg=reg.rename(columns={'Planning Authority':'local_auth','Site Code':'site_code','Site Name (If Supplied)':'site_name',
 'Address (If Supplied)':'address','East':'east','North':'north','Site Size (Hectares)':'ha_register','Site Type':'site_type',
 'Location of Site':'location','Owner 1':'owner_1','Owner 2':'owner_2','Period when site became Vacant or Derelict':'period',
 'Previous Use of Site':'previous_use','Development Potential':'dev_potential','Data Zone':'register_dz2011'})
for c in reg.columns: reg[c]=reg[c].astype(str).str.strip().replace({'nan':None})
for c in ['east','north','ha_register']: reg[c]=pd.to_numeric(reg[c])
LA_FIX={'Loch Lomond and the Trossachs National Park':'Loch Lomond and Trossachs National Park','Na h-Eileanan Siar':'Na h-Eileanan an Iar'}
reg['la']=reg.local_auth.replace(LA_FIX)
norm=lambda s: s.astype(str).str.upper().str.replace(r'\s+',' ',regex=True).str.strip()
reg['k']=reg.la+'|'+norm(reg.site_code)
assert not reg.k.duplicated().any()
reg['is_derelict']=reg.site_type.eq('Derelict'); reg['is_vacant']=~reg.is_derelict
reg['in_published_scope']=reg.is_derelict|reg.location.str.contains('equal to or over 2,000')  # SG headline = derelict + urban vacant (settlements >=2,000)
def yr(p):
    if p is None or p=='Unknown': return np.nan
    m=re.findall(r'\d{4}',p); return float(m[-1]) if m else np.nan   # upper year of band ('1980 or earlier' -> 1980)
reg['period_upper_year']=reg.period.map(yr)
reg['unused_15plus']=reg.period_upper_year<=REF_YEAR-15
reg['period_unknown']=reg.period_upper_year.isna()
qa['register_rows']=len(reg); qa['register_ha']=round(reg.ha_register.sum(),2)
qa['register_ha_published_scope']=round(reg.loc[reg.in_published_scope,'ha_register'].sum(),2)
qa['register_sites_published_scope']=int(reg.in_published_scope.sum())
qa['published_national_2025']={'total_ha':8591,'derelict_ha':6958,'urban_vacant_ha':1633,'sites':3002,'source':'SVDLS 2025 Tables, Table 2'}

# ---------------- Spatial Hub VDL polygons ----------------
def prep(g):
    g=g.copy(); g['geometry']=shapely.make_valid(g.geometry.values)
    g['geometry']=g.geometry.apply(lambda x: x if x.geom_type in('Polygon','MultiPolygon') else shapely.MultiPolygon([p for p in getattr(x,'geoms',[]) if p.geom_type=='Polygon']) )
    return g
def circ(g):
    pp=4*np.pi*g.area/g.length**2
    nv=shapely.get_num_coordinates(g.geometry.values)
    return pp, nv
vdl=prep(gpd.read_file(R/'spatialhub/Vacant_and_Derelict_Land_-_Scotland/pub_vdlPolygon.shp')); assert vdl.crs.to_epsg()==CRS
vdl['pp'],vdl['nv']=circ(vdl); vdl['is_buffer']=(vdl.pp>0.99)&(vdl.nv>=33)
vdl['k']=vdl.local_auth+'|'+norm(vdl.site_code)
assert not vdl.k.duplicated().any()
m=reg.merge(vdl[['k','geometry','is_buffer','pp','sh_date_up','sh_src_id']],on='k',how='left')
m=gpd.GeoDataFrame(m,geometry='geometry',crs=CRS)
has=m.geometry.notna()&~m.geometry.is_empty
m['geom_provenance']=np.where(has,np.where(m.is_buffer.fillna(False),'spatialhub_buffer','spatialhub_polygon'),None)
qa['spatialhub_vdl_rows']=len(vdl); qa['spatialhub_buffer_shapes_all']=int(vdl.is_buffer.sum())
qa['register_matched_spatialhub']=int(has.sum())
qa['unmatched_by_council']=m.loc[~has].groupby('local_auth').size().sort_values(ascending=False).to_dict()
qa['spatialhub_not_on_2025_register']=int((~vdl.k.isin(reg.k)).sum())
qa['spatialhub_not_on_register_by_council']=vdl.loc[~vdl.k.isin(reg.k)].groupby('local_auth').size().sort_values(ascending=False).to_dict()

# ---------------- RoS INSPIRE outlines for unmatched (and, for QA only, buffered) sites ----------------
pts=gpd.GeoDataFrame(m[['k','ha_register']],geometry=gpd.points_from_xy(m.east,m.north),crs=CRS)
need=m.geom_provenance.isna()|m.geom_provenance.eq('spatialhub_buffer')
zips=sorted(glob.glob(str(R/'inspire/[A-Z][A-Z][A-Z].zip')))
cand=[]
CACHE=W/'inspire_cand.pkl'
if zips and CACHE.exists():
    cand=[pd.read_pickle(CACHE)]; qa['inspire_used']=True; qa['inspire_counties']=len(zips)
elif zips:
    for z in zips:
        c=Path(z).stem; src=f'/vsizip/{z}/{c}_bng.shp'
        x0,y0,x1,y1=pyogrio.read_info(src)['total_bounds']
        q=pts[need.values]; q=q[(q.geometry.x>=x0)&(q.geometry.x<=x1)&(q.geometry.y>=y0)&(q.geometry.y<=y1)]
        if q.empty: continue
        p=gpd.read_file(src,columns=['inspireid'],mask=shapely.MultiPoint(q.geometry.values).buffer(1))
        if p.empty: continue
        p['geometry']=shapely.make_valid(p.geometry.values)
        j=gpd.sjoin(q,p,predicate='within',how='inner')
        j['ros_geom']=p.geometry.loc[j.index_right].values; j['county']=c
        cand.append(pd.DataFrame(j[['k','ha_register','inspireid','county','ros_geom']]))
    qa['inspire_used']=True; qa['inspire_counties']=len(zips)
    if cand: pd.concat(cand).to_pickle(CACHE)
else:
    qa['inspire_used']=False; qa['inspire_note']='no INSPIRE parcels under raw/inspire; step b skipped'
if cand:
    cd=pd.concat(cand); cd['ros_ha']=shapely.area(cd.ros_geom.values)/1e4; cd['ratio']=cd.ros_ha/cd.ha_register
    cd['ok']=(cd.ratio-1).abs()<=TOL; cd['d']=(np.log(cd.ratio)).abs()
    best=cd[cd.ok].sort_values('d').drop_duplicates('k').set_index('k')
    qa['inspire_candidates_sites']=int(cd.k.nunique())
else: best=pd.DataFrame(columns=['inspireid','county','ros_geom','ros_ha','ratio'])
tgt=m.geom_provenance.isna()&m.k.isin(best.index)
m.loc[tgt,'geometry']=gpd.GeoSeries(best.loc[m.loc[tgt,'k'],'ros_geom'].values,index=m.index[tgt],crs=CRS)
m.loc[tgt,'geom_provenance']='ros_inspire_outline'
m['ros_inspireid']=m.k.map(best['inspireid']) if len(best) else None
m.loc[~tgt,'ros_inspireid']=None
bufk=m.geom_provenance.eq('spatialhub_buffer')
qa['unmatched_sites']=int((~has).sum()); qa['inspire_outline_accepted']=int(tgt.sum())
qa['buffered_sites_with_acceptable_inspire_outline_info_only']=int((bufk&m.k.isin(best.index)).sum())
ps=m.geom_provenance.isna()
r_=np.sqrt(m.loc[ps,'ha_register']*1e4/np.pi)
m.loc[ps,'geometry']=gpd.GeoSeries(shapely.buffer(shapely.points(m.loc[ps,'east'],m.loc[ps,'north']),r_,quad_segs=16),index=m.index[ps],crs=CRS)
m.loc[ps,'geom_provenance']='point_sized'
m['ha_geometry']=m.area/1e4; m['area_ratio_geom_to_register']=m.ha_geometry/m.ha_register
qa['provenance_counts']=m.geom_provenance.value_counts().to_dict()
qa['provenance_register_ha']=m.groupby('geom_provenance').ha_register.sum().round(1).to_dict()
def ag(s):
    r=s.area_ratio_geom_to_register; return {'n':len(s),'median_ratio':round(float(r.median()),4),'share_outside_30pct':round(float(((r-1).abs()>TOL).mean()),4),
      'share_ratio_lt_0.7':round(float((r<1-TOL).mean()),4),'share_ratio_gt_1.3':round(float((r>1+TOL).mean()),4)}
qa['area_agreement_spatialhub_polygon']=ag(m[m.geom_provenance.eq('spatialhub_polygon')])
qa['area_agreement_spatialhub_all_matched']=ag(m[m.geom_provenance.isin(['spatialhub_polygon','spatialhub_buffer'])])
qa['area_agreement_all_sites']=ag(m)
qa['buffer_share_of_register_sites']=round(float(bufk.mean()),4)
qa['buffer_share_of_matched_sites']=round(float(bufk.sum()/has.sum()),4)

# ---------------- HLS ----------------
hls=prep(gpd.read_file(R/'spatialhub/Housing_Land_Supply_-_Scotland/pub_hls.shp')); assert hls.crs.to_epsg()==CRS
hls=hls[~hls.geometry.is_empty].reset_index(drop=True)
hls['pp'],hls['nv']=circ(hls); hls['is_buffer']=(hls.pp>0.99)&(hls.nv>=33)
hls['ha_geometry']=hls.area/1e4
hls['hls_uid']=['HLS%05d'%i for i in range(len(hls))]   # row id: site_refer is not unique across phases/years
qa['hls_dup_key_la_siterefer_year']=int(hls.duplicated(['la_s_code','site_refer','hla_year']).sum())
qa['hls_rows']=len(hls); qa['hls_buffer_shapes']=int(hls.is_buffer.sum()); qa['hls_buffer_share']=round(float(hls.is_buffer.mean()),4)
qa['hls_ha_sum']=round(hls.ha_geometry.sum(),1); qa['hls_ha_union']=round(shapely.union_all(hls.geometry.values).area/1e4,1)
qa['hls_buffer_ha']=round(hls.loc[hls.is_buffer,'ha_geometry'].sum(),1)

# ---------------- cross-list duplicates ----------------
s=m[['k','geometry']].reset_index(drop=True); h=hls[['hls_uid','site_refer','geometry']]
j=gpd.sjoin(s,h,predicate='intersects',how='inner')
gi=shapely.intersection(s.geometry.loc[j.index].values,h.geometry.loc[j.index_right].values)
j['ov']=shapely.area(gi); j['smaller']=np.minimum(shapely.area(s.geometry.loc[j.index].values),shapely.area(h.geometry.loc[j.index_right].values))
j=j[j.ov>=DUP*j.smaller]
m['dup_hls_site_refer']=m.k.map(j.groupby('k').site_refer.apply(lambda x:';'.join(sorted(set(map(str,x))))))
code_by_k=m.set_index('k').site_code
hls['dup_svdls_site_code']=hls.hls_uid.map(j.assign(sc=j.k.map(code_by_k)).groupby('hls_uid').sc.apply(lambda x:';'.join(sorted(set(map(str,x))))))
m['dup_hls']=m.dup_hls_site_refer.notna(); hls['dup_svdls']=hls.dup_svdls_site_code.notna()
qa['dup_pairs']=len(j); qa['svdls_sites_flagged_in_hls']=int(m.dup_hls.sum()); qa['svdls_ha_flagged_in_hls']=round(m.loc[m.dup_hls,'ha_register'].sum(),1)
qa['hls_sites_flagged_in_svdls']=int(hls.dup_svdls.sum()); qa['hls_ha_flagged_in_svdls']=round(hls.loc[hls.dup_svdls,'ha_geometry'].sum(),1)
qa['svdls_flagged_by_provenance']=m.loc[m.dup_hls].geom_provenance.value_counts().to_dict()

# ---------------- owner groups ----------------
OWN={'Local Authority':'local_authority','Housing Association':'housing_association',
 'Other Private':'private','Unknown Private':'private','Private Gas':'private','Private Port Company':'private','Private Coal Company':'private',
 'Private Telecommunications':'private','Private Steel':'private','Network Rail/ Rail Franchise Holder':'private','Scottish Power':'private',
 'Ownership unknown':'unknown'}
m['owner_group']=m.owner_1.map(OWN).fillna('other_public')   # remaining categories are public bodies / statutory undertakers / Crown
qa['owner_1_categories']=m.owner_1.value_counts().to_dict()

# ---------------- zones + footprint allocation ----------------
zones={2011:gpd.read_file(R/'SG_DataZoneBdry_2011/SG_DataZone_Bdry_2011.shp',columns=['DataZone'])[['DataZone','geometry']].rename(columns={'DataZone':'code'}),
       2022:gpd.read_file(R/'SG_DataZoneBdry_2022/SG_DataZone_Bdry_2022.shp',columns=['dzcode'])[['dzcode','geometry']].rename(columns={'dzcode':'code'})}
RANGE={2011:(6506,13481),2022:(13482,20873)}
for v,z in zones.items():
    assert z.crs.to_epsg()==CRS; z['geometry']=shapely.make_valid(z.geometry.values)
    n=z.code.str[3:].astype(int); assert z.code.str.match(r'^S01\d{6}$').all() and n.between(*RANGE[v]).all(), v
    assert not z.code.duplicated().any()
def alloc(g,idcol,v):
    z=zones[v]; j=gpd.sjoin(g[[idcol,'geometry']],z,predicate='intersects',how='inner')
    j['a']=shapely.area(shapely.intersection(g.geometry.loc[j.index].values,z.geometry.loc[j.index_right].values))
    j=j[j.a>0][[idcol,'code','a']]
    miss=sorted(set(g[idcol])-set(j[idcol]))
    if miss:  # off-coast / no overlap -> point on surface, nearest zone
        gp=g[g[idcol].isin(miss)].copy(); gp['geometry']=gp.geometry.representative_point()
        nn=gpd.sjoin_nearest(gp[[idcol,'geometry']],z,how='left',distance_col='dist'); nn=nn[~nn.index.duplicated()]
        j=pd.concat([j,pd.DataFrame({idcol:nn[idcol].values,'code':nn.code.values,'a':1.0})])
        qa[f'{idcol}_{v}_pos_fallback']={'n':len(miss),'max_dist_m':round(float(nn.dist.max()),1)}
    j['w']=j.a/j.groupby(idcol).a.transform('sum')
    j['main']=j.w.eq(j.groupby(idcol).w.transform('max')); j.loc[j.duplicated([idcol,'main'])&j.main,'main']=False
    split_on_land=1-j.groupby(idcol).a.sum()/g.set_index(idcol).geometry.area.reindex(j[idcol].unique())
    qa[f'{idcol}_{v}_sites_split_over_zones']=int((j.groupby(idcol).size()>1).sum())
    qa[f'{idcol}_{v}_share_area_outside_zones_median']=round(float(split_on_land.median()),5)
    return j
def stamp(df,v):
    df.insert(1,'vintage',v); return df
# Public rollup uses OGL geometry only: the 27 INSPIRE-outline sites are allocated with their point_sized circle
# (OS INSPIRE end-user terms not yet cleared for derived zone statistics).  The INSPIRE-based variant stays internal.
m_pub=m.copy(); ri=m_pub.geom_provenance.eq('ros_inspire_outline')
m_pub.loc[ri,'geometry']=gpd.GeoSeries(shapely.buffer(shapely.points(m_pub.loc[ri,'east'],m_pub.loc[ri,'north']),
    np.sqrt(m_pub.loc[ri,'ha_register']*1e4/np.pi),quad_segs=16),index=m_pub.index[ri],crs=CRS)
m_pub.loc[ri,'geom_provenance']='point_sized'
def svroll(mm,v,z,provs):
    j=alloc(mm,'k',v).merge(mm.drop(columns='geometry'),on='k')
    w=j.w; f=lambda col: (j[col]*w)
    d=pd.DataFrame({'code':j.code,'main':j.main.astype(int),
      'ha_register':f('ha_register'),'ha_geometry':j.a/1e4,
      'n_derelict':j.main*j.is_derelict,'n_vacant':j.main*j.is_vacant,
      'ha_derelict':w*j.ha_register*j.is_derelict,'ha_vacant':w*j.ha_register*j.is_vacant,
      'ha_published_scope':w*j.ha_register*j.in_published_scope,
      'ha_unused_15plus':w*j.ha_register*j.unused_15plus,'ha_period_unknown':w*j.ha_register*j.period_unknown,
      'n_dup_hls':j.main*j.dup_hls,'ha_dup_hls':w*j.ha_register*j.dup_hls})
    for g in ['local_authority','housing_association','private','other_public','unknown']: d[f'n_owner_{g}']=j.main*j.owner_group.eq(g)
    for p in provs: d[f'ha_register_{p}']=w*j.ha_register*j.geom_provenance.eq(p)
    t=d.groupby('code').sum().rename(columns={'main':'n_sites'})
    t['ha_register_excl_hls_dup']=t.ha_register-t.ha_dup_hls
    t=t.reindex(z.code.sort_values()).fillna(0); t.index.name='code'
    t['crosswalk_method']='footprint_area'; return stamp(t.reset_index(),v), j
sv_out=[]; hl_out=[]; svi_out=[]
for v,z in zones.items():
    t,j=svroll(m_pub,v,z,['spatialhub_polygon','spatialhub_buffer','point_sized']); sv_out.append(t)
    ti,_=svroll(m,v,z,['spatialhub_polygon','spatialhub_buffer','ros_inspire_outline','point_sized']); svi_out.append(ti)
    # HLS
    jh=alloc(hls,'hls_uid',v).merge(hls.drop(columns='geometry'),on='hls_uid')
    dh=pd.DataFrame({'code':jh.code,'n_sites':jh.main.astype(int),'ha_geometry':jh.a/1e4,
       'n_buffered':jh.main*jh.is_buffer,'ha_buffered':jh.a/1e4*jh.is_buffer,
       'n_dup_svdls':jh.main*jh.dup_svdls,'ha_dup_svdls':jh.a/1e4*jh.dup_svdls})
    th=dh.groupby('code').sum(); th['ha_excl_svdls_dup']=th.ha_geometry-th.ha_dup_svdls
    th=th.reindex(z.code.sort_values()).fillna(0); th.index.name='code'
    th['crosswalk_method']='footprint_area'; hl_out.append(stamp(th.reset_index(),v))
    # QA: register DZ2011 code vs our main zone
    if v==2011:
        mz=j[j.main.astype(bool)].set_index('k').code
        qa['register_dz2011_agrees_with_main_overlap_zone']=round(float((m.set_index('k').register_dz2011==mz.reindex(m.k)).mean()),4)
sv=pd.concat(sv_out); hl=pd.concat(hl_out); svi=pd.concat(svi_out)
icols=[c for c in svi.columns if c.startswith('n_')]; svi[icols]=svi[icols].round().astype(int)
icols=[c for c in sv.columns if c.startswith('n_')]; sv[icols]=sv[icols].round().astype(int)
icols=[c for c in hl.columns if c.startswith('n_')]; hl[icols]=hl[icols].round().astype(int)
for v in (2011,2022):
    a=sv[sv.vintage==v]; qa[f'rollup_svdls_{v}']={'rows':len(a),'n_sites':int(a.n_sites.sum()),'ha_register':round(a.ha_register.sum(),2),
        'ha_geometry':round(a.ha_geometry.sum(),2),'ha_derelict':round(a.ha_derelict.sum(),1),'ha_vacant':round(a.ha_vacant.sum(),1),
        'ha_published_scope':round(a.ha_published_scope.sum(),1),'zones_with_sites':int((a.n_sites>0).sum())}
    b=hl[hl.vintage==v]; qa[f'rollup_hls_{v}']={'rows':len(b),'n_sites':int(b.n_sites.sum()),'ha_geometry':round(b.ha_geometry.sum(),1),'zones_with_sites':int((b.n_sites>0).sum())}
(O/'internal').mkdir(exist_ok=True); svi.to_csv(O/'internal/dz_svdls_rollup_with_inspire.csv',index=False,float_format='%.6f')
sv.to_csv(O/'dz_svdls_rollup.csv',index=False,float_format='%.6f'); hl.to_csv(O/'dz_hls_rollup.csv',index=False,float_format='%.6f')

# ---------------- internal gpkgs ----------------
mz11=alloc(m,'k',2011); mz22=alloc(m,'k',2022)
m['dz2011_main']=m.k.map(mz11[mz11.main].set_index('k').code); m['dz2022_main']=m.k.map(mz22[mz22.main].set_index('k').code)
hz11=alloc(hls,'hls_uid',2011); hz22=alloc(hls,'hls_uid',2022)
hls['dz2011_main']=hls.hls_uid.map(hz11[hz11.main].set_index('hls_uid').code); hls['dz2022_main']=hls.hls_uid.map(hz22[hz22.main].set_index('hls_uid').code)
gcols=['local_auth','site_code','site_name','address','east','north','ha_register','ha_geometry','area_ratio_geom_to_register','site_type','location',
 'in_published_scope','owner_1','owner_2','owner_group','period','period_upper_year','unused_15plus','previous_use','dev_potential','register_dz2011',
 'dz2011_main','dz2022_main','geom_provenance','ros_inspireid','sh_src_id','sh_date_up','dup_hls_site_refer','geometry']
out=m[gcols].copy(); out['ros_inspireid']=out.ros_inspireid.astype(object)
out['licence']=np.where(out.geom_provenance.eq('ros_inspire_outline'),'INTERNAL: OS/RoS INSPIRE end-user terms (geometry); OGL v3 (attributes)','OGL v3')
out.to_file(O/'svdls_sites.gpkg',layer='svdls_sites',driver='GPKG')
hc=['hls_uid','site_refer','local_auth','la_s_code','hla_year','epc_count_','ha_geometry','is_buffer','pp','dz2011_main','dz2022_main','dup_svdls_site_code','sh_src_id','sh_date_up','geometry']
hls[hc].rename(columns={'pp':'polsby_popper'}).to_file(O/'hls_sites.gpkg',layer='hls_sites',driver='GPKG')
json.dump(qa,open(O/'qa_svdls_hls.json','w'),indent=1,default=str); print(json.dumps(qa,indent=1,default=str))
