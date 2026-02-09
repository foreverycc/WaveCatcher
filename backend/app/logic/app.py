import streamlit as st
import pandas as pd
import os
import time
from stock_analyzer import analyze_stocks
import re
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode
import numpy as np

# Set page configuration
st.set_page_config(
    page_title="Stock Analysis App",
    page_icon="📈",
    layout="wide"
)

# Initialize session state for selected ticker and interval
if 'selected_ticker' not in st.session_state:
    st.session_state.selected_ticker = None
if 'selected_interval' not in st.session_state:
    st.session_state.selected_interval = None

# Initialize session state for MC page
if 'mc_selected_ticker' not in st.session_state:
    st.session_state.mc_selected_ticker = None
if 'mc_selected_interval' not in st.session_state:
    st.session_state.mc_selected_interval = None

# Function to handle ticker selection
def handle_ticker_selection(ticker, interval):
    st.session_state.selected_ticker = ticker
    st.session_state.selected_interval = interval

# Function to handle MC ticker selection
def handle_mc_ticker_selection(ticker, interval):
    st.session_state.mc_selected_ticker = ticker
    st.session_state.mc_selected_interval = interval

# Page selection
st.sidebar.title("Navigation")
page = st.sidebar.radio("Select Page", ["CD Analysis (抄底)", "MC Analysis (卖出)"])

# Main title
if page == "CD Analysis (抄底)":
    st.title("📈 CD Signal Analysis Dashboard (抄底)")
elif page == "MC Analysis (卖出)":
    st.title("📉 MC Signal Analysis Dashboard (卖出)")

# Load data helper function
def load_data_from_file(file_path):
    """Load data from CSV or tab-separated file"""
    try:
        if file_path.endswith('.csv'):
            return pd.read_csv(file_path)
        else:
            return pd.read_csv(file_path, sep='\t')
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return None

# Helper function to handle ticker selection updates
def update_ticker_selection(new_ticker, new_interval, page_type='cd'):
    """Update ticker selection in session state"""
    if page_type == 'cd':
        if (st.session_state.selected_ticker != new_ticker or 
            st.session_state.selected_interval != new_interval):
            st.session_state.selected_ticker = new_ticker
            st.session_state.selected_interval = new_interval
            st.rerun()
    elif page_type == 'mc':
        if (st.session_state.mc_selected_ticker != new_ticker or 
            st.session_state.mc_selected_interval != new_interval):
            st.session_state.mc_selected_ticker = new_ticker
            st.session_state.mc_selected_interval = new_interval
            st.rerun()

# Function to get Chinese stock name mapping
def get_chinese_stock_mapping():
    """Get mapping of Chinese stock codes to names using akshare."""
    mapping_file = './data/chinese_stocks_mapping.csv'
    
    # Check if the mapping file exists
    if os.path.exists(mapping_file):
        try:
            # Read from existing file
            df = pd.read_csv(mapping_file)
            mapping = {}
            for _, row in df.iterrows():
                code = str(row['code']).zfill(6)  # Ensure 6 digits with leading zeros
                name = row['name']
                # Add different formats that might be used
                mapping[code] = name
                mapping[f"{code}.SH"] = name  # Shanghai
                mapping[f"{code}.SZ"] = name  # Shenzhen
                mapping[f"{code}.SS"] = name  # Shanghai (alternative)
            
            return mapping
        except Exception as e:
            st.warning(f"Failed to read Chinese stock mapping file: {e}")
            return {}
    else:
        # File doesn't exist, fetch from akshare and save
        try:
            import akshare as ak
            df = ak.stock_info_a_code_name()
            
            # Save to file for future use
            os.makedirs('./data', exist_ok=True)
            df.to_csv(mapping_file, index=False)
            st.success(f"Chinese stock mapping saved to {mapping_file}")
            
            # Create a mapping dictionary: code -> name
            mapping = {}
            for _, row in df.iterrows():
                code = str(row['code']).zfill(6)  # Ensure 6 digits with leading zeros
                name = row['name']
                # Add different formats that might be used
                mapping[code] = name
                mapping[f"{code}.SH"] = name  # Shanghai
                mapping[f"{code}.SZ"] = name  # Shenzhen
                mapping[f"{code}.SS"] = name  # Shanghai (alternative)
            return mapping
        except Exception as e:
            st.warning(f"Failed to load Chinese stock names from akshare: {e}")
            return {}

def is_chinese_stock_code(ticker):
    """Check if a ticker is a Chinese stock code (starts with digits)."""
    if not isinstance(ticker, str):
        return False
    # Chinese stock codes typically start with digits and may have .SH/.SZ/.SS suffix
    pattern = r'^\d{6}(\.(SH|SZ|SS))?$'
    return bool(re.match(pattern, ticker))

def replace_chinese_tickers_in_df(df, chinese_mapping):
    """Replace Chinese ticker symbols with names in a dataframe."""
    if df is None or df.empty or 'ticker' not in df.columns:
        return df
    
    df_copy = df.copy()
    
    # Replace ticker symbols with names where applicable
    def replace_ticker(ticker):
        if is_chinese_stock_code(ticker) and ticker in chinese_mapping:
            return f"{chinese_mapping[ticker]} ({ticker})"
        return ticker
    
    df_copy['ticker'] = df_copy['ticker'].apply(replace_ticker)
    return df_copy

def update_output_files_with_chinese_names(chinese_mapping):
    """Update all output files with Chinese stock names."""
    output_dir = './output'
    if not os.path.exists(output_dir) or not chinese_mapping:
        return
    
    updated_files = []
    
    # Get all CSV and TAB files in output directory
    for filename in os.listdir(output_dir):
        if filename.endswith('.csv') or filename.endswith('.tab'):
            file_path = os.path.join(output_dir, filename)
            
            try:
                # Read the file
                if filename.endswith('.csv'):
                    df = pd.read_csv(file_path)
                else:  # .tab files
                    df = pd.read_csv(file_path, sep='\t')
                
                # Check if file has ticker column and Chinese stocks
                if 'ticker' in df.columns:
                    # Check if any Chinese stocks exist in this file
                    has_chinese_stocks = any(is_chinese_stock_code(ticker) for ticker in df['ticker'])
                    
                    if has_chinese_stocks:
                        # Check if names are already applied (avoid double processing)
                        has_names_already = any('(' in str(ticker) and ')' in str(ticker) 
                                               for ticker in df['ticker'] if pd.notna(ticker))
                        
                        if not has_names_already:
                            # Apply Chinese name mapping
                            df_updated = replace_chinese_tickers_in_df(df, chinese_mapping)
                            
                            # Save back to file
                            if filename.endswith('.csv'):
                                df_updated.to_csv(file_path, index=False)
                            else:  # .tab files
                                df_updated.to_csv(file_path, sep='\t', index=False)
                            
                            updated_files.append(filename)
                
            except Exception as e:
                st.warning(f"Error updating file {filename}: {e}")
    
    if updated_files:
        st.success(f"Updated {len(updated_files)} output files with Chinese stock names")
        with st.expander("Updated files:", expanded=False):
            for file in updated_files:
                st.write(f"- {file}")
    else:
        st.info("No output files required Chinese stock name updates")

# SIDEBAR CONFIGURATION
st.sidebar.header("Configuration")

# Stock list selection
stock_list_files = [f for f in os.listdir('./data') if f.endswith('.tab') or f.endswith('.txt')]
selected_file = st.sidebar.selectbox(
    "Select Stock List",
    stock_list_files,
    index=2 if stock_list_files else None
)

# Reset selection when the file changes
if 'current_selected_file' not in st.session_state:
    st.session_state.current_selected_file = selected_file

# Display stock list info in sidebar
if selected_file:
    file_path = os.path.join('./data', selected_file)
    
    try:
        with open(file_path, 'r') as f:
            original_stocks = f.read().strip()
        
        # Show basic info about the selected stock list
        current_stocks_list = original_stocks.strip().splitlines() if original_stocks.strip() else []
        st.sidebar.write(f"📊 {len(current_stocks_list)} stocks")
        if current_stocks_list:
            st.sidebar.write(f"Preview: {', '.join(current_stocks_list[:3])}{'...' if len(current_stocks_list) > 3 else ''}")
        
        # Expandable stock list management section
        with st.sidebar.expander("📋 Manage Stock List", expanded=False):
            # Create tabs for stock list management
            tab_edit, tab_delete, tab_create = st.tabs(["✏️ Edit", "🗑️ Delete", "➕ Create New"])
            
            # Edit tab
            with tab_edit:
                st.write(f"**Editing: {selected_file}**")
                
                # Handle temporary stocks from utility functions
                if 'temp_stocks' in st.session_state:
                    display_stocks = st.session_state.temp_stocks
                    del st.session_state.temp_stocks
                else:
                    display_stocks = original_stocks
                
                # Editable text area for stock list
                edited_stocks = st.text_area(
                    "Stock symbols (one per line):",
                    value=display_stocks,
                    height=200,
                    help="Enter stock symbols, one per line. Changes will be saved when you click 'Save Changes'."
                )
                
                # Save button and status
                col_save, col_status = st.columns([1, 2])
                
                with col_save:
                    if st.button("Save Changes", type="primary"):
                        try:
                            # Save the edited content back to the file
                            with open(file_path, 'w') as f:
                                f.write(edited_stocks.strip())
                            st.success("✅ Saved!")
                            # Force a rerun to refresh the preview
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error saving file: {e}")
                
                with col_status:
                    # Show if there are unsaved changes
                    if edited_stocks.strip() != original_stocks:
                        st.warning("⚠️ Unsaved changes")
                    else:
                        st.info("📄 No changes")
                
                # Utility buttons
                col_util1, col_util2, col_util3 = st.columns(3)
                
                with col_util1:
                    if st.button("Remove Duplicates", help="Remove duplicate stock symbols"):
                        lines = edited_stocks.strip().splitlines()
                        unique_lines = list(dict.fromkeys([line.strip().upper() for line in lines if line.strip()]))
                        st.session_state.temp_stocks = '\n'.join(unique_lines)
                        st.rerun()
                
                with col_util2:
                    if st.button("Sort A-Z", help="Sort stock symbols alphabetically"):
                        lines = edited_stocks.strip().splitlines()
                        sorted_lines = sorted([line.strip().upper() for line in lines if line.strip()])
                        st.session_state.temp_stocks = '\n'.join(sorted_lines)
                        st.rerun()
                
                with col_util3:
                    if st.button("Validate Symbols", help="Check for invalid stock symbols"):
                        lines = edited_stocks.strip().splitlines()
                        invalid_symbols = []
                        valid_symbols = []
                        
                        for line in lines:
                            symbol = line.strip().upper()
                            if symbol:
                                # Basic validation: should be 1-5 characters, letters only
                                if len(symbol) >= 1 and len(symbol) <= 5 and symbol.isalpha():
                                    valid_symbols.append(symbol)
                                else:
                                    invalid_symbols.append(symbol)
                        
                        if invalid_symbols:
                            st.warning(f"⚠️ Potentially invalid symbols: {', '.join(invalid_symbols)}")
                        else:
                            st.success("✅ All symbols appear valid")
                
                # Show preview of current stocks in editor
                current_stocks = edited_stocks.strip().splitlines() if edited_stocks.strip() else []
                if current_stocks:
                    st.write(f"**Preview ({len(current_stocks)} stocks):**")
                    st.write(", ".join(current_stocks[:5]) + ("..." if len(current_stocks) > 5 else ""))
                else:
                    st.write("**Preview:** No stocks in list")
            
            # Delete tab
            with tab_delete:
                st.warning(f"⚠️ This will permanently delete '{selected_file}'")
                
                # Confirmation checkbox
                confirm_delete = st.checkbox(f"I confirm I want to delete '{selected_file}'")
                
                if st.button("Delete Stock List", type="secondary", disabled=not confirm_delete):
                    try:
                        os.remove(file_path)
                        st.success(f"✅ Deleted '{selected_file}' successfully!")
                        st.info("Please refresh the page to update the dropdown.")
                        # Clear the selection by rerunning
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error deleting file: {e}")
            
            # Create new tab
            with tab_create:
                new_file_name = st.text_input(
                    "New file name (without extension):",
                    placeholder="e.g., my_custom_stocks"
                )
                
                new_file_extension = st.selectbox(
                    "File extension:",
                    [".tab", ".txt"],
                    index=0
                )
                
                new_stocks_content = st.text_area(
                    "Stock symbols (one per line):",
                    placeholder="AAPL\nMSFT\nGOOGL\nTSLA",
                    height=150
                )
                
                if st.button("Create Stock List", type="primary"):
                    if new_file_name and new_stocks_content:
                        try:
                            new_file_path = os.path.join('./data', f"{new_file_name}{new_file_extension}")
                            
                            # Check if file already exists
                            if os.path.exists(new_file_path):
                                st.error(f"File '{new_file_name}{new_file_extension}' already exists!")
                            else:
                                # Create the new file
                                with open(new_file_path, 'w') as f:
                                    f.write(new_stocks_content.strip())
                                    
                                    st.success(f"✅ Created '{new_file_name}{new_file_extension}' successfully!")
                                    st.info("Please refresh the page to see the new file in the dropdown.")
                                    
                        except Exception as e:
                            st.error(f"Error creating file: {e}")
                    else:
                        st.error("Please provide both a file name and stock symbols.")
            
    except Exception as e:
        st.sidebar.error(f"Error reading file: {e}")

# Backtesting configuration
st.sidebar.markdown("---")
st.sidebar.header("Backtesting Settings")

# End date picker for backtesting
from datetime import datetime, date
enable_backtesting = st.sidebar.checkbox("Enable Backtesting", value=False, 
                                        help="Enable to analyze data up to a specific date for backtesting")

end_date = None
if enable_backtesting:
    end_date = st.sidebar.date_input(
        "End Date for Analysis",
        value=date.today(),
        max_value=date.today(),
        help="Select the end date for backtesting. Analysis will only use data up to this date."
    )
    
    # Convert date to string for passing to analysis function
    end_date_str = end_date.strftime('%Y-%m-%d')
    st.sidebar.info(f"📅 Data will be truncated to: {end_date_str}")
else:
    st.sidebar.info("🔄 Using current data (live analysis)")

# Run analysis button in sidebar
st.sidebar.markdown("---")
if st.sidebar.button("Run Analysis", use_container_width=True, type="primary"):
    if not selected_file:
        st.sidebar.error("Please select a stock list file first.")
    else:
        file_path = os.path.join('./data', selected_file)
        
        # Show progress
        progress_bar = st.sidebar.progress(0)
        status_text = st.sidebar.empty()
        
        try:
            status_text.text("Starting comprehensive analysis...")
            progress_bar.progress(25)
            
            # Check if the stock list file exists and is readable
            if not os.path.exists(file_path):
                st.sidebar.error(f"Stock list file not found: {file_path}")
                progress_bar.empty()
                status_text.empty()
            elif True:  # Continue with analysis
                # Check if the file has content
                with open(file_path, 'r') as f:
                    content = f.read().strip()
                    if not content:
                        st.sidebar.error("Stock list file is empty.")
                        progress_bar.empty()
                        status_text.empty()
                    else:
                        stock_symbols = content.splitlines()
                        stock_symbols = [s.strip() for s in stock_symbols if s.strip()]
                        
                        if not stock_symbols:
                            st.sidebar.error("No valid stock symbols found in the file.")
                            progress_bar.empty()
                            status_text.empty()
                        else:
                            # Show different status messages based on backtesting mode
                            if enable_backtesting:
                                status_text.text(f"Backtesting {len(stock_symbols)} stocks (up to {end_date_str})...")
                            else:
                                status_text.text(f"Analyzing {len(stock_symbols)} stocks...")
                            progress_bar.progress(50)
                            
                            # Run the consolidated analysis function
                            # Pass end_date if backtesting is enabled
                            analysis_end_date = end_date_str if enable_backtesting else None
                            analyze_stocks(file_path, end_date=analysis_end_date)
                            
                            progress_bar.progress(100)
                            status_text.text("Analysis complete!")
                            time.sleep(1)
                            status_text.empty()
                            progress_bar.empty()
                            
                            if enable_backtesting:
                                st.sidebar.success(f"Backtesting completed successfully for {len(stock_symbols)} stocks (up to {end_date_str})!")
                            else:
                                st.sidebar.success(f"Analysis completed successfully for {len(stock_symbols)} stocks!")
            
        except Exception as e:
            progress_bar.empty()
            status_text.empty()
            
            # More detailed error reporting
            import traceback
            error_details = traceback.format_exc()
            
            st.sidebar.error(f"Error during analysis: {str(e)}")
            
            # Show detailed error in an expander for debugging
            with st.sidebar.expander("🔍 Error Details (for debugging)", expanded=False):
                st.code(error_details, language="python")
                
                # Additional debugging info
                st.write("**Debugging Information:**")
                st.write(f"- Selected file: {selected_file}")
                st.write(f"- File path: {file_path}")
                st.write(f"- File exists: {os.path.exists(file_path)}")
                
                if os.path.exists(file_path):
                    try:
                        with open(file_path, 'r') as f:
                            content = f.read().strip()
                            lines = content.splitlines()
                            st.write(f"- File size: {len(content)} characters")
                            st.write(f"- Number of lines: {len(lines)}")
                            st.write(f"- First few symbols: {lines[:5] if lines else 'None'}")
                    except Exception as read_error:
                        st.write(f"- Error reading file: {read_error}")
            
            # Suggest solutions
            st.sidebar.info("""
            **Possible solutions:**
            1. Check if the stock symbols in your list are valid
            2. Ensure you have internet connection for data download
            3. Try with a smaller stock list first
            4. Check if the stock symbols are properly formatted (one per line)
            """)

# Function to get the latest update time for a stock list
def get_latest_update_time(stock_list_file):
    if not stock_list_file:
        return None
    
    output_dir = './output'
    if not os.path.exists(output_dir):
        return None
    
    # Extract stock list name from file (remove extension)
    stock_list_name = os.path.splitext(stock_list_file)[0]
    
    # Find all result files for this specific stock list (exact match)
    result_files = []
    for f in os.listdir(output_dir):
        if f.endswith('.csv') or f.endswith('.tab'):
            # Simple approach: check if the file ends with the stock list name + extension
            # This handles cases like "breakout_candidates_summary_1234_stocks_all.tab"
            base_name = f.rsplit('.', 1)[0]  # Remove file extension
            if base_name.endswith('_' + stock_list_name) or base_name == stock_list_name:
                result_files.append(f)
    
    if not result_files:
        return None
    
    # Get the most recent modification time
    latest_time = 0
    for file in result_files:
        file_path = os.path.join(output_dir, file)
        mod_time = os.path.getmtime(file_path)
        if mod_time > latest_time:
            latest_time = mod_time
    
    return latest_time

# Results section header with stock list indicator
if selected_file:
    latest_time = get_latest_update_time(selected_file)
    if latest_time:
        import datetime
        
        try:
            # Try to use pytz for PST conversion
            import pytz
            utc_time = datetime.datetime.fromtimestamp(latest_time, tz=pytz.UTC)
            pst_tz = pytz.timezone('US/Pacific')
            pst_time = utc_time.astimezone(pst_tz)
            formatted_time = pst_time.strftime("%Y-%m-%d %H:%M:%S PST")
        except ImportError:
            # Fallback: manually adjust for PST (UTC-8, or UTC-7 during DST)
            # This is a simple approximation
            utc_time = datetime.datetime.fromtimestamp(latest_time)
            pst_time = utc_time - datetime.timedelta(hours=8)  # Approximate PST
            formatted_time = pst_time.strftime("%Y-%m-%d %H:%M:%S PST")
        
        # Show backtesting indicator if enabled
        if enable_backtesting:
            st.header(f"📊 Backtesting Results for: {selected_file} (Data up to: {end_date_str})")
            st.info(f"🔍 **Backtesting Mode**: Results shown use historical data up to {end_date_str}. Last updated: {formatted_time}")
        else:
            st.header(f"Results for: {selected_file} (Last updated: {formatted_time})")
    else:
        if enable_backtesting:
            st.header(f"📊 Backtesting Results for: {selected_file} (Data up to: {end_date_str})")
            st.warning("⚠️ **Backtesting Mode**: No results found. Please run analysis first.")
        else:
            st.header(f"Results for: {selected_file} (No results found)")
else:
    st.header("Results")
    st.info("Please select a stock list to view corresponding results.")

# Function to load and display results
def load_results(file_pattern, stock_list_file=None, default_sort=None):
    # Look in output directory for result files
    output_dir = './output'
    if not os.path.exists(output_dir):
        return None, "No output directory found. Please run an analysis first."
    
    # Extract stock list name from file (remove extension)
    if stock_list_file:
        stock_list_name = os.path.splitext(stock_list_file)[0]
        # Look for files that match both the pattern and the stock list
        result_files = [f for f in os.listdir(output_dir) 
                       if f.startswith(file_pattern) and stock_list_name in f]
    else:
        # Fallback to original behavior if no stock list specified
        result_files = [f for f in os.listdir(output_dir) if f.startswith(file_pattern)]
    
    if not result_files:
        if stock_list_file:
            return None, f"No results found for stock list '{stock_list_file}'. Please run analysis first."
        else:
            return None, "No results found. Please run an analysis first."
    
    # Get the most recent file
    latest_file = max(result_files, key=lambda f: os.path.getctime(os.path.join(output_dir, f)))
    file_path = os.path.join(output_dir, latest_file)
    
    try:
        # Determine file type and load accordingly
        if latest_file.endswith('.csv'):
            df = pd.read_csv(file_path)
        else:  # .tab files
            df = pd.read_csv(file_path, sep='\t')
            
        if default_sort and default_sort in df.columns:
            df = df.sort_values(by=default_sort, ascending=False)
            
        return df, latest_file
    except Exception as e:
        return None, f"Error loading results: {e}"

# ============================
# CD ANALYSIS PAGE
# ============================
if page == "CD Analysis (抄底)":

    # Load Chinese stock mapping once for all tables
    chinese_stock_mapping = get_chinese_stock_mapping() if selected_file else {}

    # Update output files with Chinese names if mapping is available
    if chinese_stock_mapping and selected_file:
        update_output_files_with_chinese_names(chinese_stock_mapping)

    # Create two columns for the two table views
    if selected_file:
        st.subheader("Waikiki Model")
        
        # Add shared ticker filter for Waikiki model
        waikiki_ticker_filter = st.text_input("Filter by ticker symbol:", key=f"waikiki_ticker_filter_{selected_file}")

        waikiki_viz_col, waikiki_tables_col = st.columns([1, 1])

        with waikiki_viz_col:
            # Load the detailed results for period information
            detailed_df, _ = load_results('cd_eval_custom_detailed_', selected_file)
            
            # Load the returns distribution data for boxplots
            returns_df, _ = load_results('cd_eval_returns_distribution_', selected_file)
            
            if detailed_df is None or 'ticker' not in detailed_df.columns:
                st.info("Please run an analysis first to view visualizations and period returns.")
            else:
                # Use selected ticker and interval from session state
                ticker_filter = st.session_state.selected_ticker if st.session_state.selected_ticker else ""
                selected_interval = st.session_state.selected_interval if st.session_state.selected_interval else '1d'
                
                # If no ticker is selected, automatically select the first one from the best intervals (50) data
                if not ticker_filter:
                    best_50_df, _ = load_results('cd_eval_best_intervals_50_', selected_file, 'avg_return_10')
                    if best_50_df is not None and not best_50_df.empty:
                        first_row = best_50_df.iloc[0]
                        ticker_filter = first_row['ticker']
                        selected_interval = first_row['interval']
                        # Update session state
                        st.session_state.selected_ticker = ticker_filter
                        st.session_state.selected_interval = selected_interval

                # Filter the detailed DataFrame with exact match for ticker and interval
                filtered_detailed = detailed_df[
                    (detailed_df['ticker'] == ticker_filter) &
                    (detailed_df['interval'] == selected_interval)
                ]
                
                if not filtered_detailed.empty:
                    selected_ticker = filtered_detailed.iloc[0]

                    # Visualization Panel
                    # Create figure with subplots: price on top, volume on bottom
                    fig = make_subplots(
                        rows=2, cols=1,
                        subplot_titles=('Price Movement', 'Volume'),
                        vertical_spacing=0.1,
                        row_heights=[0.7, 0.3]
                    )
                    
                    # Filter returns distribution data for selected ticker and interval
                    if returns_df is not None and not returns_df.empty:
                        filtered_returns = returns_df[
                            (returns_df['ticker'] == ticker_filter) &
                            (returns_df['interval'] == selected_interval)
                        ]
                        
                        if not filtered_returns.empty:
                            # Get periods that have data
                            periods_with_data = sorted(filtered_returns['period'].unique())
                            
                            # Add price boxplots for each period
                            median_price_values = []
                            median_periods = []
                            
                            # Add volume bars for each period
                            volume_periods = []
                            avg_volumes = []
                            
                            for period in periods_with_data:
                                period_data = filtered_returns[filtered_returns['period'] == period]
                                period_returns = period_data['return'].values
                                
                                if len(period_returns) > 0:
                                    # Convert returns to relative price (baseline = 100)
                                    relative_prices = 100 + period_returns
                                    
                                    # Add price boxplot
                                    fig.add_trace(go.Box(
                                        y=relative_prices,
                                        x=[period] * len(relative_prices),
                                        name=f'Period {period}',
                                        boxpoints=False,  # Don't show individual points
                                        showlegend=False,
                                        marker=dict(color='lightgray'),
                                        line=dict(color='lightgray')
                                    ))
                                    
                                    # Store median for connecting line
                                    median_price_values.append(100 + np.median(period_returns))
                                    median_periods.append(period)
                                
                                # Add volume data if available
                                if 'volume' in period_data.columns:
                                    period_volumes = period_data['volume'].values
                                    if len(period_volumes) > 0:
                                        avg_volume = np.mean(period_volumes[~np.isnan(period_volumes)])
                                        volume_periods.append(period)
                                        avg_volumes.append(avg_volume)
                            
                            # Add median price connection line
                            if len(median_price_values) > 1:
                                fig.add_trace(go.Scatter(
                                    x=median_periods,
                                    y=median_price_values,
                                    mode='lines+markers',
                                    line=dict(color='gray', width=1),
                                    marker=dict(color='gray', size=6),
                                    name='Median Returns',
                                    showlegend=True
                                ))
                            
                            # Add volume bars (grey bars for average volumes)
                            if len(avg_volumes) > 0:
                                fig.add_trace(go.Bar(
                                    x=volume_periods,
                                    y=avg_volumes,
                                    name='Average Volume',
                                    marker_color='lightgray',
                                    showlegend=True
                                ), row=2, col=1)
                        else:
                            # Fallback to original scatter plot if no returns distribution data
                            periods = [0] + list(range(1, 101))  # Full range from 0 to 100
                            stock_returns = [(0, 100)]  # Start with (0, 100)
                            for period in periods[1:]:  # Skip 0 as we already added it
                                if f'avg_return_{period}' in selected_ticker:
                                    stock_returns.append((period, 100 + selected_ticker[f'avg_return_{period}']))
                            
                            if stock_returns:
                                periods_x, returns_y = zip(*stock_returns)
                                fig.add_trace(go.Scatter(
                                    x=periods_x,
                                    y=returns_y,
                                    mode='lines+markers',
                                    line=dict(color='lightgray', width=1),
                                    marker=dict(color='gray', size=6),
                                    name=f"{selected_ticker['ticker']} ({selected_ticker['interval']})",
                                    showlegend=True
                                ))
                            
                            # Add volume bars for fallback case
                            volume_periods = []
                            avg_volumes = []
                            for period in periods[1:]:
                                if f'avg_volume_{period}' in selected_ticker:
                                    volume_periods.append(period)
                                    avg_volumes.append(selected_ticker[f'avg_volume_{period}'])
                            
                            if len(avg_volumes) > 0:
                                fig.add_trace(go.Bar(
                                    x=volume_periods,
                                    y=avg_volumes,
                                    name='Average Volume',
                                    marker_color='lightgray',
                                    showlegend=True
                                ), row=2, col=1)
                    else:
                        # Fallback to original scatter plot if no returns distribution data available
                        periods = [0] + list(range(1, 101))  # Full range from 0 to 100
                        stock_returns = [(0, 100)]  # Start with (0, 100)
                        for period in periods[1:]:  # Skip 0 as we already added it
                            if f'avg_return_{period}' in selected_ticker:
                                stock_returns.append((period, 100 + selected_ticker[f'avg_return_{period}']))
                        
                        if stock_returns:
                            periods_x, returns_y = zip(*stock_returns)
                            fig.add_trace(go.Scatter(
                                x=periods_x,
                                y=returns_y,
                                mode='lines+markers',
                                line=dict(color='lightgray', width=1),
                                marker=dict(color='gray', size=6),
                                name=f"{selected_ticker['ticker']} ({selected_ticker['interval']})",
                                showlegend=True
                            ))
                        
                        # Add volume bars
                        volume_periods = []
                        avg_volumes = []
                        for period in periods[1:]:
                            if f'avg_volume_{period}' in selected_ticker:
                                volume_periods.append(period)
                                avg_volumes.append(selected_ticker[f'avg_volume_{period}'])
                        
                        if len(avg_volumes) > 0:
                            fig.add_trace(go.Bar(
                                x=volume_periods,
                                y=avg_volumes,
                                name='Average Volume',
                                marker_color='lightgray',
                                showlegend=True
                            ), row=2, col=1)
                    
                    # Initialize variables for tracking last price point
                    last_price_period = None
                    last_price_value = None
                    
                    # Add actual price history if available
                    if 'price_history' in selected_ticker and selected_ticker['price_history']:
                        price_history = selected_ticker['price_history']
                        if isinstance(price_history, str):
                            # Handle case where price_history might be stored as string
                            try:
                                import ast
                                price_history = ast.literal_eval(str(price_history))
                            except Exception:
                                # If parsing fails, silently set to empty dict to avoid spam
                                price_history = {}
                        
                        if price_history and 0 in price_history and price_history[0] is not None:
                            entry_price = float(price_history[0])
                            price_periods = []
                            price_values = []
                            
                            # Collect price history points
                            for period in sorted(price_history.keys()):
                                if price_history[period] is not None and period >= 0:
                                    try:
                                        relative_price = (float(price_history[period]) / entry_price) * 100
                                        price_periods.append(period)
                                        price_values.append(relative_price)
                                    except (ValueError, TypeError):
                                        continue
                            
                            # Add price history line and dots
                            if len(price_periods) > 1:
                                fig.add_trace(go.Scatter(
                                    x=price_periods,
                                    y=price_values,
                                    mode='lines+markers',
                                    line=dict(color='red', width=1),
                                    marker=dict(color='red', size=6),
                                    name='Price History',
                                    showlegend=True
                                ))
                            elif len(price_periods) == 1:
                                # Single point case
                                fig.add_trace(go.Scatter(
                                    x=price_periods,
                                    y=price_values,
                                    mode='markers',
                                    marker=dict(color='red', size=6),
                                    name='Price History',
                                    showlegend=True
                                ))
                            
                            # Store the last price history point for connecting to current price
                            if price_periods:
                                last_price_period = price_periods[-1]
                                last_price_value = price_values[-1]
                    
                    # Add actual volume history if available
                    if 'volume_history' in selected_ticker and selected_ticker['volume_history']:
                        volume_history = selected_ticker['volume_history']
                        if isinstance(volume_history, str):
                            try:
                                import ast
                                volume_history = ast.literal_eval(str(volume_history))
                            except Exception:
                                # If parsing fails, silently set to empty dict to avoid spam
                                volume_history = {}
                        
                        if volume_history and 0 in volume_history and volume_history[0] is not None:
                            volume_periods = []
                            volume_values = []
                            
                            # Collect volume history points
                            for period in sorted(volume_history.keys()):
                                if volume_history[period] is not None and period >= 0:
                                    try:
                                        volume_periods.append(period)
                                        volume_values.append(float(volume_history[period]))
                                    except (ValueError, TypeError):
                                        continue
                            
                            # Add volume history line (red lines for latest signal)
                            if len(volume_periods) > 1:
                                fig.add_trace(go.Scatter(
                                    x=volume_periods,
                                    y=volume_values,
                                    mode='lines+markers',
                                    line=dict(color='red', width=2),
                                    marker=dict(color='red', size=6),
                                    name='Latest Signal Volume',
                                    showlegend=True
                                ), row=2, col=1)
                            elif len(volume_periods) == 1:
                                # Single point case
                                fig.add_trace(go.Scatter(
                                    x=volume_periods,
                                    y=volume_values,
                                    mode='markers',
                                    marker=dict(color='red', size=6),
                                    name='Latest Signal Volume',
                                    showlegend=True
                                ), row=2, col=1)
                    
                    # Add current price at current period (updated to avoid duplicate)
                    if ('current_period' in selected_ticker and 'current_price' in selected_ticker and 
                        'latest_signal_price' in selected_ticker and 'price_history' in selected_ticker):
                        current_period = selected_ticker['current_period']
                        price_history = selected_ticker['price_history']
                        
                        # Parse price_history if it's a string
                        if isinstance(price_history, str):
                            try:
                                import ast
                                price_history = ast.literal_eval(str(price_history))
                            except:
                                price_history = {}
                        
                        # Calculate current price relative value
                        current_price_relative = None
                        if selected_ticker['latest_signal_price']:
                            price_change = ((selected_ticker['current_price'] - selected_ticker['latest_signal_price']) / 
                                             selected_ticker['latest_signal_price'] * 100)
                            current_price_relative = 100 + price_change
                        
                    
                    # Add baseline reference line at y=100 (add after all traces for visibility)
                    fig.add_hline(y=100, line_dash="dash", line_color="gray", line_width=1, 
                                 annotation_text="Entry Price (Baseline)", annotation_position="top right")
                    
                    # # Add gray dot at [0, 100] and connect to first data point
                    # fig.add_trace(go.Scatter(
                    #     x=[0],
                    #     y=[100],
                    #     mode='markers',
                    #     marker=dict(color='gray', size=8),
                    #     name='Entry Point',
                    #     showlegend=True
                    # ))
                    
                    # Add gray line from [0, 100] to first available data point
                    # Find the first period with data (usually period 3)
                    first_period = None
                    first_value = None
                    
                    # Use continuous range for consistent visualization
                    # Skip boxplot data check and use scatter plot data
                    if False:  # Disable boxplot data check to force continuous range
                        filtered_returns = returns_df[
                            (returns_df['ticker'] == ticker_filter) &
                            (returns_df['interval'] == selected_interval)
                        ]
                        if not filtered_returns.empty:
                            periods_with_data = sorted(filtered_returns['period'].unique())
                            if periods_with_data:
                                first_period = periods_with_data[0]
                                period_returns = filtered_returns[filtered_returns['period'] == first_period]['return'].values
                                if len(period_returns) > 0:
                                    first_value = 100 + np.median(period_returns)
                    
                    # If no boxplot data, use scatter plot data
                    if first_period is None or first_value is None:
                        periods = list(range(1, 101))  # Full range from 1 to 100
                        for period in periods:
                            if f'avg_return_{period}' in selected_ticker:
                                first_period = period
                                first_value = 100 + selected_ticker[f'avg_return_{period}']
                                break
                    
                    # Add connecting line if we found a first data point
                    if first_period is not None and first_value is not None:
                        fig.add_trace(go.Scatter(
                            x=[0, first_period],
                            y=[100, first_value],
                            mode='lines',
                            line=dict(color='gray', width=1),
                            name='Baseline Connection',
                            showlegend=False
                        ))
                    
                    # Find the period with maximum return
                    max_return = -float('inf')
                    best_period = None
                    periods = list(range(1, 101))  # Full range from 1 to 100
                    for period in periods:
                        if f'avg_return_{period}' in selected_ticker:
                            if selected_ticker[f'avg_return_{period}'] > max_return:
                                max_return = selected_ticker[f'avg_return_{period}']
                                best_period = period
                    
                    # Update layout
                    title_html = (
                        f"<span style='font-size:24px'><b>{selected_ticker['ticker']} ({selected_ticker['interval']})</b></span><br>"
                        f"<span style='font-size:12px'>best period: {best_period}\t  "
                        f"best return: {max_return:.2f}%  "
                        f"success rate: {selected_ticker[f'success_rate_{best_period}']:.2f}\t  "
                        f"test count: {selected_ticker[f'test_count_{best_period}']}</span>"
                    )
                                    
                    fig.update_layout(
                        legend=dict(font=dict(color='black')),
                        title=dict(
                            text=title_html,
                            x=0.5,
                            font=dict(size=24, color='black'),
                            xanchor='center',
                            yanchor='top'
                        ),
                        showlegend=True,
                        height=566,  # Increased height for dual subplots
                        plot_bgcolor='white',
                        paper_bgcolor='white'
                    )
                    
                    # Update axes for subplots with synchronized x-axis
                    fig.update_xaxes(
                        title_text="Period", 
                        row=1, col=1,
                        range=[-5, 105],  # Set consistent x-axis range
                        showgrid=True,
                        gridwidth=1,
                        gridcolor='lightgray',
                        showline=True,
                        linewidth=1,
                        linecolor='black',
                        tickfont=dict(color='black'),
                        title=dict(text="Period", font=dict(color='black'))
                    )
                    fig.update_xaxes(
                        title_text="Period", 
                        row=2, col=1,
                        range=[-5, 105],  # Same x-axis range as top subplot
                        showgrid=True,
                        gridwidth=1,
                        gridcolor='lightgray',
                        showline=True,
                        linewidth=1,
                        linecolor='black',
                        tickfont=dict(color='black'),
                        title=dict(text="Period", font=dict(color='black'))
                    )
                    fig.update_yaxes(
                        title_text="Relative Price (Baseline = 100)", 
                        row=1, col=1,
                        showgrid=True,
                        gridwidth=1,
                        gridcolor='lightgray',
                        showline=True,
                        linewidth=1,
                        linecolor='black',
                        tickfont=dict(color='black'),
                        title=dict(text="Relative Price (Baseline = 100)", font=dict(color='black'))
                    )
                    fig.update_yaxes(
                        title_text="Volume", 
                        row=2, col=1,
                        showgrid=True,
                        gridwidth=1,
                        gridcolor='lightgray',
                        showline=True,
                        linewidth=1,
                        linecolor='black',
                        tickfont=dict(color='black'),
                        title=dict(text="Volume", font=dict(color='black'))
                    )
                    
                    # Display the plot
                    st.plotly_chart(fig, use_container_width=True)

                elif ticker_filter:
                    st.info("No matching stocks found for the selected criteria.")
                else:
                    st.info("Please select a stock from the tables below to view details.")

        with waikiki_tables_col:
            # Helper for single-select AgGrid
            def waikiki_aggrid_editor(df, tab_key):
                if df is not None and not df.empty:
                    df = df.copy()
                    
                    # To prevent ArrowTypeError from mixed types, convert object columns to string
                    for col in df.columns:
                        if df[col].dtype == 'object':
                            df[col] = df[col].astype(str)

                    # Round all numeric columns to 2 decimal places
                    for col in df.columns:
                        if df[col].dtype in ['float64', 'float32']:
                            df[col] = df[col].round(2)
                    
                    # Configure AgGrid options
                    gb = GridOptionsBuilder.from_dataframe(df)
                    gb.configure_selection('single', use_checkbox=True, groupSelectsChildren=False, groupSelectsFiltered=False)
                    gb.configure_grid_options(domLayout='normal', rowSelection='single')
                    gb.configure_default_column(editable=False, filterable=True, sortable=True, resizable=True)
                    
                    # Configure specific columns - only minWidth for ticker, latest_signal, current_time
                    # All others use fixed width based on header length
                    
                    # Only these 3 columns get minWidth (variable content needs flexibility)
                    if 'ticker' in df.columns:
                        gb.configure_column('ticker', pinned='left', minWidth=90)
                    if 'latest_signal' in df.columns:
                        gb.configure_column('latest_signal', minWidth=120)
                    if 'current_time' in df.columns:
                        gb.configure_column('current_time', minWidth=100)
                    
                    # All other columns get fixed width based on header length
                    column_widths = {
                        'interval': 80,           # 8 chars: "interval"
                        'hold_time': 90,          # 9 chars: "hold_time"
                        'exp_return': 100,         # 10 chars: "exp_return"
                        'signal_count': 120,       # 12 chars: "signal_count"
                        'latest_signal_price': 150, # 18 chars: "latest_signal_price"
                        'current_price': 120,      # 13 chars: "current_price"
                        'current_period': 120,    # 14 chars: "current_period"
                        'test_count': 100,         # 10 chars: "test_count"
                        'success_rate': 110,       # 12 chars: "success_rate"
                        'best_period': 110,        # 11 chars: "best_period"
                        'max_return': 100,         # 10 chars: "max_return"
                        'min_return': 100,         # 10 chars: "min_return"
                        'avg_return': 100,         # 10 chars: "avg_return"
                        # NX columns
                        'nx_1d_signal': 100,      # 12 chars: "nx_1d_signal"
                        'nx_30m_signal': 110,     # 13 chars: "nx_30m_signal"
                        'nx_1h_signal': 100,      # 12 chars: "nx_1h_signal"
                        'nx_5m_signal': 100,      # 12 chars: "nx_5m_signal"
                        'nx_1d': 80,              # 6 chars: "nx_1d"
                        'nx_30m': 90,             # 7 chars: "nx_30m"
                        'nx_1h': 80,              # 6 chars: "nx_1h"
                        'nx_5m': 80,              # 6 chars: "nx_5m"
                        'nx_4h': 80,              # 6 chars: "nx_4h"
                    }
                    
                    # Add MC signal analysis column widths
                    mc_column_widths = {
                        'mc_signals_before_cd': 150,        # 18 chars: "mc_signals_before_cd"
                        'mc_at_top_price_count': 160,       # 20 chars: "mc_at_top_price_count"
                        'mc_at_top_price_rate': 150,        # 18 chars: "mc_at_top_price_rate"
                        'avg_mc_price_percentile': 170,     # 21 chars: "avg_mc_price_percentile"
                        'avg_mc_decline_after': 160,        # 19 chars: "avg_mc_decline_after"
                        'avg_mc_criteria_met': 150,         # 18 chars: "avg_mc_criteria_met"
                        'latest_mc_date': 160,              # 15 chars: "latest_mc_date"
                        'latest_mc_price': 140,             # 16 chars: "latest_mc_price"
                        'latest_mc_at_top_price': 180,      # 22 chars: "latest_mc_at_top_price"
                        'latest_mc_price_percentile': 190,  # 26 chars: "latest_mc_price_percentile"
                        'latest_mc_decline_after': 180,     # 23 chars: "latest_mc_decline_after"
                        'latest_mc_criteria_met': 170,      # 22 chars: "latest_mc_criteria_met"
                    }
                    
                    # Configure columns with specific widths
                    for col_name, width in column_widths.items():
                        if col_name in df.columns:
                            if col_name in ['exp_return', 'latest_signal_price', 'current_price', 'success_rate', 'max_return', 'min_return', 'avg_return']:
                                gb.configure_column(col_name, type=['numericColumn', 'numberColumnFilter'], precision=2, width=width)
                            elif col_name in ['nx_1d_signal', 'nx_30m_signal', 'nx_1h_signal', 'nx_5m_signal', 'nx_1d', 'nx_30m', 'nx_1h', 'nx_5m', 'nx_4h']:
                                gb.configure_column(col_name, type=['booleanColumn'], width=width)
                            else:
                                gb.configure_column(col_name, width=width)
                    
                    # Configure MC signal analysis columns
                    for col_name, width in mc_column_widths.items():
                        if col_name in df.columns:
                            if col_name in ['mc_at_top_price_rate', 'avg_mc_price_percentile', 'avg_mc_decline_after', 'avg_mc_criteria_met', 
                                          'latest_mc_price', 'latest_mc_price_percentile', 'latest_mc_decline_after']:
                                gb.configure_column(col_name, type=['numericColumn', 'numberColumnFilter'], precision=2, width=width)
                            elif col_name in ['latest_mc_date']:
                                gb.configure_column(col_name, minWidth=width)
                            else:
                                gb.configure_column(col_name, width=width)
                    
                    # Handle dynamic columns (test_count_X, success_rate_X, avg_return_X where X is a number)
                    for col in df.columns:
                        if col.startswith('test_count_'):
                            gb.configure_column(col, width=85)  # 10-14 chars: "test_count_XX"
                        elif col.startswith('success_rate_'):
                            gb.configure_column(col, type=['numericColumn', 'numberColumnFilter'], precision=2, width=110)  # 14-18 chars: "success_rate_XXX"
                        elif col.startswith('avg_return_'):
                            gb.configure_column(col, type=['numericColumn', 'numberColumnFilter'], precision=2, width=100)  # 12-16 chars: "avg_return_XXX"
                    
                    # Enable pagination for large datasets
                    gb.configure_pagination(paginationAutoPageSize=True)
                    
                    grid_options = gb.build()
                    
                    # Suppress the grid's auto-sizing to enforce our fixed-width columns
                    grid_options['suppressSizeToFit'] = True
                    
                    # Display AgGrid
                    grid_response = AgGrid(
                        df,
                        gridOptions=grid_options,
                        data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
                        update_mode=GridUpdateMode.SELECTION_CHANGED,
                        fit_columns_on_grid_load=False,  # Use custom sizing
                        theme='streamlit',
                        height=425,
                        width='100%',
                        key=f"waikiki_aggrid_{tab_key}_{selected_file}",
                        reload_data=False,
                        allow_unsafe_jscode=True
                    )
                    
                    # Handle selection
                    selected_rows = grid_response['selected_rows']
                    if selected_rows is not None and len(selected_rows) > 0:
                        selected_row = selected_rows.iloc[0]  # Take first selected row
                        new_ticker = selected_row['ticker']
                        new_interval = selected_row['interval']
                        
                        # Update session state if selection changed
                        if (st.session_state.selected_ticker != new_ticker or
                            st.session_state.selected_interval != new_interval):
                            st.session_state.selected_ticker = new_ticker
                            st.session_state.selected_interval = new_interval
                            st.rerun()
                    
                    return grid_response['data']
                else:
                    st.info("No data available for this table. Please run analysis first.")
                    return None

            tabs = st.tabs([
                "Best Intervals (50)", 
                "Best Intervals (20)", 
                "Best Intervals (100)", 
                "High Return Intervals",
                "Interval Details",
            ])

            # Display best intervals (50)
            with tabs[0]:
                df, message = load_results('cd_eval_best_intervals_50_', selected_file, 'avg_return_10')
                if df is not None:
                    if waikiki_ticker_filter:
                        df = df[df['ticker'].str.contains(waikiki_ticker_filter, case=False)]
                    
                    if 'interval' in df.columns:
                        intervals = sorted(df['interval'].unique())
                        selected_intervals = st.multiselect("Filter by interval:", intervals, default=intervals, key=f"interval_filter_best_50_{selected_file}")
                        if selected_intervals:
                            df = df[df['interval'].isin(selected_intervals)]
                    waikiki_aggrid_editor(df, '50')
                else:
                    st.info("No best intervals data available for 50-period analysis. Please run CD Signal Evaluation first.")

            # Display best intervals (20)
            with tabs[1]:
                df, message = load_results('cd_eval_best_intervals_20_', selected_file, 'avg_return_10')
                if df is not None:
                    if waikiki_ticker_filter:
                        df = df[df['ticker'].str.contains(waikiki_ticker_filter, case=False)]
                    
                    if 'interval' in df.columns:
                        intervals = sorted(df['interval'].unique())
                        selected_intervals = st.multiselect("Filter by interval:", intervals, default=intervals, key=f"interval_filter_best_20_{selected_file}")
                        if selected_intervals:
                            df = df[df['interval'].isin(selected_intervals)]
                    waikiki_aggrid_editor(df, '20')
                else:
                    st.info("No best intervals data available for 20-period analysis. Please run CD Signal Evaluation first.")

            # Display best intervals (100)
            with tabs[2]:
                df, message = load_results('cd_eval_best_intervals_100_', selected_file, 'avg_return_10')
                if df is not None:
                    if waikiki_ticker_filter:
                        df = df[df['ticker'].str.contains(waikiki_ticker_filter, case=False)]
                    
                    if 'interval' in df.columns:
                        intervals = sorted(df['interval'].unique())
                        selected_intervals = st.multiselect("Filter by interval:", intervals, default=intervals, key=f"interval_filter_best_100_{selected_file}")
                        if selected_intervals:
                            df = df[df['interval'].isin(selected_intervals)]
                    waikiki_aggrid_editor(df, '100')
                else:
                    st.info("No best intervals data available for 100-period analysis. Please run CD Signal Evaluation first.")

            # Display high return intervals
            with tabs[3]:
                df, message = load_results('cd_eval_good_signals_', selected_file, 'latest_signal')
                if df is not None:
                    if waikiki_ticker_filter:
                        df = df[df['ticker'].str.contains(waikiki_ticker_filter, case=False)]
                    
                    if 'latest_signal' in df.columns:
                        df = df[df['latest_signal'].notna()]
                        df = df.sort_values(by='latest_signal', ascending=False)
                        if 'interval' in df.columns:
                            intervals = sorted(df['interval'].unique())
                            selected_intervals = st.multiselect("Filter by interval:", intervals, default=intervals, key=f"interval_filter_recent_{selected_file}")
                            if selected_intervals:
                                df = df[df['interval'].isin(selected_intervals)]
                        waikiki_aggrid_editor(df, 'good')
                    else:
                        st.info("No signal date information available in the results.")
                else:
                    st.info("No recent signals data available. Please run an analysis first.")

            # Display interval details
            with tabs[4]:
                df, message = load_results('cd_eval_custom_detailed_', selected_file, 'avg_return_10')
                if df is not None:
                    if waikiki_ticker_filter:
                        df = df[df['ticker'].str.contains(waikiki_ticker_filter, case=False)]
                    
                    if 'interval' in df.columns:
                        intervals = sorted(df['interval'].unique())
                        selected_intervals = st.multiselect("Filter by interval:", intervals, default=intervals, key=f"interval_filter_details_{selected_file}")
                        if selected_intervals:
                            df = df[df['interval'].isin(selected_intervals)]
                    waikiki_aggrid_editor(df, 'details')
                else:
                    st.info("No interval summary data available. Please run CD Signal Evaluation first.")

        # Resonance Model section
        st.subheader("Resonance Model")
        
        # Add shared ticker filter for Resonance model
        resonance_ticker_filter = st.text_input("Filter by ticker symbol:", key=f"resonance_ticker_filter_{selected_file}")
        
        # Helper for AgGrid in Resonance model
        def resonance_aggrid_editor(df, tab_key, selection_enabled=True):
            if df is not None and not df.empty:
                df = df.copy()
                # To prevent ArrowTypeError from mixed types, convert object columns to string
                for col in df.columns:
                    if df[col].dtype == 'object':
                        df[col] = df[col].astype(str)

                gb = GridOptionsBuilder.from_dataframe(df)
                gb.configure_default_column(editable=False, filterable=True, sortable=True, resizable=True)
                gb.configure_pagination(paginationAutoPageSize=True)
                
                if selection_enabled:
                    gb.configure_selection('single', use_checkbox=True, groupSelectsChildren=False, groupSelectsFiltered=False)

                if 'ticker' in df.columns:
                    gb.configure_column('ticker', pinned='left', minWidth=90)
                if 'date' in df.columns:
                    gb.configure_column('date', minWidth=120)
                if 'signal_date' in df.columns:
                    gb.configure_column('signal_date', minWidth=120)

                grid_options = gb.build()
                
                ag_grid_params = {
                    'gridOptions': grid_options,
                    'fit_columns_on_grid_load': True,
                    'theme': 'streamlit',
                    'height': 350,
                    'width': '100%',
                    'key': f"resonance_aggrid_{tab_key}_{selected_file}",
                    'reload_data': False,
                    'allow_unsafe_jscode': True
                }

                if selection_enabled:
                    grid_response = AgGrid(
                        df,
                        data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
                        update_mode=GridUpdateMode.SELECTION_CHANGED,
                        **ag_grid_params
                    )
                    return grid_response
                else:
                    AgGrid(df, **ag_grid_params)
                    return None

        # Create two columns for 1234 and 5230 data
        col_1234, col_5230 = st.columns([1, 1])

        # Left column: 1234 data
        with col_1234:
            st.markdown("### 1234 Model")
            tab_1234_candidates, tab_1234_details = st.tabs(["Candidates", "Details"])

            # Display 1234 breakout candidates
            with tab_1234_candidates:
                df, message = load_results('cd_breakout_candidates_summary_1234_', selected_file, 'date')
                
                if df is not None and '1234' in message:
                    # Truncate to most recent 60 days
                    if 'date' in df.columns:
                        df['date'] = pd.to_datetime(df['date'])
                        cutoff_date = pd.Timestamp.now() - pd.Timedelta(days=60)
                        df = df[df['date'] >= cutoff_date]
                        if 'nx_30m_signal' in df.columns:
                            df['nx_30m_signal'] = df['nx_30m_signal'].astype(bool)
                        df['date'] = df['date'].dt.strftime('%Y-%m-%d')
                    
                    if resonance_ticker_filter:
                        df = df[df['ticker'].str.contains(resonance_ticker_filter, case=False)]
                    
                    # Add NX filtering if available
                    nx_filters_applied = False
                    if 'nx_1d_signal' in df.columns:
                        nx_1d_values = sorted(df['nx_1d_signal'].unique())
                        selected_nx_1d = st.multiselect("Filter by NX 1d Signal:", nx_1d_values, 
                                                       default=[True] if True in nx_1d_values else nx_1d_values,
                                                       key=f"nx_1d_filter_1234_{selected_file}")
                        if selected_nx_1d:
                            df = df[df['nx_1d_signal'].isin(selected_nx_1d)]
                            nx_filters_applied = True
                    
                    df_sorted = df.sort_values(by='date', ascending=False)
                    grid_response = resonance_aggrid_editor(df_sorted, 'summary_1234')

                    # Initialize session state for both selections
                    if 'resonance_1234_selected' not in st.session_state:
                        st.session_state.resonance_1234_selected = pd.DataFrame()
                    if 'resonance_5230_selected' not in st.session_state:
                        st.session_state.resonance_5230_selected = pd.DataFrame()

                    # Default selection to the first candidate if none are selected
                    if not df_sorted.empty and st.session_state.resonance_1234_selected.empty and st.session_state.resonance_5230_selected.empty:
                        st.session_state.resonance_1234_selected = df_sorted.head(1)

                    # If new selection is made in this grid
                    if grid_response and grid_response['selected_rows'] is not None and not pd.DataFrame(grid_response['selected_rows']).empty:
                        selected_df = pd.DataFrame(grid_response['selected_rows'])
                        # Avoid rerun if selection hasn't changed
                        if not selected_df.equals(st.session_state.resonance_1234_selected):
                            st.session_state.resonance_1234_selected = selected_df
                            st.session_state.resonance_5230_selected = pd.DataFrame()  # Clear other selection
                            st.rerun()
                else:
                    st.info("No 1234 breakout candidates found. Please run analysis first.")

            # Display 1234 detailed results
            with tab_1234_details:
                df, message = load_results('cd_breakout_candidates_details_1234_', selected_file, 'signal_date')
                
                if df is not None and '1234' in message:
                    # Truncate to most recent 60 days
                    if 'signal_date' in df.columns:
                        df['signal_date'] = pd.to_datetime(df['signal_date'])
                        cutoff_date = pd.Timestamp.now() - pd.Timedelta(days=60)
                        df = df[df['signal_date'] >= cutoff_date]
                        df['signal_date'] = df['signal_date'].dt.strftime('%Y-%m-%d')

                    if resonance_ticker_filter:
                        df = df[df['ticker'].str.contains(resonance_ticker_filter, case=False)]
                    
                    if 'interval' in df.columns:
                        intervals = sorted(df['interval'].unique())
                        selected_intervals = st.multiselect("Filter by interval:", intervals, 
                                                           default=intervals,
                                                           key=f"interval_filter_1234_{selected_file}")
                        if selected_intervals:
                            df = df[df['interval'].isin(selected_intervals)]
                    
                    # Display the dataframe
                    resonance_aggrid_editor(df.sort_values(by='signal_date', ascending=False), 'details_1234', selection_enabled=False)
                    
                else:
                    st.info("No 1234 detailed results found. Please run analysis first.")

        # Right column: 5230 data
        with col_5230:
            st.markdown("### 5230 Model")
            tab_5230_candidates, tab_5230_details = st.tabs(["Candidates", "Details"])

            # Display 5230 breakout candidates
            with tab_5230_candidates:
                df, message = load_results('cd_breakout_candidates_summary_5230_', selected_file, 'date')
                
                if df is not None and '5230' in message:
                    if resonance_ticker_filter:
                        df = df[df['ticker'].str.contains(resonance_ticker_filter, case=False)]
                    
                    # Add NX filtering if available
                    if 'nx_1h_signal' in df.columns:
                        nx_values = sorted(df['nx_1h_signal'].unique())
                        selected_nx = st.multiselect("Filter by NX 1h Signal:", nx_values, 
                                                   default=[True] if True in nx_values else nx_values,
                                                   key=f"nx_filter_5230_{selected_file}")
                        if selected_nx:
                            df = df[df['nx_1h_signal'].isin(selected_nx)]
                    
                    # Display the dataframe
                    grid_response = resonance_aggrid_editor(df.sort_values(by='date', ascending=False), 'summary_5230')

                    # If new selection is made in this grid
                    if grid_response and grid_response['selected_rows'] is not None and not pd.DataFrame(grid_response['selected_rows']).empty:
                        selected_df = pd.DataFrame(grid_response['selected_rows'])
                        # Avoid rerun if selection hasn't changed
                        if not selected_df.equals(st.session_state.resonance_5230_selected):
                            st.session_state.resonance_5230_selected = selected_df
                            st.session_state.resonance_1234_selected = pd.DataFrame()  # Clear other selection
                            st.rerun()
                else:
                    st.info("No 5230 breakout candidates found. Please run analysis first.")

            # Display 5230 detailed results
            with tab_5230_details:
                df, message = load_results('cd_breakout_candidates_details_5230_', selected_file, 'signal_date')
                
                if df is not None and '5230' in message:
                    if resonance_ticker_filter:
                        df = df[df['ticker'].str.contains(resonance_ticker_filter, case=False)]
                    
                    if 'interval' in df.columns:
                        intervals = sorted(df['interval'].unique())
                        selected_intervals = st.multiselect("Filter by interval:", intervals, 
                                                           default=intervals,
                                                           key=f"interval_filter_5230_{selected_file}")
                        if selected_intervals:
                            df = df[df['interval'].isin(selected_intervals)]
                    
                    # Display the dataframe
                    resonance_aggrid_editor(df.sort_values(by='signal_date', ascending=False), 'details_5230', selection_enabled=False)
                    
                else:
                    st.info("No 5230 detailed results found. Please run analysis first.")


        # Determine which selection to use
        selected_candidates = pd.DataFrame()
        source_model = None
        if 'resonance_1234_selected' in st.session_state and not st.session_state.resonance_1234_selected.empty:
            selected_candidates = st.session_state.resonance_1234_selected
            source_model = '1234'
        elif 'resonance_5230_selected' in st.session_state and not st.session_state.resonance_5230_selected.empty:
            selected_candidates = st.session_state.resonance_5230_selected
            source_model = '5230'

        if not selected_candidates.empty:
            # Load detailed data from waikiki model
            detailed_df, _ = load_results('cd_eval_custom_detailed_', selected_file)
            
            # Load returns distribution data for boxplots
            returns_df, _ = load_results('cd_eval_returns_distribution_', selected_file)

            if detailed_df is None or detailed_df.empty:
                st.warning("Could not load detailed data for Waikiki model. Please run analysis to generate `cd_eval_custom_detailed` file.")
            else:
                for index, row in selected_candidates.iterrows():
                    ticker = row['ticker']
                    # The intervals are like "1,2,4". These are hours. I need to convert them to "1h", "2h", "4h".
                    intervals_to_plot_str = row.get('intervals', '')
                    if not intervals_to_plot_str:
                        continue

                    st.markdown(f"#### Plots for {ticker} ({source_model} Model)")
                    
                    # Logic to parse intervals based on source_model
                    if source_model == '1234':
                        intervals_to_plot = [f"{i}h" for i in intervals_to_plot_str.split(',')]
                    elif source_model == '5230':
                        # For 5230 model, use fixed intervals: 5m, 10m, 15m, 30m
                        intervals_to_plot = ['5m', '10m', '15m', '30m']
                    else:
                        intervals_to_plot = []

                    # Create columns for plots
                    plot_cols = st.columns(len(intervals_to_plot))

                    for i, interval in enumerate(intervals_to_plot):
                        with plot_cols[i]:
                            # Filter data for this ticker and interval
                            plot_data = detailed_df[(detailed_df['ticker'] == ticker) & (detailed_df['interval'] == interval)]

                            if plot_data.empty:
                                st.write(f"No detailed data for {ticker} ({interval})")
                                continue
                            
                            selected_ticker_data = plot_data.iloc[0]

                            # Create figure with subplots: price on top, volume on bottom
                            fig = make_subplots(
                                rows=2, cols=1,
                                subplot_titles=('Price Movement', 'Volume'),
                                vertical_spacing=0.1,
                                row_heights=[0.7, 0.3]
                            )
                            
                            # Initialize variables for tracking last price point
                            last_price_period = None
                            last_price_value = None
                            
                            # Filter returns distribution data for boxplot visualization
                            if returns_df is not None and not returns_df.empty:
                                filtered_returns = returns_df[
                                    (returns_df['ticker'] == ticker) &
                                    (returns_df['interval'] == interval)
                                ]
                                
                                if not filtered_returns.empty:
                                    # Get periods that have data
                                    periods_with_data = sorted(filtered_returns['period'].unique())
                                    
                                    # Add boxplots for each period
                                    median_price_values = []
                                    median_periods = []
                                    
                                    # Add volume bars for each period
                                    volume_periods = []
                                    avg_volumes = []
                                    
                                    for period in periods_with_data:
                                        period_data = filtered_returns[filtered_returns['period'] == period]
                                        period_returns = period_data['return'].values
                                        
                                        if len(period_returns) > 0:
                                            # Convert returns to relative price (baseline = 100)
                                            relative_prices = 100 + period_returns
                                            
                                            # Add price boxplot
                                            fig.add_trace(go.Box(
                                                y=relative_prices,
                                                x=[period] * len(relative_prices),
                                                name=f'Period {period}',
                                                boxpoints=False,  # Don't show individual points
                                                showlegend=False,
                                                marker=dict(color='lightgray'),
                                                line=dict(color='lightgray')
                                            ))
                                            
                                            # Store median for connecting line
                                            median_price_values.append(100 + np.median(period_returns))
                                            median_periods.append(period)
                                        
                                        # Add volume data if available
                                        if 'volume' in period_data.columns:
                                            period_volumes = period_data['volume'].values
                                            if len(period_volumes) > 0:
                                                avg_volume = np.mean(period_volumes[~np.isnan(period_volumes)])
                                                volume_periods.append(period)
                                                avg_volumes.append(avg_volume)
                                    
                                    # Add median price connection line
                                    if len(median_price_values) > 1:
                                        fig.add_trace(go.Scatter(
                                            x=median_periods,
                                            y=median_price_values,
                                            mode='lines+markers',
                                            line=dict(color='gray', width=1),
                                            marker=dict(color='gray', size=6),
                                            name='Median Returns',
                                            showlegend=False
                                        ), row=1, col=1)
                                    
                                    # Add volume bars (grey bars for average volumes)
                                    if len(avg_volumes) > 0:
                                        fig.add_trace(go.Bar(
                                            x=volume_periods,
                                            y=avg_volumes,
                                            name='Average Volume',
                                            marker_color='lightgray',
                                            showlegend=False
                                        ), row=2, col=1)
                                else:
                                    # Fallback to scatter plot
                                    periods = [0] + list(range(1, 101))  # Full range from 0 to 100
                                    stock_returns = [(0, 100)]  # Start with (0, 100)
                                    for period in periods[1:]:  # Skip 0 as we already added it
                                        if f'avg_return_{period}' in selected_ticker_data and pd.notna(selected_ticker_data[f'avg_return_{period}']):
                                            stock_returns.append((period, 100 + selected_ticker_data[f'avg_return_{period}']))
                                    
                                    if len(stock_returns) > 1:
                                        periods_x, returns_y = zip(*stock_returns)
                                        fig.add_trace(go.Scatter(
                                            x=periods_x,
                                            y=returns_y,
                                            mode='lines+markers',
                                            line=dict(color='lightgray', width=1),
                                            marker=dict(color='gray', size=6),
                                            name=f"{ticker} ({interval})",
                                        ), row=1, col=1)
                                    
                                    # Add volume bars for fallback case
                                    volume_periods = []
                                    avg_volumes = []
                                    for period in periods[1:]:
                                        if f'avg_volume_{period}' in selected_ticker_data:
                                            volume_periods.append(period)
                                            avg_volumes.append(selected_ticker_data[f'avg_volume_{period}'])
                                    
                                    if len(avg_volumes) > 0:
                                        fig.add_trace(go.Bar(
                                            x=volume_periods,
                                            y=avg_volumes,
                                            name='Average Volume',
                                            marker_color='lightgray',
                                            showlegend=False
                                        ), row=2, col=1)
                            else:
                                # Fallback to scatter plot if no returns distribution data
                                periods = [0] + list(range(1, 101))  # Full range from 0 to 100
                                stock_returns = [(0, 100)]
                                for period in periods[1:]:
                                    if f'avg_return_{period}' in selected_ticker_data and pd.notna(selected_ticker_data[f'avg_return_{period}']):
                                        stock_returns.append((period, 100 + selected_ticker_data[f'avg_return_{period}']))
                                
                                if len(stock_returns) > 1:
                                    periods_x, returns_y = zip(*stock_returns)
                                    fig.add_trace(go.Scatter(
                                        x=periods_x,
                                        y=returns_y,
                                        mode='lines+markers',
                                        line=dict(color='lightgray', width=1),
                                        marker=dict(color='gray', size=6),
                                        name=f"{ticker} ({interval})",
                                    ), row=1, col=1)
                                
                                # Add volume bars
                                volume_periods = []
                                avg_volumes = []
                                for period in periods[1:]:
                                    if f'avg_volume_{period}' in selected_ticker_data:
                                        volume_periods.append(period)
                                        avg_volumes.append(selected_ticker_data[f'avg_volume_{period}'])
                                
                                if len(avg_volumes) > 0:
                                    fig.add_trace(go.Bar(
                                        x=volume_periods,
                                        y=avg_volumes,
                                        name='Average Volume',
                                        marker_color='lightgray',
                                        showlegend=False
                                    ), row=2, col=1)
                            
                            # Add actual price history if available
                            if 'price_history' in selected_ticker_data and selected_ticker_data['price_history']:
                                price_history = selected_ticker_data['price_history']
                                if isinstance(price_history, str):
                                    # Handle case where price_history might be stored as string
                                    try:
                                        import ast
                                        price_history = ast.literal_eval(str(price_history))
                                    except Exception:
                                        # If parsing fails, silently set to empty dict to avoid spam
                                        price_history = {}
                                
                                if price_history and 0 in price_history and price_history[0] is not None:
                                    entry_price = float(price_history[0])
                                    price_periods = []
                                    price_values = []
                                    
                                    # Collect price history points
                                    for period in sorted(price_history.keys()):
                                        if price_history[period] is not None and period >= 0:
                                            try:
                                                relative_price = (float(price_history[period]) / entry_price) * 100
                                                price_periods.append(period)
                                                price_values.append(relative_price)
                                            except (ValueError, TypeError):
                                                continue
                                    
                                    # Add price history line and dots
                                    if len(price_periods) > 1:
                                        fig.add_trace(go.Scatter(
                                            x=price_periods,
                                            y=price_values,
                                            mode='lines+markers',
                                            line=dict(color='red', width=1),
                                            marker=dict(color='red', size=6),
                                            name='Price History',
                                            showlegend=True
                                        ), row=1, col=1)
                                    elif len(price_periods) == 1:
                                        # Single point case
                                        fig.add_trace(go.Scatter(
                                            x=price_periods,
                                            y=price_values,
                                            mode='markers',
                                            marker=dict(color='red', size=6),
                                            name='Price History',
                                            showlegend=True
                                        ), row=1, col=1)
                                    
                                    # Store the last price history point for connecting to current price
                                    if price_periods:
                                        last_price_period = price_periods[-1]
                                        last_price_value = price_values[-1]
                            
                            # Add actual volume history if available
                            if 'volume_history' in selected_ticker_data and selected_ticker_data['volume_history']:
                                volume_history = selected_ticker_data['volume_history']
                                if isinstance(volume_history, str):
                                    try:
                                        import ast
                                        volume_history = ast.literal_eval(str(volume_history))
                                    except Exception:
                                        # If parsing fails, silently set to empty dict to avoid spam
                                        volume_history = {}
                                
                                if volume_history and 0 in volume_history and volume_history[0] is not None:
                                    volume_periods = []
                                    volume_values = []
                                    
                                    # Collect volume history points
                                    for period in sorted(volume_history.keys()):
                                        if volume_history[period] is not None and period >= 0:
                                            try:
                                                volume_periods.append(period)
                                                volume_values.append(float(volume_history[period]))
                                            except (ValueError, TypeError):
                                                continue
                                    
                                    # Add volume history line (red lines for latest signal)
                                    if len(volume_periods) > 1:
                                        fig.add_trace(go.Scatter(
                                            x=volume_periods,
                                            y=volume_values,
                                            mode='lines+markers',
                                            line=dict(color='red', width=2),
                                            marker=dict(color='red', size=6),
                                            name='Latest Signal Volume',
                                            showlegend=True
                                        ), row=2, col=1)
                                    elif len(volume_periods) == 1:
                                        # Single point case
                                        fig.add_trace(go.Scatter(
                                            x=volume_periods,
                                            y=volume_values,
                                            mode='markers',
                                            marker=dict(color='red', size=6),
                                            name='Latest Signal Volume',
                                            showlegend=True
                                        ), row=2, col=1)
                        
                            # Add baseline reference line at y=100 (add after all traces for visibility)
                            fig.add_hline(y=100, line_dash="dash", line_color="gray", line_width=1, 
                                         annotation_text="Entry Price (Baseline)", annotation_position="top right", row=1, col=1)
                            
                            # # Add gray dot at [0, 100] and connect to first data point
                            # fig.add_trace(go.Scatter(
                            #     x=[0],
                            #     y=[100],
                            #     mode='markers',
                            #     marker=dict(color='gray', size=8),
                            #     name='Entry Point',
                            #     showlegend=True
                            # ), row=1, col=1)
                            
                            # Add gray line from [0, 100] to first available data point
                            # Find the first period with data (usually period 3)
                            first_period = None
                            first_value = None
                            
                            # Use continuous range for consistent visualization
                            # Skip boxplot data check and use scatter plot data
                            if False:  # Disable boxplot data check to force continuous range
                                filtered_returns = returns_df[
                                    (returns_df['ticker'] == ticker) &
                                    (returns_df['interval'] == interval)
                                ]
                                if not filtered_returns.empty:
                                    periods_with_data = sorted(filtered_returns['period'].unique())
                                    if periods_with_data:
                                        first_period = periods_with_data[0]
                                        period_returns = filtered_returns[filtered_returns['period'] == first_period]['return'].values
                                        if len(period_returns) > 0:
                                            first_value = 100 + np.median(period_returns)
                            
                            # If no boxplot data, use scatter plot data
                            if first_period is None or first_value is None:
                                periods = list(range(1, 101))  # Full range from 1 to 100
                                for period in periods:
                                    if f'avg_return_{period}' in selected_ticker_data and pd.notna(selected_ticker_data[f'avg_return_{period}']):
                                        first_period = period
                                        first_value = 100 + selected_ticker_data[f'avg_return_{period}']
                                        break
                            
                            # Add connecting line if we found a first data point
                            if first_period is not None and first_value is not None:
                                fig.add_trace(go.Scatter(
                                    x=[0, first_period],
                                    y=[100, first_value],
                                    mode='lines',
                                    line=dict(color='gray', width=1),
                                    name='Baseline Connection',
                                    showlegend=False
                                ), row=1, col=1)
                            
                            # Highlight best period
                            max_return = -float('inf')
                            best_period = None
                            periods = list(range(1, 101))  # Full range from 1 to 100
                            for period in periods:
                                if f'avg_return_{period}' in selected_ticker_data and pd.notna(selected_ticker_data[f'avg_return_{period}']):
                                    if selected_ticker_data[f'avg_return_{period}'] > max_return:
                                        max_return = selected_ticker_data[f'avg_return_{period}']
                                        best_period = period
                            
                            title_html = (
                                f"<span style='font-size:16px'><b>{ticker} ({interval})</b></span><br>"
                            )
                            if best_period is not None:
                                 title_html += (f"<span style='font-size:10px'>best period: {best_period} | "
                                f"return: {max_return:.2f}% | "
                                f"success: {selected_ticker_data.get(f'success_rate_{best_period}', 0):.2f}  "
                                f"test count: {selected_ticker_data.get(f'test_count_{best_period}', 0)}</span>")
                            
                            fig.update_layout(
                                title=dict(text=title_html, 
                                            x=0.5, 
                                            font=dict(color='black'),
                                            xanchor='center',
                                            yanchor='top'),
                                showlegend=False,
                                height=400,  # Increased height for dual subplots
                                plot_bgcolor='white',
                                paper_bgcolor='white'
                            )
                            
                            # Update axes for subplots with synchronized x-axis
                            fig.update_xaxes(
                                title_text="Period", 
                                row=1, col=1,
                                range=[-5, 105],  # Set consistent x-axis range
                                showgrid=True,
                                gridwidth=1,
                                gridcolor='lightgray',
                                showline=True,
                                linewidth=1,
                                linecolor='black',
                                tickfont=dict(color='black'),
                                title=dict(text="Period", font=dict(color='black'))
                            )
                            fig.update_xaxes(
                                title_text="Period", 
                                row=2, col=1,
                                range=[-5, 105],  # Same x-axis range as top subplot
                                showgrid=True,
                                gridwidth=1,
                                gridcolor='lightgray',
                                showline=True,
                                linewidth=1,
                                linecolor='black',
                                tickfont=dict(color='black'),
                                title=dict(text="Period", font=dict(color='black'))
                            )
                            fig.update_yaxes(
                                title_text="Relative Price (Baseline = 100)", 
                                row=1, col=1,
                                showgrid=True,
                                gridwidth=1,
                                gridcolor='lightgray',
                                showline=True,
                                linewidth=1,
                                linecolor='black',
                                tickfont=dict(color='black'),
                                title=dict(text="Relative Price (Baseline = 100)", font=dict(color='black'))
                            )
                            fig.update_yaxes(
                                title_text="Volume", 
                                row=2, col=1,
                                showgrid=True,
                                gridwidth=1,
                                gridcolor='lightgray',
                                showline=True,
                                linewidth=1,
                                linecolor='black',
                                tickfont=dict(color='black'),
                                title=dict(text="Volume", font=dict(color='black'))
                            )
                            
                            st.plotly_chart(fig, use_container_width=True)


# ============================
# MC ANALYSIS PAGE  
# ============================
elif page == "MC Analysis (卖出)":
    # Create two columns for the two table views
    if selected_file:
        st.subheader("Waikiki Model")
        
        # Add shared ticker filter for Waikiki model
        mc_waikiki_ticker_filter = st.text_input("Filter by ticker symbol:", key=f"mc_waikiki_ticker_filter_{selected_file}")

        mc_waikiki_viz_col, mc_waikiki_tables_col = st.columns([1, 1])

        with mc_waikiki_viz_col:
            # Load the detailed results for period information
            mc_detailed_df, _ = load_results('mc_eval_custom_detailed_', selected_file)
            
            # Load the returns distribution data for boxplots
            mc_returns_df, _ = load_results('mc_eval_returns_distribution_', selected_file)
            
            if mc_detailed_df is None or 'ticker' not in mc_detailed_df.columns:
                st.info("Please run an analysis first to view visualizations and period returns.")
            else:
                # Use selected ticker and interval from session state for MC
                mc_ticker_filter = st.session_state.mc_selected_ticker if st.session_state.mc_selected_ticker else ""
                mc_selected_interval = st.session_state.mc_selected_interval if st.session_state.mc_selected_interval else '1d'
                
                # If no ticker is selected, automatically select the first one from the best intervals (50) data
                if not mc_ticker_filter:
                    mc_best_50_df, _ = load_results('mc_eval_best_intervals_50_', selected_file, 'avg_return_10')
                    if mc_best_50_df is not None and not mc_best_50_df.empty:
                        first_row = mc_best_50_df.iloc[0]
                        mc_ticker_filter = first_row['ticker']
                        mc_selected_interval = first_row['interval']
                        # Update session state
                        st.session_state.mc_selected_ticker = mc_ticker_filter
                        st.session_state.mc_selected_interval = mc_selected_interval

                # Filter the detailed DataFrame with exact match for ticker and interval
                mc_filtered_detailed = mc_detailed_df[
                    (mc_detailed_df['ticker'] == mc_ticker_filter) &
                    (mc_detailed_df['interval'] == mc_selected_interval)
                ]
                
                if not mc_filtered_detailed.empty:
                    mc_selected_ticker = mc_filtered_detailed.iloc[0]

                    # Visualization Panel
                    # Create figure with subplots: price on top, volume on bottom
                    fig = make_subplots(
                        rows=2, cols=1,
                        subplot_titles=('Price Movement After MC Signal', 'Volume'),
                        vertical_spacing=0.1,
                        row_heights=[0.7, 0.3]
                    )
                    
                    # Filter returns distribution data for selected ticker and interval
                    if mc_returns_df is not None and not mc_returns_df.empty:
                        mc_filtered_returns = mc_returns_df[
                            (mc_returns_df['ticker'] == mc_ticker_filter) &
                            (mc_returns_df['interval'] == mc_selected_interval)
                        ]
                        
                        if not mc_filtered_returns.empty:
                            # Get periods that have data
                            periods_with_data = sorted(mc_filtered_returns['period'].unique())
                            
                            # Add price boxplots for each period
                            median_price_values = []
                            median_periods = []
                            
                            # Add volume bars for each period
                            volume_periods = []
                            avg_volumes = []
                            
                            for period in periods_with_data:
                                period_data = mc_filtered_returns[mc_filtered_returns['period'] == period]
                                period_returns = period_data['return'].values
                                
                                if len(period_returns) > 0:
                                    # Convert returns to relative price (baseline = 100)
                                    relative_prices = 100 + period_returns
                                    
                                    # Add price boxplot
                                    fig.add_trace(go.Box(
                                        y=relative_prices,
                                        x=[period] * len(relative_prices),
                                        name=f'Period {period}',
                                        boxpoints=False,  # Don't show individual points
                                        showlegend=False,
                                        marker=dict(color='lightgray'),
                                        line=dict(color='lightgray')
                                    ))
                                    
                                    # Store median for connecting line
                                    median_price_values.append(100 + np.median(period_returns))
                                    median_periods.append(period)
                                
                                # Add volume data if available
                                if 'volume' in period_data.columns:
                                    period_volumes = period_data['volume'].values
                                    if len(period_volumes) > 0:
                                        avg_volume = np.mean(period_volumes[~np.isnan(period_volumes)])
                                        volume_periods.append(period)
                                        avg_volumes.append(avg_volume)
                            
                            # Add median price connection line
                            if len(median_price_values) > 1:
                                fig.add_trace(go.Scatter(
                                    x=median_periods,
                                    y=median_price_values,
                                    mode='lines+markers',
                                    line=dict(color='gray', width=1),
                                    marker=dict(color='gray', size=6),
                                    name='Median Returns',
                                    showlegend=True
                                ))
                            
                            # Add volume bars (grey bars for average volumes)
                            if len(avg_volumes) > 0:
                                fig.add_trace(go.Bar(
                                    x=volume_periods,
                                    y=avg_volumes,
                                    name='Average Volume',
                                    marker_color='lightgray',
                                    showlegend=True
                                ), row=2, col=1)
                        else:
                            # Fallback to original scatter plot if no returns distribution data
                            periods = [0] + list(range(1, 101))  # Full range from 0 to 100
                            stock_returns = [(0, 100)]  # Start with (0, 100)
                            for period in periods[1:]:  # Skip 0 as we already added it
                                if f'avg_return_{period}' in mc_selected_ticker:
                                    stock_returns.append((period, 100 + mc_selected_ticker[f'avg_return_{period}']))
                            
                            if stock_returns:
                                periods_x, returns_y = zip(*stock_returns)
                                fig.add_trace(go.Scatter(
                                    x=periods_x,
                                    y=returns_y,
                                    mode='lines+markers',
                                    line=dict(color='lightgray', width=1),
                                    marker=dict(color='gray', size=6),
                                    name=f"{mc_selected_ticker['ticker']} ({mc_selected_ticker['interval']})",
                                    showlegend=True
                                ))
                            
                            # Add volume bars for fallback case
                            volume_periods = []
                            avg_volumes = []
                            for period in periods[1:]:
                                if f'avg_volume_{period}' in mc_selected_ticker:
                                    volume_periods.append(period)
                                    avg_volumes.append(mc_selected_ticker[f'avg_volume_{period}'])
                            
                            if len(avg_volumes) > 0:
                                fig.add_trace(go.Bar(
                                    x=volume_periods,
                                    y=avg_volumes,
                                    name='Average Volume',
                                    marker_color='lightgray',
                                    showlegend=True
                                ), row=2, col=1)
                    else:
                        # Fallback to original scatter plot if no returns distribution data available
                        periods = [0] + list(range(1, 101))  # Full range from 0 to 100
                        stock_returns = [(0, 100)]  # Start with (0, 100)
                        for period in periods[1:]:  # Skip 0 as we already added it
                            if f'avg_return_{period}' in mc_selected_ticker:
                                stock_returns.append((period, 100 + mc_selected_ticker[f'avg_return_{period}']))
                        
                        if stock_returns:
                            periods_x, returns_y = zip(*stock_returns)
                            fig.add_trace(go.Scatter(
                                x=periods_x,
                                y=returns_y,
                                mode='lines+markers',
                                line=dict(color='lightgray', width=1),
                                marker=dict(color='gray', size=6),
                                name=f"{mc_selected_ticker['ticker']} ({mc_selected_ticker['interval']})",
                                showlegend=True
                            ))
                        
                        # Add volume bars
                        volume_periods = []
                        avg_volumes = []
                        for period in periods[1:]:
                            if f'avg_volume_{period}' in mc_selected_ticker:
                                volume_periods.append(period)
                                avg_volumes.append(mc_selected_ticker[f'avg_volume_{period}'])
                        
                        if len(avg_volumes) > 0:
                            fig.add_trace(go.Bar(
                                x=volume_periods,
                                y=avg_volumes,
                                name='Average Volume',
                                marker_color='lightgray',
                                showlegend=True
                            ), row=2, col=1)
                    
                    # Initialize variables for tracking last price point
                    last_price_period = None
                    last_price_value = None
                    
                    # Add actual price history if available
                    if 'price_history' in mc_selected_ticker and mc_selected_ticker['price_history']:
                        price_history = mc_selected_ticker['price_history']
                        if isinstance(price_history, str):
                            # Handle case where price_history might be stored as string
                            try:
                                import ast
                                price_history = ast.literal_eval(str(price_history))
                            except Exception:
                                # If parsing fails, silently set to empty dict to avoid spam
                                price_history = {}
                        
                        if price_history and 0 in price_history and price_history[0] is not None:
                            entry_price = float(price_history[0])
                            price_periods = []
                            price_values = []
                            
                            # Collect price history points
                            for period in sorted(price_history.keys()):
                                if price_history[period] is not None and period >= 0:
                                    try:
                                        relative_price = (float(price_history[period]) / entry_price) * 100
                                        price_periods.append(period)
                                        price_values.append(relative_price)
                                    except (ValueError, TypeError):
                                        continue
                            
                            # Add price history line and dots
                            if len(price_periods) > 1:
                                fig.add_trace(go.Scatter(
                                    x=price_periods,
                                    y=price_values,
                                    mode='lines+markers',
                                    line=dict(color='red', width=1),
                                    marker=dict(color='red', size=6),
                                    name='Price History',
                                    showlegend=True
                                ))
                            elif len(price_periods) == 1:
                                # Single point case
                                fig.add_trace(go.Scatter(
                                    x=price_periods,
                                    y=price_values,
                                    mode='markers',
                                    marker=dict(color='red', size=6),
                                    name='Price History',
                                    showlegend=True
                                ))
                            
                            # Store the last price history point for connecting to current price
                            if price_periods:
                                last_price_period = price_periods[-1]
                                last_price_value = price_values[-1]
                    
                    # Add actual volume history if available
                    if 'volume_history' in mc_selected_ticker and mc_selected_ticker['volume_history']:
                        volume_history = mc_selected_ticker['volume_history']
                        if isinstance(volume_history, str):
                            try:
                                import ast
                                volume_history = ast.literal_eval(str(volume_history))
                            except Exception:
                                # If parsing fails, silently set to empty dict to avoid spam
                                volume_history = {}
                        
                        if volume_history and 0 in volume_history and volume_history[0] is not None:
                            volume_periods = []
                            volume_values = []
                            
                            # Collect volume history points
                            for period in sorted(volume_history.keys()):
                                if volume_history[period] is not None and period >= 0:
                                    try:
                                        volume_periods.append(period)
                                        volume_values.append(float(volume_history[period]))
                                    except (ValueError, TypeError):
                                        continue
                            
                            # Add volume history line (red lines for latest signal)
                            if len(volume_periods) > 1:
                                fig.add_trace(go.Scatter(
                                    x=volume_periods,
                                    y=volume_values,
                                    mode='lines+markers',
                                    line=dict(color='red', width=2),
                                    marker=dict(color='red', size=6),
                                    name='Latest Signal Volume',
                                    showlegend=True
                                ), row=2, col=1)
                            elif len(volume_periods) == 1:
                                # Single point case
                                fig.add_trace(go.Scatter(
                                    x=volume_periods,
                                    y=volume_values,
                                    mode='markers',
                                    marker=dict(color='red', size=6),
                                    name='Latest Signal Volume',
                                    showlegend=True
                                ), row=2, col=1)
                    
                    # Add current price at current period (updated to avoid duplicate)
                    if ('current_period' in mc_selected_ticker and 'current_price' in mc_selected_ticker and 
                        'latest_signal_price' in mc_selected_ticker and 'price_history' in mc_selected_ticker):
                        current_period = mc_selected_ticker['current_period']
                        price_history = mc_selected_ticker['price_history']
                        
                        # Parse price_history if it's a string
                        if isinstance(price_history, str):
                            try:
                                import ast
                                price_history = ast.literal_eval(str(price_history))
                            except:
                                price_history = {}
                        
                        # Calculate current price relative value
                        current_price_relative = None
                        if mc_selected_ticker['latest_signal_price']:
                            price_change = ((mc_selected_ticker['current_price'] - mc_selected_ticker['latest_signal_price']) / 
                                             mc_selected_ticker['latest_signal_price'] * 100)
                            current_price_relative = 100 + price_change
                        
                        # Only add current price marker if it's not already in price_history
                        if (isinstance(price_history, dict) and current_period not in price_history and 
                            current_period > 0 and current_price_relative is not None):
                            
                            # Add connecting line from last price history point to current price
                            if last_price_period is not None and last_price_value is not None:
                                fig.add_trace(go.Scatter(
                                    x=[last_price_period, current_period],
                                    y=[last_price_value, current_price_relative],
                                    mode='lines',
                                    line=dict(color='red', width=1, dash='dot'),
                                    name='Price Projection',
                                    showlegend=False
                                ))
                            
                            # Add current price star
                            fig.add_trace(go.Scatter(
                                x=[current_period],
                                y=[current_price_relative],
                                mode='markers',
                                marker=dict(color='red', size=10, symbol='star'),
                                name='Current Price',
                                showlegend=True
                            ))
                        elif not price_history and current_period > 0 and current_price_relative is not None:
                            # If no price_history at all, still show current price
                            fig.add_trace(go.Scatter(
                                x=[current_period],
                                y=[current_price_relative],
                                mode='markers',
                                marker=dict(color='red', size=10, symbol='star'),
                                name='Current Price',
                                showlegend=True
                            ))
                    
                    # Add baseline reference line at y=100 (add after all traces for visibility)
                    fig.add_hline(y=100, line_dash="dash", line_color="gray", line_width=1, 
                                 annotation_text="Short Price (Baseline)", annotation_position="top right")
                    
                    # Find the first period with data (usually period 3)
                    first_period = None
                    first_value = None
                    
                    # Check if we have boxplot data for baseline connection
                    if mc_returns_df is not None and not mc_returns_df.empty:
                        filtered_returns = mc_returns_df[
                            (mc_returns_df['ticker'] == mc_ticker_filter) &
                            (mc_returns_df['interval'] == mc_selected_interval)
                        ]
                        if not filtered_returns.empty:
                            periods_with_data = sorted(filtered_returns['period'].unique())
                            if periods_with_data:
                                first_period = periods_with_data[0]
                                period_returns = filtered_returns[filtered_returns['period'] == first_period]['return'].values
                                if len(period_returns) > 0:
                                    first_value = 100 + np.median(period_returns)
                    
                    # If no boxplot data, use scatter plot data
                    if first_period is None or first_value is None:
                        periods = list(range(1, 101))  # Full range from 1 to 100
                        for period in periods:
                            if f'avg_return_{period}' in mc_selected_ticker:
                                first_period = period
                                first_value = 100 + mc_selected_ticker[f'avg_return_{period}']
                                break
                    
                    # Add connecting line if we found a first data point
                    if first_period is not None and first_value is not None:
                        fig.add_trace(go.Scatter(
                            x=[0, first_period],
                            y=[100, first_value],
                            mode='lines',
                            line=dict(color='gray', width=1),
                            name='Baseline Connection',
                            showlegend=False
                        ))
                    
                    # Find the period with minimum return (best for MC signals - more negative is better)
                    min_return = float('inf')
                    best_period = None
                    periods = list(range(1, 101))  # Full range from 1 to 100
                    for period in periods:
                        if f'avg_return_{period}' in mc_selected_ticker:
                            if mc_selected_ticker[f'avg_return_{period}'] < min_return:
                                min_return = mc_selected_ticker[f'avg_return_{period}']
                                best_period = period
                    
                    # Update layout
                    title_html = (
                        f"<span style='font-size:24px'><b>{mc_selected_ticker['ticker']} ({mc_selected_ticker['interval']})</b></span><br>"
                        f"<span style='font-size:12px'>best period: {best_period}\t  "
                        f"best return: {min_return:.2f}%  "
                        f"success rate: {mc_selected_ticker[f'success_rate_{best_period}']:.2f}\t  "
                        f"test count: {mc_selected_ticker[f'test_count_{best_period}']}</span>"
                    )
                                    
                    fig.update_layout(
                        legend=dict(font=dict(color='black')),
                        title=dict(
                            text=title_html,
                            x=0.5,
                            font=dict(size=24, color='black'),
                            xanchor='center',
                            yanchor='top'
                        ),
                        showlegend=True,
                        height=566,  # Increased height for dual subplots
                        plot_bgcolor='white',
                        paper_bgcolor='white'
                    )
                    
                    # Update axes for subplots with synchronized x-axis
                    fig.update_xaxes(
                        title_text="Period", 
                        row=1, col=1,
                        range=[-5, 105],  # Set consistent x-axis range
                        showgrid=True,
                        gridwidth=1,
                        gridcolor='lightgray',
                        showline=True,
                        linewidth=1,
                        linecolor='black', 
                        tickfont=dict(color='black'),
                        title=dict(text="Period", font=dict(color='black'))
                    )
                    fig.update_xaxes(
                        title_text="Period", 
                        row=2, col=1,
                        range=[-5, 105],  # Same x-axis range as top subplot
                        showgrid=True,
                        gridwidth=1,
                        gridcolor='lightgray',
                        showline=True,
                        linewidth=1,
                        linecolor='black',
                        tickfont=dict(color='black'),
                        title=dict(text="Period", font=dict(color='black'))
                    )
                    fig.update_yaxes(
                        title_text="Relative Price (Baseline = 100)", 
                        row=1, col=1,
                        showgrid=True,
                        gridwidth=1,
                        gridcolor='lightgray',
                        showline=True,
                        linewidth=1,
                        linecolor='black',
                        tickfont=dict(color='black'),
                        title=dict(text="Relative Price (Baseline = 100)", font=dict(color='black'))
                    )
                    fig.update_yaxes(
                        title_text="Volume", 
                        row=2, col=1,
                        showgrid=True,
                        gridwidth=1,
                        gridcolor='lightgray',
                        showline=True,
                        linewidth=1,
                        linecolor='black',
                        tickfont=dict(color='black'),
                        title=dict(text="Volume", font=dict(color='black'))
                    )
                    
                    # Display the plot
                    st.plotly_chart(fig, use_container_width=True)

                elif mc_ticker_filter:
                    st.info("No matching stocks found for the selected criteria.")
                else:
                    st.info("Please select a stock from the tables below to view details.")

        with mc_waikiki_tables_col:
            # Helper for single-select AgGrid for MC
            def mc_waikiki_aggrid_editor(df, tab_key):
                if df is not None and not df.empty:
                    df = df.copy()
                    
                    # To prevent ArrowTypeError from mixed types, convert object columns to string
                    for col in df.columns:
                        if df[col].dtype == 'object':
                            df[col] = df[col].astype(str)

                    # Round all numeric columns to 2 decimal places
                    for col in df.columns:
                        if df[col].dtype in ['float64', 'float32']:
                            df[col] = df[col].round(2)
                    
                    # Configure AgGrid options
                    gb = GridOptionsBuilder.from_dataframe(df)
                    gb.configure_selection('single', use_checkbox=True, groupSelectsChildren=False, groupSelectsFiltered=False)
                    gb.configure_grid_options(domLayout='normal', rowSelection='single')
                    gb.configure_default_column(editable=False, filterable=True, sortable=True, resizable=True)
                    
                    # Configure specific columns - only minWidth for ticker, latest_signal, current_time
                    # All others use fixed width based on header length
                    
                    # Only these 3 columns get minWidth (variable content needs flexibility)
                    if 'ticker' in df.columns:
                        gb.configure_column('ticker', pinned='left', minWidth=90)
                    if 'latest_signal' in df.columns:
                        gb.configure_column('latest_signal', minWidth=120)
                    if 'current_time' in df.columns:
                        gb.configure_column('current_time', minWidth=100)
                    
                    # All other columns get fixed width based on header length
                    column_widths = {
                        'interval': 80,           # 8 chars: "interval"
                        'hold_time': 90,          # 9 chars: "hold_time"
                        'exp_return': 100,         # 10 chars: "exp_return"
                        'signal_count': 120,       # 12 chars: "signal_count"
                        'latest_signal_price': 150, # 18 chars: "latest_signal_price"
                        'current_price': 120,      # 13 chars: "current_price"
                        'current_period': 120,    # 14 chars: "current_period"
                        'test_count': 100,         # 10 chars: "test_count"
                        'success_rate': 110,       # 12 chars: "success_rate"
                        'best_period': 110,        # 11 chars: "best_period"
                        'max_return': 100,         # 10 chars: "max_return"
                        'min_return': 100,         # 10 chars: "min_return"
                        'avg_return': 100,         # 10 chars: "avg_return"
                        # NX columns
                        'nx_1d_signal': 100,      # 12 chars: "nx_1d_signal"
                        'nx_30m_signal': 110,     # 13 chars: "nx_30m_signal"
                        'nx_1h_signal': 100,      # 12 chars: "nx_1h_signal"
                        'nx_5m_signal': 100,      # 12 chars: "nx_5m_signal"
                        'nx_1d': 80,              # 6 chars: "nx_1d"
                        'nx_30m': 90,             # 7 chars: "nx_30m"
                        'nx_1h': 80,              # 6 chars: "nx_1h"
                        'nx_5m': 80,              # 6 chars: "nx_5m"
                        'nx_4h': 80,              # 6 chars: "nx_4h"
                    }
                    
                    # Add CD signal analysis column widths for MC analysis
                    cd_column_widths = {
                        'cd_signals_before_mc': 150,        # 18 chars: "cd_signals_before_mc"
                        'cd_at_bottom_price_count': 160,    # 21 chars: "cd_at_bottom_price_count"
                        'cd_at_bottom_price_rate': 150,     # 20 chars: "cd_at_bottom_price_rate"
                        'avg_cd_price_percentile': 170,     # 21 chars: "avg_cd_price_percentile"
                        'avg_cd_increase_after': 160,       # 18 chars: "avg_cd_increase_after"
                        'avg_cd_criteria_met': 150,         # 16 chars: "avg_cd_criteria_met"
                        'latest_cd_date': 160,              # 13 chars: "latest_cd_date"
                        'latest_cd_price': 140,             # 14 chars: "latest_cd_price"
                        'latest_cd_at_bottom_price': 180,   # 22 chars: "latest_cd_at_bottom_price"
                        'latest_cd_price_percentile': 190,  # 24 chars: "latest_cd_price_percentile"
                        'latest_cd_increase_after': 180,    # 21 chars: "latest_cd_increase_after"
                        'latest_cd_criteria_met': 170,      # 18 chars: "latest_cd_criteria_met"
                    }
                    
                    # Configure columns with specific widths
                    for col_name, width in column_widths.items():
                        if col_name in df.columns:
                            if col_name in ['exp_return', 'latest_signal_price', 'current_price', 'success_rate', 'max_return', 'min_return', 'avg_return']:
                                gb.configure_column(col_name, type=['numericColumn', 'numberColumnFilter'], precision=2, width=width)
                            elif col_name in ['nx_1d_signal', 'nx_30m_signal', 'nx_1h_signal', 'nx_5m_signal', 'nx_1d', 'nx_30m', 'nx_1h', 'nx_5m', 'nx_4h']:
                                gb.configure_column(col_name, type=['booleanColumn'], width=width)
                            else:
                                gb.configure_column(col_name, width=width)
                    
                    # Configure CD signal analysis columns for MC analysis
                    for col_name, width in cd_column_widths.items():
                        if col_name in df.columns:
                            if col_name in ['cd_at_bottom_price_rate', 'avg_cd_price_percentile', 'avg_cd_increase_after', 'avg_cd_criteria_met', 
                                          'latest_cd_price', 'latest_cd_price_percentile', 'latest_cd_increase_after']:
                                gb.configure_column(col_name, type=['numericColumn', 'numberColumnFilter'], precision=2, width=width)
                            elif col_name in ['latest_cd_date']:
                                gb.configure_column(col_name, minWidth=width)
                            else:
                                gb.configure_column(col_name, width=width)
                    
                    # Handle dynamic columns (test_count_X, success_rate_X, avg_return_X where X is a number)
                    for col in df.columns:
                        if col.startswith('test_count_'):
                            gb.configure_column(col, width=85)  # 10-14 chars: "test_count_XX"
                        elif col.startswith('success_rate_'):
                            gb.configure_column(col, type=['numericColumn', 'numberColumnFilter'], precision=2, width=110)  # 14-18 chars: "success_rate_XXX"
                        elif col.startswith('avg_return_'):
                            gb.configure_column(col, type=['numericColumn', 'numberColumnFilter'], precision=2, width=100)  # 12-16 chars: "avg_return_XXX"
                    
                    # Enable pagination for large datasets
                    gb.configure_pagination(paginationAutoPageSize=True)
                    
                    grid_options = gb.build()
                    
                    # Suppress the grid's auto-sizing to enforce our fixed-width columns
                    grid_options['suppressSizeToFit'] = True
                    
                    # Display AgGrid
                    grid_response = AgGrid(
                        df,
                        gridOptions=grid_options,
                        data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
                        update_mode=GridUpdateMode.SELECTION_CHANGED,
                        fit_columns_on_grid_load=False,  # Use custom sizing
                        theme='streamlit',
                        height=425,
                        width='100%',
                        key=f"mc_waikiki_aggrid_{tab_key}_{selected_file}",
                        reload_data=False,
                        allow_unsafe_jscode=True
                    )
                    
                    # Handle selection
                    selected_rows = grid_response['selected_rows']
                    if selected_rows is not None and len(selected_rows) > 0:
                        selected_row = selected_rows.iloc[0]  # Take first selected row
                        new_ticker = selected_row['ticker']
                        new_interval = selected_row['interval']
                        
                        # Update session state if selection changed
                        if (st.session_state.mc_selected_ticker != new_ticker or
                            st.session_state.mc_selected_interval != new_interval):
                            st.session_state.mc_selected_ticker = new_ticker
                            st.session_state.mc_selected_interval = new_interval
                            st.rerun()
                    
                    return grid_response['data']
                else:
                    st.info("No data available for this table. Please run analysis first.")
                    return None

            tabs = st.tabs([
                "Best Intervals (50)", 
                "Best Intervals (20)", 
                "Best Intervals (100)", 
                "High Return Intervals",
                "Interval Details"
            ])

            # Display best intervals (50) - for MC, best means most negative returns
            with tabs[0]:
                df, message = load_results('mc_eval_best_intervals_50_', selected_file, 'avg_return_10')
                if df is not None:
                    if mc_waikiki_ticker_filter:
                        df = df[df['ticker'].str.contains(mc_waikiki_ticker_filter, case=False)]
                    
                    if 'interval' in df.columns:
                        intervals = sorted(df['interval'].unique())
                        selected_intervals = st.multiselect("Filter by interval:", intervals, default=intervals, key=f"mc_interval_filter_best_50_{selected_file}")
                        if selected_intervals:
                            df = df[df['interval'].isin(selected_intervals)]
                    mc_waikiki_aggrid_editor(df, '50')
                else:
                    st.info("No best intervals data available for 50-period analysis. Please run MC Signal Evaluation first.")

            # Display best intervals (20)
            with tabs[1]:
                df, message = load_results('mc_eval_best_intervals_20_', selected_file, 'avg_return_10')
                if df is not None:
                    if mc_waikiki_ticker_filter:
                        df = df[df['ticker'].str.contains(mc_waikiki_ticker_filter, case=False)]
                    
                    if 'interval' in df.columns:
                        intervals = sorted(df['interval'].unique())
                        selected_intervals = st.multiselect("Filter by interval:", intervals, default=intervals, key=f"mc_interval_filter_best_20_{selected_file}")
                        if selected_intervals:
                            df = df[df['interval'].isin(selected_intervals)]
                    mc_waikiki_aggrid_editor(df, '20')
                else:
                    st.info("No best intervals data available for 20-period analysis. Please run MC Signal Evaluation first.")

            # Display best intervals (100)
            with tabs[2]:
                df, message = load_results('mc_eval_best_intervals_100_', selected_file, 'avg_return_10')
                if df is not None:
                    if mc_waikiki_ticker_filter:
                        df = df[df['ticker'].str.contains(mc_waikiki_ticker_filter, case=False)]
                    
                    if 'interval' in df.columns:
                        intervals = sorted(df['interval'].unique())
                        selected_intervals = st.multiselect("Filter by interval:", intervals, default=intervals, key=f"mc_interval_filter_best_100_{selected_file}")
                        if selected_intervals:
                            df = df[df['interval'].isin(selected_intervals)]
                    mc_waikiki_aggrid_editor(df, '100')
                else:
                    st.info("No best intervals data available for 100-period analysis. Please run MC Signal Evaluation first.")

            # Display high return intervals (negative returns for MC)
            with tabs[3]:
                df, message = load_results('mc_eval_good_signals_', selected_file, 'latest_signal')
                if df is not None:
                    if mc_waikiki_ticker_filter:
                        df = df[df['ticker'].str.contains(mc_waikiki_ticker_filter, case=False)]
                    
                    if 'latest_signal' in df.columns:
                        df = df[df['latest_signal'].notna()]
                        df = df.sort_values(by='latest_signal', ascending=False)
                        if 'interval' in df.columns:
                            intervals = sorted(df['interval'].unique())
                            selected_intervals = st.multiselect("Filter by interval:", intervals, default=intervals, key=f"mc_interval_filter_recent_{selected_file}")
                            if selected_intervals:
                                df = df[df['interval'].isin(selected_intervals)]
                        mc_waikiki_aggrid_editor(df, 'good')
                    else:
                        st.info("No signal date information available in the results.")
                else:
                    st.info("No recent signals data available. Please run an analysis first.")

            # Display interval details
            with tabs[4]:
                df, message = load_results('mc_eval_custom_detailed_', selected_file, 'avg_return_10')
                if df is not None:
                    if mc_waikiki_ticker_filter:
                        df = df[df['ticker'].str.contains(mc_waikiki_ticker_filter, case=False)]
                    
                    if 'interval' in df.columns:
                        intervals = sorted(df['interval'].unique())
                        selected_intervals = st.multiselect("Filter by interval:", intervals, default=intervals, key=f"mc_interval_filter_details_{selected_file}")
                        if selected_intervals:
                            df = df[df['interval'].isin(selected_intervals)]
                    mc_waikiki_aggrid_editor(df, 'details')
                else:
                    st.info("No interval summary data available. Please run MC Signal Evaluation first.")

        # Resonance Model section
        st.subheader("Resonance Model")
        
        # Add shared ticker filter for MC Resonance model
        mc_resonance_ticker_filter = st.text_input("Filter by ticker symbol:", key=f"mc_resonance_ticker_filter_{selected_file}")
        
        # Helper for AgGrid in MC Resonance model
        def mc_resonance_aggrid_editor(df, tab_key, selection_enabled=True):
            if df is not None and not df.empty:
                df = df.copy()
                # To prevent ArrowTypeError from mixed types, convert object columns to string
                for col in df.columns:
                    if df[col].dtype == 'object':
                        df[col] = df[col].astype(str)

                gb = GridOptionsBuilder.from_dataframe(df)
                gb.configure_default_column(editable=False, filterable=True, sortable=True, resizable=True)
                gb.configure_pagination(paginationAutoPageSize=True)
                
                if selection_enabled:
                    gb.configure_selection('single', use_checkbox=True, groupSelectsChildren=False, groupSelectsFiltered=False)

                if 'ticker' in df.columns:
                    gb.configure_column('ticker', pinned='left', minWidth=90)
                if 'date' in df.columns:
                    gb.configure_column('date', minWidth=120)
                if 'signal_date' in df.columns:
                    gb.configure_column('signal_date', minWidth=120)

                grid_options = gb.build()
                
                ag_grid_params = {
                    'gridOptions': grid_options,
                    'fit_columns_on_grid_load': True,
                    'theme': 'streamlit',
                    'height': 350,
                    'width': '100%',
                    'key': f"mc_resonance_aggrid_{tab_key}_{selected_file}",
                    'reload_data': False,
                    'allow_unsafe_jscode': True
                }

                if selection_enabled:
                    grid_response = AgGrid(
                        df,
                        data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
                        update_mode=GridUpdateMode.SELECTION_CHANGED,
                        **ag_grid_params
                    )
                    return grid_response
                else:
                    AgGrid(df, **ag_grid_params)
                    return None

        # Create two columns for 1234 and 5230 data
        col_1234, col_5230 = st.columns([1, 1])

        # Left column: 1234 data
        with col_1234:
            st.markdown("### 1234 Model")
            tab_1234_candidates, tab_1234_details = st.tabs(["Candidates", "Details"])

            # Display 1234 breakout candidates
            with tab_1234_candidates:
                df, message = load_results('mc_breakout_candidates_summary_1234_', selected_file, 'date')
                
                if df is not None and '1234' in message:
                    # Truncate to most recent 60 days
                    if 'date' in df.columns:
                        df['date'] = pd.to_datetime(df['date'])
                        cutoff_date = pd.Timestamp.now() - pd.Timedelta(days=60)
                        df = df[df['date'] >= cutoff_date]
                        if 'nx_30m_signal' in df.columns:
                            df['nx_30m_signal'] = df['nx_30m_signal'].astype(bool)
                        df['date'] = df['date'].dt.strftime('%Y-%m-%d')

                    if mc_resonance_ticker_filter:
                        df = df[df['ticker'].str.contains(mc_resonance_ticker_filter, case=False)]
                    
                    # Add NX filtering if available
                    nx_filters_applied = False
                    if 'nx_1d_signal' in df.columns:
                        nx_1d_values = sorted(df['nx_1d_signal'].unique())
                        selected_nx_1d = st.multiselect("Filter by NX 1d Signal:", nx_1d_values, 
                                                       default=[False] if False in nx_1d_values else nx_1d_values,
                                                       key=f"mc_nx_1d_filter_1234_{selected_file}")
                        if selected_nx_1d:
                            df = df[df['nx_1d_signal'].isin(selected_nx_1d)]
                            nx_filters_applied = True
                    
                    df_sorted = df.sort_values(by='date', ascending=False)
                    grid_response = mc_resonance_aggrid_editor(df_sorted, 'summary_1234')

                    # Initialize session state for both MC resonance selections
                    if 'mc_resonance_1234_selected' not in st.session_state:
                        st.session_state.mc_resonance_1234_selected = pd.DataFrame()
                    if 'mc_resonance_5230_selected' not in st.session_state:
                        st.session_state.mc_resonance_5230_selected = pd.DataFrame()

                    # Default selection to the first candidate if none are selected
                    if not df_sorted.empty and st.session_state.mc_resonance_1234_selected.empty and st.session_state.mc_resonance_5230_selected.empty:
                        st.session_state.mc_resonance_1234_selected = df_sorted.head(1)

                    # If new selection is made in this grid
                    if grid_response and grid_response['selected_rows'] is not None and not pd.DataFrame(grid_response['selected_rows']).empty:
                        selected_df = pd.DataFrame(grid_response['selected_rows'])
                        # Avoid rerun if selection hasn't changed
                        if not selected_df.equals(st.session_state.mc_resonance_1234_selected):
                            st.session_state.mc_resonance_1234_selected = selected_df
                            st.session_state.mc_resonance_5230_selected = pd.DataFrame()  # Clear other selection
                            st.rerun()
                else:
                    st.info("No MC 1234 breakout candidates found. Please run analysis first.")

            # Display 1234 detailed results
            with tab_1234_details:
                df, message = load_results('mc_breakout_candidates_details_1234_', selected_file, 'signal_date')
                
                if df is not None and '1234' in message:
                    # Truncate to most recent 60 days
                    if 'signal_date' in df.columns:
                        df['signal_date'] = pd.to_datetime(df['signal_date'])
                        cutoff_date = pd.Timestamp.now() - pd.Timedelta(days=60)
                        df = df[df['signal_date'] >= cutoff_date]
                        df['signal_date'] = df['signal_date'].dt.strftime('%Y-%m-%d')

                    if mc_resonance_ticker_filter:
                        df = df[df['ticker'].str.contains(mc_resonance_ticker_filter, case=False)]
                    
                    if 'interval' in df.columns:
                        intervals = sorted(df['interval'].unique())
                        selected_intervals = st.multiselect("Filter by interval:", intervals, 
                                                           default=intervals,
                                                           key=f"mc_interval_filter_1234_{selected_file}")
                        if selected_intervals:
                            df = df[df['interval'].isin(selected_intervals)]
                    
                    # Display the dataframe
                    mc_resonance_aggrid_editor(df.sort_values(by='signal_date', ascending=False), 'details_1234', selection_enabled=False)
                    
                else:
                    st.info("No MC 1234 detailed results found. Please run analysis first.")

        # Right column: 5230 data
        with col_5230:
            st.markdown("### 5230 Model")
            tab_5230_candidates, tab_5230_details = st.tabs(["Candidates", "Details"])

            # Display 5230 breakout candidates
            with tab_5230_candidates:
                df, message = load_results('mc_breakout_candidates_summary_5230_', selected_file, 'date')
                
                if df is not None and '5230' in message:
                    if mc_resonance_ticker_filter:
                        df = df[df['ticker'].str.contains(mc_resonance_ticker_filter, case=False)]
                    
                    # Add NX filtering if available
                    if 'nx_1h_signal' in df.columns:
                        nx_values = sorted(df['nx_1h_signal'].unique())
                        selected_nx = st.multiselect("Filter by NX 1h Signal:", nx_values, 
                                                   default=[False] if False in nx_values else nx_values,
                                                   key=f"mc_nx_filter_5230_{selected_file}")
                        if selected_nx:
                            df = df[df['nx_1h_signal'].isin(selected_nx)]
                    
                    # Display the dataframe
                    grid_response = mc_resonance_aggrid_editor(df.sort_values(by='date', ascending=False), 'summary_5230')

                    # If new selection is made in this grid
                    if grid_response and grid_response['selected_rows'] is not None and not pd.DataFrame(grid_response['selected_rows']).empty:
                        selected_df = pd.DataFrame(grid_response['selected_rows'])
                        # Avoid rerun if selection hasn't changed
                        if not selected_df.equals(st.session_state.mc_resonance_5230_selected):
                            st.session_state.mc_resonance_5230_selected = selected_df
                            st.session_state.mc_resonance_1234_selected = pd.DataFrame()  # Clear other selection
                            st.rerun()
                else:
                    st.info("No MC 5230 breakout candidates found. Please run analysis first.")

            # Display 5230 detailed results
            with tab_5230_details:
                df, message = load_results('mc_breakout_candidates_details_5230_', selected_file, 'signal_date')
                
                if df is not None and '5230' in message:
                    if mc_resonance_ticker_filter:
                        df = df[df['ticker'].str.contains(mc_resonance_ticker_filter, case=False)]
                    
                    if 'interval' in df.columns:
                        intervals = sorted(df['interval'].unique())
                        selected_intervals = st.multiselect("Filter by interval:", intervals, 
                                                           default=intervals,
                                                           key=f"mc_interval_filter_5230_{selected_file}")
                        if selected_intervals:
                            df = df[df['interval'].isin(selected_intervals)]
                    
                    # Display the dataframe
                    mc_resonance_aggrid_editor(df.sort_values(by='signal_date', ascending=False), 'details_5230', selection_enabled=False)
                    
                else:
                    st.info("No MC 5230 detailed results found. Please run analysis first.")


        # Determine which selection to use for MC resonance
        mc_selected_candidates = pd.DataFrame()
        mc_source_model = None
        if 'mc_resonance_1234_selected' in st.session_state and not st.session_state.mc_resonance_1234_selected.empty:
            mc_selected_candidates = st.session_state.mc_resonance_1234_selected
            mc_source_model = '1234'
        elif 'mc_resonance_5230_selected' in st.session_state and not st.session_state.mc_resonance_5230_selected.empty:
            mc_selected_candidates = st.session_state.mc_resonance_5230_selected
            mc_source_model = '5230'

        if not mc_selected_candidates.empty:
            # Load detailed data from MC waikiki model
            mc_detailed_df, _ = load_results('mc_eval_custom_detailed_', selected_file)
            
            # Load returns distribution data for boxplots
            mc_returns_df, _ = load_results('mc_eval_returns_distribution_', selected_file)

            if mc_detailed_df is None or mc_detailed_df.empty:
                st.warning("Could not load detailed data for MC Waikiki model. Please run analysis to generate `mc_eval_custom_detailed` file.")
            else:
                for index, row in mc_selected_candidates.iterrows():
                    ticker = row['ticker']
                    # The intervals are like "1,2,4". These are hours. I need to convert them to "1h", "2h", "4h".
                    intervals_to_plot_str = row.get('intervals', '')
                    if not intervals_to_plot_str:
                        continue

                    st.markdown(f"#### Plots for {ticker} ({mc_source_model} Model)")
                    
                    # Logic to parse intervals based on source_model
                    if mc_source_model == '1234':
                        intervals_to_plot = [f"{i}h" for i in intervals_to_plot_str.split(',')]
                    elif mc_source_model == '5230':
                        # For 5230 model, use fixed intervals: 5m, 10m, 15m, 30m
                        intervals_to_plot = ['5m', '10m', '15m', '30m']
                    else:
                        intervals_to_plot = []

                    # Create columns for plots
                    plot_cols = st.columns(len(intervals_to_plot))

                    for i, interval in enumerate(intervals_to_plot):
                        with plot_cols[i]:
                            # Filter data for this ticker and interval
                            plot_data = mc_detailed_df[(mc_detailed_df['ticker'] == ticker) & (mc_detailed_df['interval'] == interval)]

                            if plot_data.empty:
                                st.write(f"No detailed data for {ticker} ({interval})")
                                continue
                            
                            selected_ticker_data = plot_data.iloc[0]

                            # Create figure with subplots: price on top, volume on bottom
                            fig = make_subplots(
                                rows=2, cols=1,
                                subplot_titles=('Price Movement After MC Signal', 'Volume'),
                                vertical_spacing=0.1,
                                row_heights=[0.7, 0.3]
                            )
                            
                            # Initialize variables for tracking last price point
                            last_price_period = None
                            last_price_value = None
                            
                            # Filter returns distribution data for boxplot visualization
                            if mc_returns_df is not None and not mc_returns_df.empty:
                                filtered_returns = mc_returns_df[
                                    (mc_returns_df['ticker'] == ticker) &
                                    (mc_returns_df['interval'] == interval)
                                ]
                                
                                if not filtered_returns.empty:
                                    # Get periods that have data
                                    periods_with_data = sorted(filtered_returns['period'].unique())
                                    
                                    # Add boxplots for each period
                                    median_price_values = []
                                    median_periods = []
                                    
                                    # Add volume bars for each period
                                    volume_periods = []
                                    avg_volumes = []
                                    
                                    for period in periods_with_data:
                                        period_data = filtered_returns[filtered_returns['period'] == period]
                                        period_returns = period_data['return'].values
                                        
                                        if len(period_returns) > 0:
                                            # Convert returns to relative price (baseline = 100)
                                            relative_prices = 100 + period_returns
                                            
                                            # Add price boxplot
                                            fig.add_trace(go.Box(
                                                y=relative_prices,
                                                x=[period] * len(relative_prices),
                                                name=f'Period {period}',
                                                boxpoints=False,  # Don't show individual points
                                                showlegend=False,
                                                marker=dict(color='lightgray'),
                                                line=dict(color='lightgray')
                                            ), row=1, col=1)
                                            
                                            # Store median for connecting line
                                            median_price_values.append(100 + np.median(period_returns))
                                            median_periods.append(period)
                                        
                                        # Add volume data if available
                                        if 'volume' in period_data.columns:
                                            period_volumes = period_data['volume'].values
                                            if len(period_volumes) > 0:
                                                avg_volume = np.mean(period_volumes[~np.isnan(period_volumes)])
                                                volume_periods.append(period)
                                                avg_volumes.append(avg_volume)
                                    
                                    # Add median price connection line
                                    if len(median_price_values) > 1:
                                        fig.add_trace(go.Scatter(
                                            x=median_periods,
                                            y=median_price_values,
                                            mode='lines+markers',
                                            line=dict(color='gray', width=1),
                                            marker=dict(color='gray', size=6),
                                            name='Median Returns',
                                            showlegend=False
                                        ), row=1, col=1)
                                    
                                    # Add volume bars (grey bars for average volumes)
                                    if len(avg_volumes) > 0:
                                        fig.add_trace(go.Bar(
                                            x=volume_periods,
                                            y=avg_volumes,
                                            name='Average Volume',
                                            marker_color='lightgray',
                                            showlegend=False
                                        ), row=2, col=1)
                                else:
                                    # Fallback to scatter plot
                                    periods = [0] + list(range(1, 101))  # Full range from 0 to 100
                                    stock_returns = [(0, 100)]  # Start with (0, 100)
                                    for period in periods[1:]:  # Skip 0 as we already added it
                                        if f'avg_return_{period}' in selected_ticker_data and pd.notna(selected_ticker_data[f'avg_return_{period}']):
                                            stock_returns.append((period, 100 + selected_ticker_data[f'avg_return_{period}']))
                                    
                                    if len(stock_returns) > 1:
                                        periods_x, returns_y = zip(*stock_returns)
                                        fig.add_trace(go.Scatter(
                                            x=periods_x,
                                            y=returns_y,
                                            mode='lines+markers',
                                            line=dict(color='lightgray', width=1),
                                            marker=dict(color='gray', size=6),
                                            name=f"{ticker} ({interval})",
                                        ), row=1, col=1)
                                    
                                    # Add volume bars for fallback case
                                    volume_periods = []
                                    avg_volumes = []
                                    for period in periods[1:]:
                                        if f'avg_volume_{period}' in selected_ticker_data:
                                            volume_periods.append(period)
                                            avg_volumes.append(selected_ticker_data[f'avg_volume_{period}'])
                                    
                                    if len(avg_volumes) > 0:
                                        fig.add_trace(go.Bar(
                                            x=volume_periods,
                                            y=avg_volumes,
                                            name='Average Volume',
                                            marker_color='lightgray',
                                            showlegend=False
                                        ), row=2, col=1)
                            else:
                                # Fallback to scatter plot if no returns distribution data
                                periods = [0] + list(range(1, 101))  # Full range from 0 to 100
                                stock_returns = [(0, 100)]
                                for period in periods[1:]:
                                    if f'avg_return_{period}' in selected_ticker_data and pd.notna(selected_ticker_data[f'avg_return_{period}']):
                                        stock_returns.append((period, 100 + selected_ticker_data[f'avg_return_{period}']))
                                
                                if len(stock_returns) > 1:
                                    periods_x, returns_y = zip(*stock_returns)
                                    fig.add_trace(go.Scatter(
                                        x=periods_x,
                                        y=returns_y,
                                        mode='lines+markers',
                                        line=dict(color='lightgray', width=1),
                                        marker=dict(color='gray', size=6),
                                        name=f"{ticker} ({interval})",
                                    ), row=1, col=1)
                                
                                # Add volume bars
                                volume_periods = []
                                avg_volumes = []
                                for period in periods[1:]:
                                    if f'avg_volume_{period}' in selected_ticker_data:
                                        volume_periods.append(period)
                                        avg_volumes.append(selected_ticker_data[f'avg_volume_{period}'])
                                
                                if len(avg_volumes) > 0:
                                    fig.add_trace(go.Bar(
                                        x=volume_periods,
                                        y=avg_volumes,
                                        name='Average Volume',
                                        marker_color='lightgray',
                                        showlegend=False
                                    ), row=2, col=1)
                            
                            # Add actual price history if available
                            if 'price_history' in selected_ticker_data and selected_ticker_data['price_history']:
                                price_history = selected_ticker_data['price_history']
                                if isinstance(price_history, str):
                                    # Handle case where price_history might be stored as string
                                    try:
                                        import ast
                                        price_history = ast.literal_eval(str(price_history))
                                    except Exception:
                                        # If parsing fails, silently set to empty dict to avoid spam
                                        price_history = {}
                                
                                if price_history and 0 in price_history and price_history[0] is not None:
                                    entry_price = float(price_history[0])
                                    price_periods = []
                                    price_values = []
                                    
                                    # Collect price history points
                                    for period in sorted(price_history.keys()):
                                        if price_history[period] is not None and period >= 0:
                                            try:
                                                relative_price = (float(price_history[period]) / entry_price) * 100
                                                price_periods.append(period)
                                                price_values.append(relative_price)
                                            except (ValueError, TypeError):
                                                continue
                                    
                                    # Add price history line and dots
                                    if len(price_periods) > 1:
                                        fig.add_trace(go.Scatter(
                                            x=price_periods,
                                            y=price_values,
                                            mode='lines+markers',
                                            line=dict(color='red', width=1),
                                            marker=dict(color='red', size=6),
                                            name='Price History',
                                            showlegend=True
                                        ), row=1, col=1)
                                    elif len(price_periods) == 1:
                                        # Single point case
                                        fig.add_trace(go.Scatter(
                                            x=price_periods,
                                            y=price_values,
                                            mode='markers',
                                            marker=dict(color='red', size=6),
                                            name='Price History',
                                            showlegend=True
                                        ), row=1, col=1)
                                    
                                    # Store the last price history point for connecting to current price
                                    if price_periods:
                                        last_price_period = price_periods[-1]
                                        last_price_value = price_values[-1]
                            
                            # Add actual volume history if available
                            if 'volume_history' in selected_ticker_data and selected_ticker_data['volume_history']:
                                volume_history = selected_ticker_data['volume_history']
                                if isinstance(volume_history, str):
                                    try:
                                        import ast
                                        volume_history = ast.literal_eval(str(volume_history))
                                    except Exception:
                                        # If parsing fails, silently set to empty dict to avoid spam
                                        volume_history = {}
                                
                                if volume_history and 0 in volume_history and volume_history[0] is not None:
                                    volume_periods = []
                                    volume_values = []
                                    
                                    # Collect volume history points
                                    for period in sorted(volume_history.keys()):
                                        if volume_history[period] is not None and period >= 0:
                                            try:
                                                volume_periods.append(period)
                                                volume_values.append(float(volume_history[period]))
                                            except (ValueError, TypeError):
                                                continue
                                    
                                    # Add volume history line (red lines for latest signal)
                                    if len(volume_periods) > 1:
                                        fig.add_trace(go.Scatter(
                                            x=volume_periods,
                                            y=volume_values,
                                            mode='lines+markers',
                                            line=dict(color='red', width=2),
                                            marker=dict(color='red', size=6),
                                            name='Latest Signal Volume',
                                            showlegend=True
                                        ), row=2, col=1)
                                    elif len(volume_periods) == 1:
                                        # Single point case
                                        fig.add_trace(go.Scatter(
                                            x=volume_periods,
                                            y=volume_values,
                                            mode='markers',
                                            marker=dict(color='red', size=6),
                                            name='Latest Signal Volume',
                                            showlegend=True
                                        ), row=2, col=1)
                        
                            # Add baseline reference line at y=100 (add after all traces for visibility)
                            fig.add_hline(y=100, line_dash="dash", line_color="gray", line_width=1, 
                                         annotation_text="Short Price (Baseline)", annotation_position="top right", row=1, col=1)
                            
                            # Find the first period with data (usually period 3)
                            first_period = None
                            first_value = None
                            
                            # Use continuous range for consistent visualization
                            # Skip boxplot data check and use scatter plot data
                            if False:  # Disable boxplot data check to force continuous range
                                filtered_returns = mc_returns_df[
                                    (mc_returns_df['ticker'] == ticker) &
                                    (mc_returns_df['interval'] == interval)
                                ]
                                if not filtered_returns.empty:
                                    periods_with_data = sorted(filtered_returns['period'].unique())
                                    if periods_with_data:
                                        first_period = periods_with_data[0]
                                        period_returns = filtered_returns[filtered_returns['period'] == first_period]['return'].values
                                        if len(period_returns) > 0:
                                            first_value = 100 + np.median(period_returns)
                            
                            # If no boxplot data, use scatter plot data
                            if first_period is None or first_value is None:
                                periods = list(range(1, 101))  # Full range from 1 to 100
                                for period in periods:
                                    if f'avg_return_{period}' in selected_ticker_data and pd.notna(selected_ticker_data[f'avg_return_{period}']):
                                        first_period = period
                                        first_value = 100 + selected_ticker_data[f'avg_return_{period}']
                                        break
                            
                            # Add connecting line if we found a first data point
                            if first_period is not None and first_value is not None:
                                fig.add_trace(go.Scatter(
                                    x=[0, first_period],
                                    y=[100, first_value],
                                    mode='lines',
                                    line=dict(color='gray', width=1),
                                    name='Baseline Connection',
                                    showlegend=False
                                ), row=1, col=1)
                            
                            # Highlight best period (for MC signals, best means most negative return)
                            min_return = float('inf')
                            best_period = None
                            periods = list(range(1, 101))  # Full range from 1 to 100
                            for period in periods:
                                if f'avg_return_{period}' in selected_ticker_data and pd.notna(selected_ticker_data[f'avg_return_{period}']):
                                    if selected_ticker_data[f'avg_return_{period}'] < min_return:
                                        min_return = selected_ticker_data[f'avg_return_{period}']
                                        best_period = period
                            
                            title_html = (
                                f"<span style='font-size:16px'><b>{ticker} ({interval})</b></span><br>"
                            )
                            if best_period is not None:
                                 title_html += (f"<span style='font-size:10px'>best period: {best_period} | "
                                f"return: {min_return:.2f}% | "
                                f"success: {selected_ticker_data.get(f'success_rate_{best_period}', 0):.2f}  "
                                f"test count: {selected_ticker_data.get(f'test_count_{best_period}', 0)}</span>")
                            
                            fig.update_layout(
                                title=dict(text=title_html, 
                                            x=0.5, 
                                            font=dict(color='black'),
                                            xanchor='center',
                                            yanchor='top'),
                                showlegend=False,
                                height=400,  # Increased height for dual subplots
                                plot_bgcolor='white',
                                paper_bgcolor='white'
                            )
                            
                            # Update axes for subplots with synchronized x-axis
                            fig.update_xaxes(
                                title_text="Period", 
                                row=1, col=1,
                                range=[-5, 105],  # Set consistent x-axis range
                                showgrid=True,
                                gridwidth=1,
                                gridcolor='lightgray',
                                showline=True,
                                linewidth=1,
                                linecolor='black',
                                tickfont=dict(color='black'),
                                title=dict(text="Period", font=dict(color='black'))
                            )
                            fig.update_xaxes(
                                title_text="Period", 
                                row=2, col=1,
                                range=[-5, 105],  # Same x-axis range as top subplot
                                showgrid=True,
                                gridwidth=1,
                                gridcolor='lightgray',
                                showline=True,
                                linewidth=1,
                                linecolor='black',
                                tickfont=dict(color='black'),
                                title=dict(text="Period", font=dict(color='black'))
                            )
                            fig.update_yaxes(
                                title_text="Relative Price (Baseline = 100)", 
                                row=1, col=1,
                                showgrid=True,
                                gridwidth=1,
                                gridcolor='lightgray',
                                showline=True,
                                linewidth=1,
                                linecolor='black',
                                tickfont=dict(color='black'),
                                title=dict(text="Relative Price (Baseline = 100)", font=dict(color='black'))
                            )
                            fig.update_yaxes(
                                title_text="Volume", 
                                row=2, col=1,
                                showgrid=True,
                                gridwidth=1,
                                gridcolor='lightgray',
                                showline=True,
                                linewidth=1,
                                linecolor='black',
                                tickfont=dict(color='black'),
                                title=dict(text="Volume", font=dict(color='black'))
                            )
                            
                            st.plotly_chart(fig, use_container_width=True)

    else:
        st.info("👆 Please select a stock list above to view MC analysis results.")

# Footer
st.markdown("---")
st.markdown("Stock Analysis Dashboard | Created with Streamlit") 