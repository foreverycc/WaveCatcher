import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from app.db.database import SessionLocal, Base, engine
from app.db.models import OptionChain
from sqlalchemy import desc

# Ensure tables exist (simple migration for now)
Base.metadata.create_all(bind=engine)

def get_option_data(ticker_symbol: str):
    """
    Fetch option chain data, using DB cache if available.
    """
    db = SessionLocal()
    try:
        ticker = yf.Ticker(ticker_symbol)
        
        # Get expiration dates
        try:
            expirations = ticker.options
        except Exception as e:
            print(f"No options found for {ticker_symbol}: {e}")
            return None

        if not expirations:
            return None

        # Helper to parse date
        def parse_date(d_str):
            return datetime.strptime(d_str, '%Y-%m-%d')

        today = datetime.now()
        exp_dates = [parse_date(d) for d in expirations]

        # 1. Nearest Expiration
        nearest_date = expirations[0]

        # 2. Next Week (Closest to Today + 7 days)
        target_week = today + timedelta(days=7)
        week_date_obj = min(exp_dates, key=lambda d: abs(d - target_week))
        week_date = week_date_obj.strftime('%Y-%m-%d')
        
        # 3. Next Month (Closest to Today + 30 days)
        target_month = today + timedelta(days=30)
        month_date_obj = min(exp_dates, key=lambda d: abs(d - target_month))
        month_date = month_date_obj.strftime('%Y-%m-%d')

        targets = {
            'nearest': nearest_date,
            'week': week_date,
            'month': month_date
        }
        
        unique_dates = list(set(targets.values()))
        chain_cache = {}

        current_price = None
        try:
             current_price = ticker.fast_info.last_price
        except:
             try:
                 hist = ticker.history(period='1d')
                 if not hist.empty:
                     current_price = hist['Close'].iloc[-1]
             except:
                 pass
        
        if current_price is None:
            # Try to get from last DB entry if API fails? 
            # For now just set 0 or use basic invalid
            current_price = 0.0

        for d in unique_dates:
            # Check DB Cache (valid for 1 hour?)
            cutoff_time = datetime.utcnow() - timedelta(hours=1)
            cached_entry = db.query(OptionChain).filter(
                OptionChain.ticker == ticker_symbol,
                OptionChain.expiration == d,
                OptionChain.scrape_date >= cutoff_time
            ).order_by(desc(OptionChain.scrape_date)).first()

            if cached_entry:
                # Check if cache includes 'pain' data (for backward compatibility upgrade)
                has_pain = False
                if cached_entry.data and len(cached_entry.data) > 0:
                    if 'pain' in cached_entry.data[0]:
                        has_pain = True
                
                if has_pain:
                    print(f"DEBUG: Using cached options for {ticker_symbol} exp {d}")
                    chain_cache[d] = {
                        'data': cached_entry.data,
                        'max_pain': cached_entry.max_pain
                    }
                else:
                    print(f"DEBUG: Cache for {ticker_symbol} exp {d} missing pain data, refreshing...")
                    cached_entry = None # Force refresh
            
            if not cached_entry:
                # Fetch fresh
                try:
                    chain = ticker.option_chain(d)
                    calls = chain.calls[['strike', 'openInterest']].rename(columns={'openInterest': 'calls'})
                    puts = chain.puts[['strike', 'openInterest']].rename(columns={'openInterest': 'puts'})
                    
                    merged = pd.merge(calls, puts, on='strike', how='outer').fillna(0)
                    
                    # Cleanup
                    if (merged['calls'].sum() == 0) and (merged['puts'].sum() == 0):
                        chain_cache[d] = {'data': [], 'max_pain': None}
                        # Don't cache empty? Or cache it to prevent spamming API?
                        # Let's not cache empty result so we retry next time, 
                        # OR cache it for a shorter time. For now, just skip saving.
                        continue

                    # Calculate Max Pain and Pain Curve
                    strikes = merged['strike'].values
                    call_ois = merged['calls'].values
                    put_ois = merged['puts'].values
                    
                    min_pain_value = float('inf')
                    max_pain_strike = None
                    pain_values = []
                    
                    if len(strikes) > 0:
                        max_pain_strike, pain_values = calculate_max_pain(strikes, call_ois, put_ois)
                    else:
                        max_pain_strike, pain_values = None, []
                    
                    # Add pain curve to data
                    merged['pain'] = pain_values
                    merged = merged.sort_values('strike')
                    chain_data = merged.to_dict(orient='records')
                    
                    # Save to DB
                    new_entry = OptionChain(
                        ticker=ticker_symbol,
                        expiration=d,
                        scrape_date=datetime.utcnow(),
                        data=chain_data,
                        current_price=float(current_price) if current_price else 0.0,
                        max_pain=float(max_pain_strike) if max_pain_strike else None
                    )
                    db.add(new_entry)
                    db.commit()
                    
                    chain_cache[d] = {
                        'data': chain_data,
                        'max_pain': max_pain_strike
                    }
                    
                except Exception as e:
                    print(f"Error fetching chain for {d}: {e}")
                    chain_cache[d] = {'data': [], 'max_pain': None}

        db.close()

        return {
            "current_price": current_price,
            "nearest": {
                "date": targets['nearest'], 
                "data": chain_cache.get(targets['nearest'], {}).get('data', []),
                "max_pain": chain_cache.get(targets['nearest'], {}).get('max_pain')
            },
            "week": {
                "date": targets['week'], 
                "data": chain_cache.get(targets['week'], {}).get('data', []),
                "max_pain": chain_cache.get(targets['week'], {}).get('max_pain')
            },
            "month": {
                "date": targets['month'], 
                "data": chain_cache.get(targets['month'], {}).get('data', []),
                "max_pain": chain_cache.get(targets['month'], {}).get('max_pain')
            }
        }

    except Exception as e:
        print(f"Error in get_option_data: {e}")
        return None

def calculate_max_pain(strikes, calls, puts):
    """
    Calculate max pain strike and pain curve.
    
    Args:
        strikes: Array of strike prices
        calls: Array of call open interest
        puts: Array of put open interest
        
    Returns:
        tuple: (max_pain_strike, pain_values_list)
    """
    if len(strikes) == 0:
        return None, []
        
    min_pain_value = float('inf')
    max_pain_strike = None
    pain_values = []
    
    for price_point in strikes:
        # Intrinsic value of calls at this price point (if price < strike, val is 0)
        # Call holders lose nothing if price < strike (option expires worthless)
        # Error in logic in previous code?
        # Standard Max Pain Formula:
        # For a given expiration price P:
        # Call Pain (Intrinsic Value) = Max(0, P - Strike) * Open Interest
        # Put Pain (Intrinsic Value) = Max(0, Strike - P) * Open Interest
        # The Market Makers want to Minimize this total payout.
        
        # Previous logic:
        # call_loss = np.maximum(0, price_point - strikes) * call_ois
        # If 'price_point' is the hypothetical stock price at expiration.
        # Yes, that matches.
        
        call_loss = np.maximum(0, price_point - strikes) * calls
        put_loss = np.maximum(0, strikes - price_point) * puts
        
        # Multiply by 100 because each contract is 100 shares
        total_pain = np.sum(call_loss + put_loss) * 100
        
        pain_values.append(float(total_pain))
        
        if total_pain < min_pain_value:
            min_pain_value = total_pain
            max_pain_strike = price_point
            
    return max_pain_strike, pain_values

def process_options_csv(file_path):
    """
    Process option data from CSV file.
    Expects columns: symbol,type,strike,expiration_date,last_price,bid,mid,ask,volume,open_interest,...
    """
    try:
        # Read CSV
        df = pd.read_csv(file_path)
        
        # Clean numeric columns (remove commas)
        numeric_cols = ['strike', 'last_price', 'bid', 'mid', 'ask', 'volume', 'open_interest']
        for col in numeric_cols:
            if col in df.columns and df[col].dtype == 'object':
                df[col] = df[col].astype(str).str.replace(',', '').apply(pd.to_numeric, errors='coerce').fillna(0)
                
        # Normalize types
        df['type'] = df['type'].str.upper().str.strip()
        
        # Filter mostly relevant checks? No, take all.
        
        # We need to restructure to standardized format:
        # List of Check: strike, calls, puts, pain
        # But separate rows for CALL and PUT in CSV.
        
        # Pivot or Group
        # Create separate DFs
        calls_df = df[df['type'].str.contains('CALL')].set_index('strike')['open_interest']
        puts_df = df[df['type'].str.contains('PUT')].set_index('strike')['open_interest']
        
        # Align indexes (strikes)
        # Use outer join concept via pandas
        merged = pd.DataFrame({'calls': calls_df, 'puts': puts_df}).fillna(0).sort_index()
        merged.index.name = 'strike'
        merged = merged.reset_index()
        
        # Calculate Max Pain
        strikes = merged['strike'].values
        call_ois = merged['calls'].values
        put_ois = merged['puts'].values
        
        max_pain, pain_values = calculate_max_pain(strikes, call_ois, put_ois)
        
        merged['pain'] = pain_values
        
        # Convert to records
        data = merged.to_dict(orient='records')
        
        return {
            "data": data,
            "max_pain": max_pain
        }
        
    except Exception as e:
        print(f"Error processing CSV {file_path}: {e}")
        return None
