# StockBoard

Stockboard is a Streamlit stock analysis dashboard with SQL-powered screening. I created it with open-source code published to GitHub to allow beginners looking to get into finance + CS. The code is annotated with functions to help you understand what each line of code does.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run the app:
```bash
streamlit run app.py
```

3. Open your browser to `http://localhost:8501`

## Features

- **Overview** — Live price, candlestick chart with 50/200 MA, volume
- **Technicals** — RSI, MACD, Bollinger Bands, Stochastic
- **Fundamentals** — Valuation, profitability, financial health, multi-stock comparison
- **SQL Analysis** — Query all saved stock data, preset screens, auto-charts, CSV export
- **Portfolio** — Log trades, track P&L live

## SQL Tables

| Table | Description |
|-------|-------------|
| `stock_fundamentals` | Saved each time you view a stock |
| `watchlist` | Stocks you're watching |
| `portfolio` | Your logged trades |

## Example SQL Screens

```sql
-- Find cheap & profitable stocks
SELECT ticker, pe_ratio, ROUND(profit_margin*100,2) as margin_pct
FROM stock_fundamentals
WHERE pe_ratio < 20 AND profit_margin > 0.15
ORDER BY pe_ratio ASC

-- Compare ROE across stocks
SELECT ticker, ROUND(roe*100,2) as roe_pct
FROM stock_fundamentals
ORDER BY roe DESC
```
