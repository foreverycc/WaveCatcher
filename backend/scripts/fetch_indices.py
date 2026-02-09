import pandas as pd
import os
import requests
import io

def get_html_content(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.content

def fetch_sp500():
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    content = get_html_content(url)
    tables = pd.read_html(io.BytesIO(content))
    df = tables[0]
    stocks = df['Symbol'].tolist()
    # Replace dots with dashes for compatibility (e.g. BRK.B -> BRK-B)
    stocks = [s.replace('.', '-') for s in stocks]
    return sorted(stocks)

def fetch_nasdaq100():
    url = "https://en.wikipedia.org/wiki/Nasdaq-100"
    content = get_html_content(url)
    tables = pd.read_html(io.BytesIO(content))
    # The table index might vary, usually it's the 4th table (index 4) or search for "Ticker"
    for table in tables:
        if 'Ticker' in table.columns:
            stocks = table['Ticker'].tolist()
            stocks = [s.replace('.', '-') for s in stocks]
            return sorted(stocks)
        elif 'Symbol' in table.columns: # fallback if column name differs
             stocks = table['Symbol'].tolist()
             stocks = [s.replace('.', '-') for s in stocks]
             return sorted(stocks)
    return []

def fetch_russell2000():
    url = "https://www.ishares.com/us/products/239710/ishares-russell-2000-etf/1467271812596.ajax?fileType=csv&fileName=IWM_holdings&dataType=fund"
    content = get_html_content(url)
    # The CSV usually has 9 lines of header info before the actual table
    try:
        df = pd.read_csv(io.BytesIO(content), skiprows=9)
    except Exception:
        # Fallback: try finding the header line dynamically if skiprows=9 fails (though likely stable)
        df = pd.read_csv(io.BytesIO(content), header=0) # naive try
    
    if 'Ticker' not in df.columns:
        # If header wasn't found at line 10, try reading with no header and finding the row with 'Ticker'
        df = pd.read_csv(io.BytesIO(content), header=None)
        # Find row index where first column is 'Ticker'
        header_row = df[df[0] == 'Ticker'].index
        if not header_row.empty:
            df = pd.read_csv(io.BytesIO(content), skiprows=header_row[0]+1, header=None)
            # Re-read with correct header? Or just set columns?
            # Easier to re-read
            df = pd.read_csv(io.BytesIO(content), skiprows=header_row[0])
            
    if 'Ticker' in df.columns:
        stocks = df['Ticker'].dropna().tolist()
        # Filter out non-string or placeholders
        stocks = [str(s) for s in stocks if s != '-' and isinstance(s, str)]
        stocks = [s.replace('.', '-') for s in stocks]
        return sorted(list(set(stocks)))
    return []

def fetch_dowjones():
    url = "https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average"
    content = get_html_content(url)
    tables = pd.read_html(io.BytesIO(content))
    # Find the table with stock components
    for table in tables:
        if 'Symbol' in table.columns:
            stocks = table['Symbol'].tolist()
            stocks = [s.replace('.', '-') for s in stocks]
            return sorted(stocks)
        elif 'Ticker' in table.columns:
            stocks = table['Ticker'].tolist()
            stocks = [s.replace('.', '-') for s in stocks]
            return sorted(stocks)
    return []

def save_to_tab(stocks, filename):
    # Ensure data directory exists
    os.makedirs('data', exist_ok=True)
    filepath = os.path.join('data', filename)
    with open(filepath, 'w') as f:
        for stock in stocks:
            f.write(f"{stock}\n")
    print(f"Saved {len(stocks)} tickers to ./backend/{filepath}")

if __name__ == "__main__":
    print("Fetching S&P 500...")
    try:
        sp500 = fetch_sp500()
        save_to_tab(sp500, 'stocks_sp500.tab')
    except Exception as e:
        print(f"Error fetching S&P 500: {e}")

    print("Fetching Nasdaq 100...")
    try:
        nasdaq100 = fetch_nasdaq100()
        save_to_tab(nasdaq100, 'stocks_nasdaq100.tab')
    except Exception as e:
        print(f"Error fetching Nasdaq 100: {e}")

    print("Fetching Russell 2000...")
    try:
        russell2000 = fetch_russell2000()
        save_to_tab(russell2000, 'stocks_russell2000.tab')
    except Exception as e:
        print(f"Error fetching Russell 2000: {e}")

    print("Fetching Dow Jones 30...")
    try:
        dowjones = fetch_dowjones()
        save_to_tab(dowjones, 'stocks_dowjones.tab')
    except Exception as e:
        print(f"Error fetching Dow Jones 30: {e}")
