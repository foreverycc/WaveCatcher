"""
Debug: Query the DB directly to check BZ signals and KWEB breadth data.
"""
import sqlite3
import json
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "wavecatcher.db")

def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # 1. Find the latest completed analysis run
    cur.execute("""
        SELECT id, stock_list_name, timestamp, status
        FROM analysis_runs
        WHERE status = 'completed'
        ORDER BY timestamp DESC
        LIMIT 3
    """)
    runs = cur.fetchall()
    print("=== Latest Analysis Runs ===")
    for r in runs:
        print(f"  id={r['id']}  stock_list={r['stock_list_name']}  time={r['timestamp']}")
    
    if not runs:
        print("No completed runs found!")
        return
    
    latest_run_id = runs[0]['id']
    stock_list = runs[0]['stock_list_name']
    print(f"\nUsing run_id={latest_run_id} ({stock_list})")
    
    # 2. Check cd_signal_breadth_by_interval
    for ticker_key in [stock_list, "ALL"]:
        cur.execute("""
            SELECT data FROM analysis_results
            WHERE run_id = ? AND result_type = 'cd_signal_breadth_by_interval' AND ticker = ?
        """, (latest_run_id, ticker_key))
        row = cur.fetchone()
        if row:
            data = json.loads(row['data'])
            feb20 = [d for d in data if d.get('date', '').startswith('2026-02-20')]
            print(f"\ncd_signal_breadth_by_interval (ticker={ticker_key}):")
            print(f"  Total entries: {len(data)}")
            if feb20:
                for e in feb20:
                    print(f"  Feb 20: {e}")
            else:
                print(f"  ⚠️ No Feb 20 entry! Last 3:")
                for e in data[-3:]:
                    print(f"    {e}")
        else:
            print(f"\ncd_signal_breadth_by_interval (ticker={ticker_key}): NOT FOUND")
    
    # 3. Check raw cd_breakout_candidates_details_1234 for BZ
    cur.execute("""
        SELECT data FROM analysis_results
        WHERE run_id = ? AND result_type = 'cd_breakout_candidates_details_1234' AND ticker = 'ALL'
    """, (latest_run_id,))
    row = cur.fetchone()
    if row:
        data = json.loads(row['data'])
        bz = [d for d in data if d.get('ticker') == 'BZ']
        bz_feb = [d for d in bz if '2026-02' in str(d.get('signal_date', ''))]
        print(f"\nBZ in cd_breakout_candidates_details_1234:")
        print(f"  Total BZ results: {len(bz)}")
        if bz_feb:
            print(f"  BZ Feb 2026 signals:")
            for d in bz_feb:
                print(f"    interval={d.get('interval')}  signal_date={d.get('signal_date')}  is_hq={d.get('is_hq', 'N/A')}  score={d.get('indicator_score')}")
        else:
            print(f"  ⚠️ No BZ signals in Feb 2026")
            if bz:
                print(f"  Last 5 BZ results:")
                for d in bz[-5:]:
                    print(f"    interval={d.get('interval')}  signal_date={d.get('signal_date')}")
    else:
        print(f"\ncd_breakout_candidates_details_1234: NOT FOUND")
    
    # 4. Check cd_market_breadth_1234 (HQ breadth)
    for ticker_key in [stock_list, "ALL"]:
        cur.execute("""
            SELECT data FROM analysis_results
            WHERE run_id = ? AND result_type = 'cd_market_breadth_1234' AND ticker = ?
        """, (latest_run_id, ticker_key))
        row = cur.fetchone()
        if row:
            data = json.loads(row['data'])
            feb20 = [d for d in data if d.get('date', '').startswith('2026-02-20')]
            print(f"\ncd_market_breadth_1234 (ticker={ticker_key}):")
            print(f"  Total entries: {len(data)}")
            if feb20:
                for e in feb20:
                    print(f"  Feb 20: {e}")
            else:
                print(f"  Last 3:")
                for e in data[-3:]:
                    print(f"    {e}")
        else:
            print(f"\ncd_market_breadth_1234 (ticker={ticker_key}): NOT FOUND")
    
    # 5. Quick check: what result types exist for this run?
    cur.execute("""
        SELECT DISTINCT result_type, ticker FROM analysis_results
        WHERE run_id = ?
        ORDER BY result_type, ticker
    """, (latest_run_id,))
    print(f"\n=== All result types for run {latest_run_id} ===")
    for r in cur.fetchall():
        print(f"  {r['result_type']}  ticker={r['ticker']}")
    
    conn.close()

if __name__ == "__main__":
    main()
