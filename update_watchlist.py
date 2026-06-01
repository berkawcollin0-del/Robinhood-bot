import ftplib

def build_nasdaq_watchlist():
    print("Connecting to official NASDAQ server...")
    ftp = ftplib.FTP('ftp.nasdaqtrader.com')
    ftp.login('anonymous', '')
    
    lines = []
    # Download the live NASDAQ listed securities text file
    ftp.retrlines('RETR SymbolDirectory/nasdaqlisted.txt', lines.append)
    ftp.quit()
    
    tickers = []
    # Skip the first line (header) and the last line (file creation time)
    for line in lines[1:-1]:
        data = line.split('|')
        
        # data[0] is the Ticker Symbol
        # data[3] is the 'Test Issue' flag (we only want 'N' for No)
        if len(data) > 3 and data[3] == 'N': 
            symbol = data[0]
            
            # Filter for standard common stock (ignore warrants/rights, which usually exceed 4 characters)
            if len(symbol) <= 4 and symbol.isalpha():
                tickers.append(symbol)

    print(f"Successfully downloaded {len(tickers)} active NASDAQ tickers.")
    
    # Generate the tickers.py file for your bot
    with open('tickers.py', 'w') as f:
        f.write('WATCHLIST = [\n')
        # Group tickers 12 per line to keep the file somewhat readable
        for i in range(0, len(tickers), 12):
            row_tickers = tickers[i:i+12]
            formatted_row = ", ".join([f"'{t}'" for t in row_tickers])
            f.write(f"    {formatted_row},\n")
        f.write(']\n')
        
    print("Generated 'tickers.py'. Your bot is ready to scan the entire exchange!")

if __name__ == "__main__":
    build_nasdaq_watchlist()
