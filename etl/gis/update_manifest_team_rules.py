"""Replace ONLY the six GIS rows rebuilt under the 6 Oct 2026 team rules; add the loader's mandatory `attribution` column.
Re-reads manifest.csv immediately before the atomic write; rows owned by other workers / files are left untouched,
except dz_residential_land.csv, whose attribution is filled only if blank (copied from its README 'Licences' section)."""
import pandas as pd, hashlib, os, tempfile
from pathlib import Path
G=Path('/workspace/scotland-gis/data/processed/gis'); M=G/'manifest.csv'
sha=lambda p: hashlib.sha256(open(p,'rb').read()).hexdigest()
nrows=lambda p: len(pd.read_csv(p,dtype=str,keep_default_na=False))
DZB='SG Data Zone boundaries 2011 and 2022, Scottish Government, OGL v3 (contains OS data © Crown copyright and database right 2026)'
SPD='NRS Scottish Postcode Directory 2026/2 Postcode Index, OGL v3 (contains NRS data © Crown copyright and database right 2026; contains OS data © Crown copyright and database right 2026)'
DWY='Scot-LAND Data Zones dwellings_by_year (NRS household estimates by Data Zone, council-tax dwellings Sep 2025, OGL v3; contains NRS data © Crown copyright 2026)'
BRMA='Scottish Government Broad Rental Market Areas 2009 (maps.gov.scot), OGL v3 (© Scottish Government; contains OS data © Crown copyright and database right 2026)'
C22='NRS Census 2022, OGL v3 (© Crown copyright 2026)'
PARK='Scottish Government designated National Park boundaries (Cairngorms 2010, Loch Lomond & The Trossachs 2002; maps.gov.scot), OGL v3 (© Scottish Government; contains OS data © Crown copyright and database right 2026)'
EPC='Energy Performance Certificates (domestic EPC register, data.gov.scot), Scottish Government, OGL v3 (address fields incorporate PAF® data © Royal Mail Group Ltd; used in-box only for postcode-to-zone placement, no address data published)'
OA22='NRS Census 2022 Output Area population-weighted centroids (WFS CEN2022:OutputAreaCent2022), OGL v3 (Copyright NRS; contains OS data © Crown copyright and database right 2026)'
SRC_DW='; dwelling denominator = Scot-LAND Data Zones dwellings_by_year dwellings_total, count_year 2025 (NRS council-tax dwellings, Sept 2025)'
ROWS={
 'epc_dz_rollup.csv':dict(
   source='Scottish Government domestic EPC register (data.gov.scot, Dec 2008-Jun 2026) + NRS Scottish Postcode Directory 2026/2'+SRC_DW+'; recent10_* = certificates lodged 2016-07-01..2026-06-30; floor-area mean/sum and house/flat means (10-1500 m2 filter)',
   attribution='; '.join([EPC,SPD,DWY,DZB])),
 'dz_brma_share.csv':dict(source=None,attribution='; '.join([BRMA,C22+' household counts via '+SPD,DZB])),
 'dz_park_overlay.csv':dict(source=None,attribution='; '.join([PARK,C22+' household counts via '+SPD,DZB])),
 'alt/dz_brma_share_oa2022.csv':dict(source=None,attribution='; '.join([BRMA,OA22,C22+' OA household counts',SPD+' (OA-to-zone lookup)',DZB])),
 'alt/dz_brma_share_dwelling_bounds.csv':dict(
   source='dz_brma_share.csv split zones + Scot-LAND Data Zones dwellings_by_year (dwellings_total/occupied/second_homes, count_year 2025 = NRS council-tax dwellings, Sept 2025); share_mid = renormalised midpoint of bounds (Georgist v0.5 rule)',
   attribution='; '.join([BRMA,C22+' household counts via '+SPD,DWY,DZB])),
 'alt/dz_park_overlay_dwelling_bounds.csv':dict(
   source='dz_park_overlay.csv + Scot-LAND Data Zones dwellings_by_year (dwellings_total/occupied/second_homes, count_year 2025 = NRS council-tax dwellings, Sept 2025); share_mid = midpoint of bounds, not renormalised (Georgist v0.5 rule)',
   attribution='; '.join([PARK,C22+' household counts via '+SPD,DWY,DZB])),
}
RES_ATTR=('RoS INSPIRE Cadastral Parcels, OGL v3 + OS INSPIRE end-user licence (© Crown copyright and database right 2026; © Registers of Scotland); '
 'OS Open UPRN, OS OpenData licence (contains OS data © Crown copyright and database right 2026); Energy Performance Certificates, Scottish Government, OGL v3; '
 'NRS Census 2022 Settlements, OGL v3 (Copyright NRS; contains OS data © Crown copyright and database right 2026); NRS dwelling estimates, OGL v3; '+DWY+'; '+DZB)
# compute row values first (slow part), then re-read and write
calc={f:(str(nrows(G/f)),sha(G/f)) for f in ROWS}
cur=pd.read_csv(M,dtype=str,keep_default_na=False)
if 'attribution' not in cur.columns: cur.insert(cur.columns.get_loc('licence')+1,'attribution','')
missing=set(ROWS)-set(cur.file); assert not missing, missing
for f,v in ROWS.items():
    i=cur.index[cur.file==f]; assert len(i)==1, f
    if v['source']: cur.loc[i,'source']=v['source']
    cur.loc[i,'attribution']=v['attribution']; cur.loc[i,'zone_vintage']='2011;2022'
    cur.loc[i,'rows'],cur.loc[i,'sha256']=calc[f]
j=cur.index[(cur.file=='dz_residential_land.csv')&(cur.attribution=='')]
cur.loc[j,'attribution']=RES_ATTR
fd,tmp=tempfile.mkstemp(dir=G,suffix='.tmp'); os.close(fd); cur.to_csv(tmp,index=False); os.chmod(tmp,0o644); os.replace(tmp,M)
print(cur[['file','owner','zone_vintage','rows','sha256']].assign(sha256=cur.sha256.str[:8]).to_string()); print('attribution blank:',cur.loc[cur.attribution=='','file'].tolist())
