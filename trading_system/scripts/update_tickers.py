import pandas as pd
import requests

def download_sp500():
    print("Downloading S&P 500 list from Wikipedia...")
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
    response = requests.get(url, headers=headers)
    
    # We use flavor='html5lib' to prevent missing parser errors
    table = pd.read_html(response.text, flavor='html5lib')
    df = table[0]
    
    universe = df['Symbol'].tolist()
    universe = [sym.replace('.', '-') for sym in universe]
    
    with open("d:/paper_trading_bot/trading_system/data/sp500_tickers.txt", "w") as f:
        for sym in universe:
            f.write(sym + "\n")
            
    print(f"Successfully saved {len(universe)} symbols to sp500_tickers.txt!")

if __name__ == "__main__":
    download_sp500()
