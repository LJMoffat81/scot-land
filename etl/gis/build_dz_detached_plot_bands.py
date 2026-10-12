"""dz_detached_plot_bands: plot (parcel) size bands for detached houses, per data zone (2011 + 2022).
INTERNAL publish level (derived from RoS INSPIRE parcels; OS INSPIRE end-user terms not yet cleared).
Universe: latest domestic EPC per OSG UPRN; BUILT_FORM='Detached'; PROPERTY_TYPE in (House, Bungalow).
Cohorts: post1980 = age band 1984-1991 .. 2008 onwards, or TYPE_OF_ASSESSMENT='SAP, new dwelling' (no age band; lodged on construction 2010+);
         pre1980  = before 1919 .. 1965-1975.  '1976-1983' straddles 1980 and is excluded from both (counted in QA).
Parcel = smallest residential INSPIRE parcel containing the UPRN point. Excluded: parcel holding >1 residential UPRN
(multi_address), smallest parcel >2 ha (capped, as in dz_residential_land), no parcel (unmatched).
Bands: lt005 = <0.05 ha; 005_010 = 0.05-0.10 ha (inclusive); gt010 = >0.10 ha (to the 2 ha cap). Shares/median blank if n<5."""
import duckdb, pandas as pd, numpy as np, geopandas as gpd, json, sys
sys.path.insert(0,'/workspace/scotland-gis/scripts'); from zone_rules import check_codes
from pathlib import Path
B=Path('/workspace/scotland-gis'); R=B/'raw'; W=B/'work'; OUT=B/'out'
con=duckdb.connect(str(W/'epc.duckdb'),read_only=True)
e=con.execute("""select uprn, BUILT_FORM bf, PROPERTY_TYPE pt, CONSTRUCTION_AGE_BAND ab, TYPE_OF_ASSESSMENT ta from (
  select *, try_cast(OSG_REFERENCE_NUMBER as bigint) uprn, row_number() over (partition by try_cast(OSG_REFERENCE_NUMBER as bigint)
     order by try_cast(LODGEMENT_DATE as date) desc, REPORT_REFERENCE_NUMBER desc nulls last) rn
  from latest where try_cast(OSG_REFERENCE_NUMBER as bigint) is not null) where rn=1""").df()
POST={'1984-1991','1992-1998','1999-2002','2003-2007','2008 onwards'}; PRE={'before 1919','1919-1929','1930-1949','1950-1964','1965-1975'}
det=e[(e.bf=='Detached')&e.pt.isin(['House','Bungalow'])].copy()
det['cohort']=np.select([det.ab.isin(POST)|(det.ta=='SAP, new dwelling'),det.ab.isin(PRE),det.ab=='1976-1983'],['post1980','pre1980','straddle_1976_1983'],'unknown_age')
qa={'latest_per_uprn':len(e),'detached_house_bungalow':len(det),'cohorts':det.cohort.value_counts().to_dict(),
    'post1980_from_sap_new_dwelling':int(((det.ta=='SAP, new dwelling')&~det.ab.isin(POST)).sum())}
det=det[det.cohort.isin(['post1980','pre1980'])]
pairs=pd.read_parquet(W/'uprn_parcel_pairs.parquet')
sm=pairs.sort_values('area_m2').drop_duplicates('uprn')   # smallest containing parcel
det=det.merge(sm[['uprn','area_m2','n_uprn']],on='uprn',how='left')
det['ha']=det.area_m2/1e4
det['status']=np.select([det.area_m2.isna(),det.n_uprn>1,det.ha>2.0],['unmatched','multi_address','capped'],'matched')
pts=pd.read_parquet(W/'res_uprn.parquet'); det=det.merge(pts,on='uprn',how='inner')
G=gpd.GeoDataFrame(det,geometry=gpd.points_from_xy(det.x,det.y),crs=27700)
def bands(g):
    m=g[g.status=='matched']; n=len(m); o={'n_matched':n}
    for b,(lo,hi) in {'lt005':(-1,0.05),'005_010':(0.05,0.10),'gt010':(0.10,99)}.items():
        x=((m.ha>=lo)&(m.ha<hi)).sum() if b=='lt005' else (((m.ha>=lo)&(m.ha<=hi)).sum() if b=='005_010' else (m.ha>lo).sum())
        o[f'share_{b}']=x/n if n>=5 else np.nan
    o['median_parcel_ha']=m.ha.median() if n>=5 else np.nan
    for s in ['multi_address','capped','unmatched']: o[f'n_excl_{s}']=int((g.status==s).sum())
    return pd.Series(o)
qa['national']={}
for c,g in det.groupby('cohort'):
    s=bands(g); qa['national'][c]={k:(round(float(v),4) if isinstance(v,float) else int(v)) for k,v in s.items()}
    qa['national'][c]['matched_rate']=round(float((g.status=='matched').mean()),4)
    qa['national'][c]['parcel_ha_quantiles_matched']={str(q):round(float(g[g.status=='matched'].ha.quantile(q)),4) for q in [.1,.25,.5,.75,.9]}
out=[]
for v,f,cc in [(2011,'SG_DataZoneBdry_2011/SG_DataZone_Bdry_2011.shp','DataZone'),(2022,'SG_DataZoneBdry_2022/SG_DataZone_Bdry_2022.shp','dzcode')]:
    z=gpd.read_file(R/f)[[cc,'geometry']].rename(columns={cc:'code'})
    j=gpd.sjoin(G[['cohort','status','ha','geometry']],z,predicate='within')
    t=j.groupby(['code','cohort']).apply(bands,include_groups=False).unstack('cohort')
    t.columns=[f'{c}_{k}' for k,c in t.columns]
    t=t.reindex(z.code.sort_values()); t.index.name='code'; t=t.reset_index(); t.insert(1,'vintage',v); out.append(t)
o=pd.concat(out)
cols=['code','vintage']
for c in ['post1980','pre1980']:
    o[f'{c}_n_matched']=o[f'{c}_n_matched'].fillna(0)
    for s in ['multi_address','capped','unmatched']: o[f'{c}_n_excl_{s}']=o[f'{c}_n_excl_{s}'].fillna(0).astype(int)
    o[f'{c}_n_matched']=o[f'{c}_n_matched'].astype(int)
    cols+=[f'{c}_n_matched',f'{c}_share_lt005',f'{c}_share_005_010',f'{c}_share_gt010',f'{c}_median_parcel_ha',f'{c}_n_excl_multi_address',f'{c}_n_excl_capped',f'{c}_n_excl_unmatched']
o=o[cols].rename(columns={'post1980_n_matched':'n_detached_post1980_matched','pre1980_n_matched':'n_detached_pre1980_matched'})
RANGE={2011:('S01006506','S01013481'),2022:('S01013482','S01020873')}
for v,g in o.groupby('vintage'): assert g.code.between(*RANGE[v]).all() and len(g)=={2011:6976,2022:7392}[v]
for c in ['post1980','pre1980']:
    s=o[[f'{c}_share_lt005',f'{c}_share_005_010',f'{c}_share_gt010']].sum(axis=1,min_count=3)
    qa[f'{c}_share_sum_maxerr']=float((s.dropna()-1).abs().max())
    qa[f'{c}_zones_with_shares']={str(v):int(g[f'{c}_share_lt005'].notna().sum()) for v,g in o.groupby('vintage')}
check_codes(o); o.to_csv(OUT/'dz_detached_plot_bands.csv',index=False,float_format='%.6g')
json.dump(qa,open(OUT/'qa_dz_detached_plot_bands.json','w'),indent=1); print(json.dumps(qa,indent=1)); print(len(o))
