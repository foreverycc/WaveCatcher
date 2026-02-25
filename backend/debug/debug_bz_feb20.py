"""
Debug: BZ CD signals — data truncated to Feb 20 vs full data to Feb 24.
Does adding Feb 21-24 data change the Feb 20 signals?
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'app', 'logic'))

import pandas as pd
from indicators import compute_cd_indicator, compute_cd_break_through
from data_loader import download_stock_data

TICKER = "BZ"
CUTOFF = "2026-02-21"

def truncate_all(data, end_date):
    end_ts = pd.Timestamp(end_date)
    out = {}
    for interval, df in data.items():
        if df.empty:
            out[interval] = df
            continue
        if df.index.tz is not None:
            end_tz = end_ts.tz_localize('UTC').tz_convert(df.index.tz)
        else:
            end_tz = end_ts
        out[interval] = df[df.index.date <= end_tz.date()].copy()
    return out

def analyze(data, label):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    for interval in ['1h', '2h', '3h', '4h', '1d']:
        df = data.get(interval, pd.DataFrame())
        if df.empty:
            continue
        cd = compute_cd_indicator(df).fillna(False).infer_objects(copy=False).astype(bool)
        feb = [d for d in df.index[cd] if '2026-02' in str(d)]
        print(f"  [{interval}] {len(df)} bars, ends={df.index[-1]}, CD in Feb: {len(feb)}")
        for d in feb:
            c = df.loc[d, 'Close']
            if isinstance(c, pd.Series): c = c.iloc[0]
            print(f"    {d}  Close={c:.2f}")

def main():
    print(f"Downloading {TICKER}...")
    raw = download_stock_data(TICKER)
    
    trunc = truncate_all(raw, CUTOFF)
    
    analyze(trunc, f"Truncated to {CUTOFF}")
    analyze(raw, f"Full data (to today)")
    
    # Diff
    print(f"\n{'='*60}")
    print(f"  DIFFERENCES on Feb 20")
    print(f"{'='*60}")
    for interval in ['1h', '2h', '3h', '4h', '1d']:
        df_t = trunc.get(interval, pd.DataFrame())
        df_f = raw.get(interval, pd.DataFrame())
        if df_t.empty or df_f.empty:
            continue
        cd_t = compute_cd_indicator(df_t).fillna(False).infer_objects(copy=False).astype(bool)
        cd_f = compute_cd_indicator(df_f).fillna(False).infer_objects(copy=False).astype(bool)
        
        common = cd_t.index.intersection(cd_f.index)
        t_vals = cd_t.reindex(common, fill_value=False)
        f_vals = cd_f.reindex(common, fill_value=False)
        diffs = t_vals != f_vals
        
        feb20_diffs = [d for d in common[diffs] if '2026-02-20' in str(d)]
        all_diffs = [d for d in common[diffs] if '2026-02' in str(d)]
        
        if all_diffs:
            print(f"  [{interval}] ⚠️ {len(all_diffs)} diffs in Feb:")
            for d in all_diffs:
                print(f"    {d}  trunc={t_vals[d]}  full={f_vals[d]}")
        else:
            print(f"  [{interval}] ✅ No diffs in Feb")

if __name__ == "__main__":
    main()
