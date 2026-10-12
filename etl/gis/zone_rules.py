"""Shared Scot-LAND team rules (agreed 6 Oct 2026 in the Scot-LAND room).
- vintage is the whole number 2011 or 2022 (never 'DZ2011'/'DZ2022').
- codes must sit in the official range for their vintage.
- the dwelling denominator is Scot-LAND Data Zones' dwellings_by_year.dwellings_total for count_year 2025,
  joined on (code, vintage). A zone with no 2025 count is flagged, never filled from another year."""
import pandas as pd
RANGE={2011:('S01006506','S01013481'),2022:('S01013482','S01020873')}
NZONES={2011:6976,2022:7392}
VINT={'DZ2011':2011,'DZ2022':2022}
COUNT_YEAR=2025
DW_FILE='/workspace/scotland-datazones/data/processed/datazones/dwellings_by_year.csv'
DW_SOURCE='Scot-LAND Data Zones dwellings_by_year (NRS council-tax dwellings, Sept 2025), count_year 2025'

def check_codes(df,code='code',vintage='vintage'):
    """Assert vintage is int 2011/2022 and every code is inside its vintage's official range."""
    assert pd.api.types.is_integer_dtype(df[vintage]), f'vintage dtype {df[vintage].dtype} is not integer'
    assert set(df[vintage].unique())<=set(RANGE), f'bad vintage values {set(df[vintage].unique())-set(RANGE)}'
    for v,g in df.groupby(vintage):
        lo,hi=RANGE[v]; c=g[code].astype(str)
        bad=g[~(c.str.match(r'^S01\d{6}$')&(c>=lo)&(c<=hi))]
        assert bad.empty, f'{len(bad)} codes out of official range for {v}: {bad[code].head().tolist()}'

def dwellings_2025():
    """Data Zones dwellings for count_year 2025: code, vintage(int), dwellings_total, occupied, vacant, second_homes, dz_flags."""
    d=pd.read_csv(DW_FILE,usecols=['code','vintage','count_year','dwellings_total','occupied','vacant','second_homes','flags'],
                  dtype={'code':str,'flags':str})
    d=d[d.count_year==COUNT_YEAR].drop(columns='count_year').rename(columns={'flags':'dz_flags'})
    d['vintage']=d.vintage.astype(int)
    assert not d.duplicated(['code','vintage']).any()
    check_codes(d)
    return d

def dwellings_flag(total):
    """'' if a positive 2025 count exists; 'zero_dwellings_2025' if the count is 0; 'missing_count_2025' if no row/NaN (never filled)."""
    return pd.Series(['missing_count_2025' if pd.isna(x) else ('zero_dwellings_2025' if x==0 else '') for x in total],index=total.index)
