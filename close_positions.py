import config
from broker.alpaca_client import AlpacaClient
b = AlpacaClient(paper=True, api_key=config.ALPACA_API_KEY, api_secret=config.ALPACA_SECRET_KEY)
positions = b.get_positions()
print('Open positions:', positions)
for p in positions:
    sym = p.get('symbol','') if isinstance(p, dict) else str(p)
    try:
        b.trading.close_position(sym)
        print('Closed:', sym)
    except Exception as e:
        print('Error:', sym, e)
