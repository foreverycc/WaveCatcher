import pandas as pd
import os
import requests
import io
import re
import json

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, '..', 'data'))

def get_html_content(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
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
    url = "https://en.wikipedia.org/wiki/List_of_NASDAQ-100_companies"
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
    url = "https://www.ishares.com/us/products/239710/ishares-russell-2000-etf/latest-holdings.csv"
    content = get_html_content(url)
    # The CSV has several lines of fund info before the actual table;
    # locate the header line starting with "Ticker" dynamically.
    text = content.decode("utf-8-sig", errors="replace")
    lines = text.splitlines()
    header_idx = next((i for i, l in enumerate(lines) if l.startswith('"Ticker"') or l.startswith('Ticker')), None)
    if header_idx is None:
        return []
    df = pd.read_csv(io.StringIO("\n".join(lines[header_idx:])), on_bad_lines="skip")

    if 'Ticker' in df.columns:
        stocks = df['Ticker'].dropna().tolist()
        # Filter out non-string or placeholders
        stocks = [str(s) for s in stocks if s != '-' and isinstance(s, str)]
        stocks = [s.replace('.', '-') for s in stocks]
        return sorted(list(set(stocks)))
    return []

def _clean_tickers(values):
    stocks = [str(s).strip() for s in values if isinstance(s, str)]
    stocks = [s for s in stocks if s and s != '-' and not s[0].isdigit()]
    stocks = [s.replace('.', '-') for s in stocks]
    return sorted(set(stocks))

def fetch_ishares_holdings(url, min_weight=None):
    """Fetch equity tickers from an iShares latest-holdings.csv URL.

    If min_weight is given, only holdings with Weight (%) above it are kept.
    """
    content = get_html_content(url)
    lines = content.decode("utf-8-sig", errors="replace").splitlines()
    header_idx = next((i for i, l in enumerate(lines) if l.startswith('"Ticker"') or l.startswith('Ticker')), None)
    if header_idx is None:
        return []
    df = pd.read_csv(io.StringIO("\n".join(lines[header_idx:])), on_bad_lines="skip")
    if 'Ticker' not in df.columns:
        return []
    if 'Asset Class' in df.columns:
        df = df[df['Asset Class'] == 'Equity']
    if min_weight is not None and 'Weight (%)' in df.columns:
        weights = pd.to_numeric(df['Weight (%)'].astype(str).str.replace(',', ''), errors='coerce')
        df = df[weights > min_weight]
    return _clean_tickers(df['Ticker'].dropna().tolist())

def fetch_soxx():
    return fetch_ishares_holdings("https://www.ishares.com/us/products/239705/ishares-phlx-semiconductor-etf/latest-holdings.csv")

def fetch_igv():
    # Only keep holdings with weight over 0.5%
    return fetch_ishares_holdings("https://www.ishares.com/us/products/239771/ishares-expanded-tech-software-sector-etf/latest-holdings.csv", min_weight=0.5)


def fetch_nasa():
    """Tema Space Innovators ETF (NASA). The holdings CSV URL is date-stamped, so find it on the fund page."""
    import re
    import html
    page = get_html_content("https://temaetfs.com/nasa").decode("utf-8", errors="replace")
    links = re.findall(r'https://temaetfs\.com/hubfs/Website/Holdings/NASA-holdings-[^"\'\s<>]*\.csv[^"\'\s<>]*', page)
    if not links:
        return []
    df = pd.read_csv(io.BytesIO(get_html_content(html.unescape(links[0]))), on_bad_lines="skip")
    if 'ticker' not in df.columns:
        return []
    # Keep anything listed on a US exchange, regardless of country of domicile
    # (e.g. MDA, STM). Names listed only abroad use Bloomberg-style tickers with an
    # exchange code after a space ("FTC LN", "3491 TT"), as does the "SPACEX SPV" line.
    if 'is_cash' in df.columns:
        df = df[df['is_cash'].astype(str).isin(['0', 'False', 'false'])]
    tickers = _clean_tickers(df['ticker'].dropna().tolist())
    return sorted(t for t in tickers if ' ' not in t)

def fetch_roundhill_holdings(account):
    """Fetch US-listed equity tickers for a Roundhill ETF (e.g. 'LYTE', 'DRAM').

    Roundhill publishes one daily CSV with all its funds (column 'Account'),
    named by date. Walk back from today until a file is found.
    """
    from datetime import date, timedelta
    base = "https://www.roundhillinvestments.com/assets/data/FilepointRoundhill.40RU.RU_Holdings_{}.csv"
    df = None
    for back in range(15):
        url = base.format((date.today() - timedelta(days=back)).strftime('%m%d%Y'))
        try:
            content = get_html_content(url)
        except requests.RequestException:
            continue
        if content.lstrip().startswith(b'<'):  # HTML error page, not the CSV
            continue
        df = pd.read_csv(io.BytesIO(content), on_bad_lines="skip")
        break
    if df is None or 'Account' not in df.columns:
        return []
    df = df[df['Account'] == account]
    # Drop money-market funds, cash lines, T-bills and swaps (e.g. "BD761B9 TRS ... GS").
    df = df[df['MoneyMarketFlag'].isna() | (df['MoneyMarketFlag'] != 'Y')]
    df = df[~df['CUSIP'].astype(str).str.startswith('CASH')]
    df = df[~df['SecurityName'].astype(str).str.contains('SWAP|Treasury', case=False, regex=True)]
    tickers = _clean_tickers(df['StockTicker'].dropna().tolist())
    # Keep US-listed tickers only: plain letters. Foreign lines look like "3081 TT" / "300308 C2".
    return sorted(t for t in tickers if re.fullmatch(r'[A-Z]{1,5}(-[A-Z])?', t))

def fetch_lyte():
    return fetch_roundhill_holdings('LYTE')

def fetch_dram():
    return fetch_roundhill_holdings('DRAM')

def fetch_qtup():
    """Defiance Long Pure Quantum ETF (QTUP). Full holdings table published as HTML on /qtup-full-holdings/."""
    url = "https://www.defianceetfs.com/qtup-full-holdings/"
    content = get_html_content(url)
    tables = pd.read_html(io.BytesIO(content))
    if not tables:
        return []
    df = tables[0]
    if 'Ticker' not in df.columns:
        return []
    # Drop money market / cash lines
    df = df[~df['Ticker'].astype(str).str.contains('FGXXX|Cash', case=False, regex=True)]
    # Drop swap lines (e.g. 74768A104-TRS-03/31/33-L-QTUP)
    df = df[~df['Ticker'].astype(str).str.contains('TRS|SWAP', case=False, regex=True)]
    tickers = _clean_tickers(df['Ticker'].dropna().tolist())
    # Keep US-listed tickers: standard 1-5 letter symbols
    return sorted(t for t in tickers if re.fullmatch(r'[A-Z]{1,5}(-[A-Z])?', t))

def fetch_kweb():
    """KraneShares CSI China Internet ETF (KWEB).
    
    The holdings CSV URL is date-stamped on kraneshares.com/kweb/.
    Maps HK-listed internet giants (e.g. 9988 Alibaba, 700 Tencent) to their corresponding US ADR tickers.
    """
    page = get_html_content("https://kraneshares.com/kweb/").decode("utf-8", errors="replace")
    links = re.findall(r'https://kraneshares\.com/csv/[0-9_]+kweb_holdings\.csv', page)
    if not links:
        return []
    
    content = get_html_content(links[0])
    df = pd.read_csv(io.BytesIO(content), skiprows=1)
    if 'Ticker' not in df.columns:
        return []

    # Map HK-listed codes to their liquid US ADR symbols
    hk_to_us = {
        '700': 'TCEHY',   # Tencent Holdings
        '9988': 'BABA',   # Alibaba Group
        '3690': 'MPNGY',  # Meituan
        '9999': 'NTES',   # NetEase
        '992': 'LNVGY',   # Lenovo Group
        '2423': 'BEKE',   # KE Holdings (Beike)
        '9618': 'JD',     # JD.com
        '9961': 'TCOM',   # Trip.com Group
        '9888': 'BIDU',   # Baidu
        '1024': 'KUASF',  # Kuaishou Technology
        '9626': 'BILI',   # Bilibili
        '9698': 'GDS',    # GDS Holdings
        '3896': 'KC',     # Kingsoft Cloud
    }

    result = []
    for _, row in df.iterrows():
        raw_tk = str(row['Ticker']).strip()
        if raw_tk in hk_to_us:
            result.append(hk_to_us[raw_tk])
        elif re.fullmatch(r'[A-Z]{1,5}(-[A-Z])?', raw_tk):
            result.append(raw_tk)

    return _clean_tickers(result)

def fetch_xbi():
    url = "https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/etfs/us/holdings-daily-us-en-xbi.xlsx"
    content = get_html_content(url)
    raw = pd.read_excel(io.BytesIO(content), header=None)
    header_rows = raw.index[raw[1] == 'Ticker'].tolist()
    if not header_rows:
        return []
    h = header_rows[0]
    tickers = raw.iloc[h + 1:, 1].dropna().tolist()
    return _clean_tickers(tickers)

def fetch_dowjones():
    url = "https://en.wikipedia.org/wiki/List_of_Dow_Jones_Industrial_Average_companies"
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

def load_index_whitelist(filename, field='whitelist'):
    """Load whitelist (or blacklist, with field='blacklist') tickers for any index mapped to
    this stock list filename."""
    config_path = os.path.join(DATA_DIR, 'index_config.json')
    if not os.path.exists(config_path):
        return []
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        whitelists = []
        for entry in config.values():
            if entry.get('stock_list') == filename:
                for t in entry.get(field, []):
                    if t and str(t).strip():
                        whitelists.append(str(t).strip().upper().replace('.', '-'))
        return whitelists
    except Exception as e:
        print(f"Warning: could not load index {field} from {config_path}: {e}")
        return []

# Companies listed with more than one share class: the classes trade almost identically, so keeping
# both double-counts the company in breadth and market-cap weights. Drop the left one, keep the right one.
SHARE_CLASS_DUPLICATES = {
    'GOOG': 'GOOGL',   # Alphabet C / A
    'FOX': 'FOXA',     # Fox B / A
    'NWS': 'NWSA',     # News Corp B / A
    'BRK-A': 'BRK-B',  # Berkshire Hathaway
    'BF-A': 'BF-B',    # Brown-Forman
    'LEN-B': 'LEN',    # Lennar
    'HEI-A': 'HEI',    # HEICO
    'ZG': 'Z',         # Zillow
    'UA': 'UAA',       # Under Armour C / A
    'BATRA': 'BATRK',  # Atlanta Braves Holdings
    'BELFA': 'BELFB',  # Bel Fuse
    'CENT': 'CENTA',   # Central Garden & Pet
    'GLIBA': 'GLIBK',  # GCI Liberty
    'LILA': 'LILAK',   # Liberty Latin America
    'RUSHB': 'RUSHA',  # Rush Enterprises
    'GEF-B': 'GEF',    # Greif
    'MOG-B': 'MOG-A',  # Moog
    'BH-A': 'BH',      # Biglari Holdings
    'CRD-B': 'CRD-A',  # Crawford & Co
    'KELYB': 'KELYA',  # Kelly Services
    'LBRDA': 'LBRDK',  # Liberty Broadband
    'FWONA': 'FWONK',  # Liberty Formula One
    'QRTEB': 'QRTEA',  # QVC Group
    'CWEN-A': 'CWEN',  # Clearway Energy
    'GTN-A': 'GTN',    # Gray Media
    'AGM-A': 'AGM',    # Farmer Mac
    'STZ-B': 'STZ',    # Constellation Brands
    'TAP-A': 'TAP',    # Molson Coors
    'MKC-V': 'MKC',    # McCormick
    'BIO-B': 'BIO',    # Bio-Rad
}


def normalize_ticker(t):
    """Yahoo spelling: upper case, class suffix with '-' (BRK.B / 'GEF B' -> BRK-B / GEF-B)."""
    return re.sub(r'[.\s]+', '-', str(t).strip().upper())


def drop_share_class_duplicates(tickers):
    """Remove the duplicate share class of a company when the list also holds its main class."""
    present = set(tickers)
    dropped = [t for t in tickers if SHARE_CLASS_DUPLICATES.get(t) in present]
    if dropped:
        print(f"Dropped duplicate share classes: {', '.join(f'{t} (kept {SHARE_CLASS_DUPLICATES[t]})' for t in dropped)}")
    return [t for t in tickers if t not in dropped]


def save_to_tab(stocks, filename):
    whitelist = load_index_whitelist(filename)
    combined = list(stocks)
    if whitelist:
        combined.extend(whitelist)
        print(f"Merged whitelist ({len(whitelist)} tickers: {', '.join(whitelist)}) into {filename}")

    # Deduplicate and sort
    final_stocks = sorted(list(dict.fromkeys(
        normalize_ticker(s) for s in combined if s and str(s).strip()
    )))
    final_stocks = drop_share_class_duplicates(final_stocks)
    blacklist = set(load_index_whitelist(filename, 'blacklist'))
    if blacklist:
        blocked = [s for s in final_stocks if s in blacklist]
        final_stocks = [s for s in final_stocks if s not in blacklist]
        if blocked:
            print(f"Removed blacklisted tickers from {filename}: {', '.join(blocked)}")

    os.makedirs(DATA_DIR, exist_ok=True)
    filepath = os.path.join(DATA_DIR, filename)
    with open(filepath, 'w') as f:
        for stock in final_stocks:
            f.write(f"{stock}\n")
    print(f"Saved {len(final_stocks)} tickers to {filepath}")

if __name__ == "__main__":
    import sys
    
    # If arguments are provided, only fetch those indices
    # Valid keys: sp500, nasdaq100, dowjones, russell2000, soxx, xbi, igv, nasa, lyte, dram, qtup, kweb
    selected = set(sys.argv[1:]) if len(sys.argv) > 1 else {'sp500', 'nasdaq100', 'dowjones', 'russell2000', 'soxx', 'xbi', 'igv', 'nasa', 'lyte', 'dram', 'qtup', 'kweb'}
    
    if 'sp500' in selected:
        print("Fetching S&P 500...")
        try:
            sp500 = fetch_sp500()
            save_to_tab(sp500, 'stocks_sp500.tab')
        except Exception as e:
            print(f"Error fetching S&P 500: {e}")

    if 'nasdaq100' in selected:
        print("Fetching Nasdaq 100...")
        try:
            nasdaq100 = fetch_nasdaq100()
            save_to_tab(nasdaq100, 'stocks_nasdaq100.tab')
        except Exception as e:
            print(f"Error fetching Nasdaq 100: {e}")

    if 'russell2000' in selected:
        print("Fetching Russell 2000...")
        try:
            russell2000 = fetch_russell2000()
            save_to_tab(russell2000, 'stocks_russell2000.tab')
        except Exception as e:
            print(f"Error fetching Russell 2000: {e}")

    if 'dowjones' in selected:
        print("Fetching Dow Jones 30...")
        try:
            dowjones = fetch_dowjones()
            save_to_tab(dowjones, 'stocks_dowjones.tab')
        except Exception as e:
            print(f"Error fetching Dow Jones 30: {e}")

    for key, fn, fname, label in [
        ('soxx', fetch_soxx, 'stocks_soxx.tab', 'SOXX'),
        ('xbi', fetch_xbi, 'stocks_xbi.tab', 'XBI'),
        ('igv', fetch_igv, 'stocks_saas.tab', 'IGV'),
        ('nasa', fetch_nasa, 'stocks_space.tab', 'NASA'),
        ('lyte', fetch_lyte, 'stocks_light.tab', 'LYTE'),
        ('dram', fetch_dram, 'stocks_storage.tab', 'DRAM'),
        ('qtup', fetch_qtup, 'stocks_quantum.tab', 'QTUP'),
        ('kweb', fetch_kweb, 'stocks_zhonggai.tab', 'KWEB'),
    ]:
        if key in selected:
            print(f"Fetching {label}...")
            try:
                save_to_tab(fn(), fname)
            except Exception as e:
                print(f"Error fetching {label}: {e}")

