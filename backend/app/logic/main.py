from stock_analyzer import analyze_stocks
import os

if __name__ == '__main__':
    # Create output directory if it doesn't exist
    os.makedirs('./output', exist_ok=True)
    
    print("Running comprehensive stock analysis: 1234, 5230, CD Signal Evaluation")
    
    # Uncomment the file path you want to use:
    # analyze_stocks('/Users/foreverycc/git/stock_list/stocks_all_sel.txt')
    # analyze_stocks('/Users/foreverycc/git/stock_list/stocks_all.txt')
    analyze_stocks('./data/stocks_custom.tab', end_date=None)
    
    print("Analysis complete. Results saved to ./output/ directory")
