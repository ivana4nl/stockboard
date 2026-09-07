import streamlit as st #imports the streamlit library (with the abbreviation st) to build the UI
import yfinance as yf #imports yahoo finance (with the abbreviation yf) to get live stock data
import pandas as pd #imports pandas (abbreviated pd) which is the standard python library for working with tables of data
import plotly.graph_objects as go #from plotly; helps build charts in pieces (candlesticks & MCAD charts)
import plotly.express as px #from plotly; simpler charts such as bar charts
from plotly.subplots import make_subplots #from plotly; lets you stack multiple charts
import sqlite3 #imports pythons database library. it powers the entire SQL analysis tab
import ta #imports technical analysis library. this does the math for indicators (RSI, bollinger bands, etc)
from datetime import datetime, timedelta #imports current date and time as well as date math (ex. 30 days ago)
import warnings #imports pythons built in warning control library
warnings.filterwarnings('ignore') #for yahoo finance potential warnings about data

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config( #tells streamlit how you want the page configured
    page_title="Stockboard", #title shown in browser tab
    layout="wide", #makes the page more expanded horizontally
    initial_sidebar_state="expanded" #makes sidebar expanded when you open the site
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
#css to set the theme of the website w the colors used & fonts
st.markdown("""
<style>
    .main { background-color: #0e1117; }
    .metric-card {
        background: linear-gradient(135deg, #1a1f2e, #252d3d); #diagonal color fade for the cards
        border: 1px solid #2d3748; #subtle border around each card
        border-radius: 12px; #rounds the corners of the cards
        padding: 16px 20px; #space inside the card so text doesnt touch the edges
        margin: 6px 0; #small gap above and below each card
    }
    .metric-label { color: #8892a4; font-size: 12px; text-transform: uppercase; letter-spacing: 1px; } #styles the small grey label text at the top of each card
    .metric-value { color: #e2e8f0; font-size: 22px; font-weight: 700; margin-top: 4px; } #styles the big number value in each card
    .metric-delta-pos { color: #1d4731; font-size: 13px; } #dark green color for positive changes
    .metric-delta-neg { color: #742a2a; font-size: 13px; } #dark red color for negative changes
    .section-header {
        color: #e2e8f0; #bright white text for section titles
        font-size: 18px; #slightly larger than body text
        font-weight: 600; #semi-bold
        border-left: 3px solid #1a365d; #the dark blue vertical bar on the left of each section title
        padding-left: 12px; #space between the blue bar and the text
        margin: 20px 0 12px 0; #space above and below each section header
    }
    .stTabs [data-baseweb="tab"] { color: #8892a4; } #makes inactive tabs grey
    .stTabs [aria-selected="true"] { color: #1a365d !important; } #makes the active tab dark blue
    div[data-testid="stSidebar"] { background-color: #131722; } #sets the sidebar background color
    .sql-result { background: #1a1f2e; border-radius: 8px; padding: 12px; } #styles the sql results area
    .block-container { padding-top: 1rem !important; } #reduces the top padding on the main page
    section[data-testid="stSidebar"] > div { padding-top: 1rem !important; } #reduces the top padding in the sidebar
</style>
""", unsafe_allow_html=True) #allows HTML and CSS directly into the page and override Streamlits default look

# ── Database setup ────────────────────────────────────────────────────────────
import os #imports pythons built in operating system library
DB_PATH = os.path.join(os.path.dirname(__file__), "stocks.db") #builds the file path for the database
def init_db(): #defines a function
    conn = sqlite3.connect(DB_PATH) #opens a connection to database at the path that was just defined
    c = conn.cursor() #creates a cursor whcih sends SQL commands to database
    c.execute("""
        CREATE TABLE IF NOT EXISTS watchlist ( #creates watchlist table only if it doesnt already exist (wont wipe data on restart)
            ticker TEXT PRIMARY KEY, #ticker is the unique identifier, cant add the same stock twice
            added_date TEXT, #stores the date you added the stock as a string like "2026-09-06"
            notes TEXT #plain text field for any notes, can be empty
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS stock_fundamentals ( #creates fundamentals table, stores data every time you view a stock
            ticker TEXT, #ticker column, not a primary key on its own because same stock can appear on multiple dates
            snapshot_date TEXT, #the date the data was saved
            price REAL, #REAL means a decimal number
            market_cap REAL, #total market value of the company
            pe_ratio REAL, #price to earnings ratio (trailing twelve months)
            forward_pe REAL, #pe ratio based on projected future earnings
            eps REAL, #earnings per share
            revenue REAL, #total revenue trailing twelve months
            profit_margin REAL, #stored as a decimal ex. 0.23 = 23%
            debt_to_equity REAL, #how much debt vs shareholder equity
            roe REAL, #return on equity; also stored as decimal
            dividend_yield REAL, #annual dividend as a % of price; stored as decimal
            week_52_high REAL, #highest price in the last 52 weeks
            week_52_low REAL, #lowest price in the last 52 weeks
            beta REAL, #measures how volatile the stock is relative to the market
            PRIMARY KEY (ticker, snapshot_date) #composite key; the combination of ticker AND date must be unique
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS portfolio ( #creates portfolio table to store your trades
            id INTEGER PRIMARY KEY AUTOINCREMENT, #auto assigns a unique id number to each trade (1, 2, 3...) used when deleting
            ticker TEXT, #the stock symbol
            shares REAL, #REAL because you can own fractional shares
            buy_price REAL, #REAL because prices have decimals like $182.47
            buy_date TEXT, #stored as a string like "2026-09-06"
            notes TEXT #any notes you want to attach to the trade
        )
    """)
    conn.commit() #saves all changes to disk, nothing is written until you commit
    conn.close() #closes the connection and releases the database file

init_db() #calls the function

# ── Helper functions ──────────────────────────────────────────────────────────
@st.cache_data(ttl=300) #caches the result for 300 seconds (5 min) so it doesnt re-fetch from yahoo finance on every click
def get_stock_data(ticker, period="6mo"): #fetches live stock data; hist = price history, info = company fundamentals
    try: #wraps the fetch in a try block so errors dont crash the app
        stock = yf.Ticker(ticker) #creates a yfinance ticker object for the stock
        hist = stock.history(period=period) #fetches historical price/volume data as a dataframe
        info = stock.info #returns a dictionary of hundreds of fundamental data points
        return hist, info #returns both pieces of data back to whoever called this function
    except:
        return None, None #if anything goes wrong (bad ticker, no internet) returns None instead of crashing

def save_fundamentals(ticker, info): #called every time you view a stock so data is always up to date in the database
    if not info: #if yahoo finance returned nothing, theres nothing to save so exit immediately
        return
    conn = sqlite3.connect(DB_PATH) #opens a fresh connection to the database
    today = datetime.now().strftime("%Y-%m-%d") #gets todays date formatted as "2026-09-06"
    try:
        conn.execute("""
            INSERT OR REPLACE INTO stock_fundamentals #inserts new row, or overwrites if same ticker+date already exists
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, ( #the ? placeholders safely pass values into sql, prevents sql injection
            ticker, today,
            info.get("currentPrice") or info.get("regularMarketPrice"), #tries first key, falls back to second if missing
            info.get("marketCap"), #each info.get() pulls one field from the yahoo finance dictionary
            info.get("trailingPE"),
            info.get("forwardPE"),
            info.get("trailingEps"),
            info.get("totalRevenue"),
            info.get("profitMargins"),
            info.get("debtToEquity"),
            info.get("returnOnEquity"),
            info.get("dividendYield"),
            info.get("fiftyTwoWeekHigh"),
            info.get("fiftyTwoWeekLow"),
            info.get("beta"),
        ))
        conn.commit() #saves the insert to disk
    except:
        pass #silently ignores errors so a bad data field doesnt crash the whole app
    conn.close() #always close the connection when done

def add_to_watchlist(ticker, notes=""): #notes="" means notes is optional, defaults to empty string if not provided
    conn = sqlite3.connect(DB_PATH)
    today = datetime.now().strftime("%Y-%m-%d") #timestamps when you added the stock
    try:
        conn.execute("INSERT OR IGNORE INTO watchlist VALUES (?,?,?)", (ticker.upper(), today, notes)) #INSERT OR IGNORE silently does nothing if ticker already exists
        conn.commit() #saves the new watchlist entry to disk
    except:
        pass #silently ignores any errors
    conn.close()

def get_watchlist():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql("SELECT * FROM watchlist ORDER BY added_date DESC", conn) #reads entire watchlist table, newest first, returns as dataframe
    conn.close() #closes connection after reading
    return df #sends the dataframe back to wherever this function was called from

def run_sql(query):
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql(query, conn) #runs whatever sql you typed and returns it as a dataframe
        conn.close()
        return df, None #returns result and no error
    except Exception as e: #catches the specific error message instead of just ignoring it
        conn.close()
        return None, str(e) #returns no result and the error message so the UI can display it in red

def add_portfolio_trade(ticker, shares, buy_price, buy_date, notes=""):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO portfolio (ticker,shares,buy_price,buy_date,notes) VALUES (?,?,?,?,?)",
                 (ticker.upper(), shares, buy_price, buy_date, notes)) #logs a new trade row to the portfolio table
    conn.commit()
    conn.close()

def get_portfolio():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql("SELECT * FROM portfolio ORDER BY buy_date DESC", conn) #reads all trades, most recent first
    conn.close()
    return df

def fmt_large(n): #formats big numbers into readable strings (ex. 1500000000 becomes $1.50B)
    if n is None: return "N/A"
    if n >= 1e12: return f"${n/1e12:.2f}T" #1e12 is scientific notation for 1 trillion
    if n >= 1e9: return f"${n/1e9:.2f}B"
    if n >= 1e6: return f"${n/1e6:.2f}M"
    return f"${n:,.0f}"

def fmt_pct(n): #formats decimal ratios into percentages (ex. yahoo returns 0.23 for 23% margin, this converts it)
    if n is None: return "N/A"
    return f"{n*100:.2f}%"

def color_val(v, good_positive=True): #returns html that colors a value green or red depending on if its positive or negative
    if v is None: return "N/A"
    if isinstance(v, str): return v
    color = "#1d4731" if (v > 0) == good_positive else "#742a2a"
    return f'<span style="color:{color}">{v:+.2f}%</span>' #the + forces the sign to always show (ex. +5.23% not just 5.23%)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar: #everything indented under this renders in the left sidebar
    st.markdown("## 📈 Stock Dashboard")
    st.markdown("---") #renders as a horizontal divider line

    ticker_input = st.text_input("Enter Ticker Symbol", value="AAPL", placeholder="e.g. AAPL, TSLA").upper().strip() #.upper() forces uppercase, .strip() removes accidental spaces
    period_map = {"1 Month": "1mo", "3 Months": "3mo", "6 Months": "6mo", "1 Year": "1y", "2 Years": "2y", "5 Years": "5y"} #maps readable labels to yfinance format strings
    selected_period_label = st.selectbox("Time Period", list(period_map.keys()), index=2) #index=2 means 6 months is selected by default
    selected_period = period_map[selected_period_label] #translates the selected label back to the yfinance string like "6mo"

    st.markdown("---")
    st.markdown("**Add to Watchlist**")
    watch_notes = st.text_input("Notes (optional)", key="watch_notes") #key gives this input a unique id so streamlit can tell it apart from other text inputs
    if st.button("➕ Add to Watchlist", use_container_width=True): #use_container_width stretches button to fill the full sidebar width
        add_to_watchlist(ticker_input, watch_notes)
        st.success(f"{ticker_input} added!") #shows a green confirmation message

    st.markdown("---")
    st.markdown("**Compare Stocks**")
    compare_input = st.text_area("Tickers (one per line)", placeholder="AAPL\nMSFT\nGOOGL", height=100) #multi-line text box
    compare_tickers = [t.strip().upper() for t in compare_input.split("\n") if t.strip()] #splits by newline, strips spaces, filters blank lines, returns a clean list like ["AAPL", "MSFT"]

# ── Main tabs ─────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Overview", "📉 Technicals", "🏦 Fundamentals", "🔍 SQL Analysis", "💼 Portfolio"]) #creates the 5 tabs and assigns each to a variable

# ── Load data ─────────────────────────────────────────────────────────────────
hist, info = get_stock_data(ticker_input, selected_period) #fetches price history and fundamentals using the ticker and period from the sidebar

if hist is None or hist.empty:
    st.error(f"Could not load data for **{ticker_input}**. Check the ticker and try again.")
    st.stop() #halts the entire app so the rest of the code doesnt crash trying to use None as a dataframe

save_fundamentals(ticker_input, info) #saves current stocks fundamentals to the database immediately after loading

company_name = info.get("longName", ticker_input) if info else ticker_input #tries to get full company name, falls back to ticker if missing
current_price = info.get("currentPrice") or info.get("regularMarketPrice") or hist["Close"].iloc[-1] if info else hist["Close"].iloc[-1] #three fallbacks chained with "or" in case some fields are missing
prev_close = info.get("previousClose") or hist["Close"].iloc[-2] if len(hist) > 1 else current_price #iloc[-2] means second to last row = yesterdays close
price_change = current_price - prev_close #todays dollar change
price_change_pct = (price_change / prev_close) * 100 #todays percentage change

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — OVERVIEW
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    col_title, col_price = st.columns([3, 1]) #splits top of page into two columns; [3,1] means left takes 75% right takes 25%
    with col_title:
        st.markdown(f"## {company_name} ({ticker_input})")
        sector = info.get("sector", "") if info else ""
        industry = info.get("industry", "") if info else ""
        if sector: #only shows sector/industry line if the data exists (etfs wont have this)
            st.caption(f"{sector}  ·  {industry}") #st.caption renders smaller grey text

    with col_price:
        delta_color = "#1d4731" if price_change >= 0 else "#742a2a" #green if up, red if down
        arrow = "▲" if price_change >= 0 else "▼"
        st.markdown(f"""
        <div style="text-align:right; padding-top:10px;">
            <div style="font-size:32px; font-weight:700; color:#e2e8f0">${current_price:.2f}</div>
            <div style="font-size:16px; color:{delta_color}">{arrow} {abs(price_change):.2f} ({abs(price_change_pct):.2f}%)</div>
        </div>
        """, unsafe_allow_html=True) #abs() strips the negative sign from losses so you dont see "▼ -1.23%"

    # Key metrics row
    m1, m2, m3, m4, m5, m6 = st.columns(6) #six equal columns for the metric cards
    metrics = [
        ("Market Cap", fmt_large(info.get("marketCap") if info else None)),
        ("P/E Ratio", f"{info.get('trailingPE'):.1f}" if info and info.get('trailingPE') else "N/A"),
        ("EPS (TTM)", f"${info.get('trailingEps'):.2f}" if info and info.get('trailingEps') else "N/A"),
        ("52W High", f"${info.get('fiftyTwoWeekHigh'):.2f}" if info and info.get('fiftyTwoWeekHigh') else "N/A"),
        ("52W Low", f"${info.get('fiftyTwoWeekLow'):.2f}" if info and info.get('fiftyTwoWeekLow') else "N/A"),
        ("Beta", f"{info.get('beta'):.2f}" if info and info.get('beta') else "N/A"),
    ]
    for col, (label, val) in zip([m1,m2,m3,m4,m5,m6], metrics): #zip pairs each column with its metric so you can loop both at once
        with col:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">{label}</div>
                <div class="metric-value">{val}</div>
            </div>""", unsafe_allow_html=True)

    st.markdown("<div class='section-header'>Price Chart</div>", unsafe_allow_html=True)

    # Candlestick + volume chart
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        vertical_spacing=0.03, row_heights=[0.75, 0.25]) #two stacked panels; price takes 75% height, volume takes 25%; shared x-axis means zooming one panel zooms both

    fig.add_trace(go.Candlestick(
        x=hist.index, open=hist["Open"], high=hist["High"],
        low=hist["Low"], close=hist["Close"],
        increasing_line_color="#1d4731", decreasing_line_color="#742a2a", #green candles for up days, red for down
        name="Price"
    ), row=1, col=1) #row=1 col=1 puts this in the top panel

    # 50 & 200 MA
    hist["MA50"] = hist["Close"].rolling(50).mean() #rolling(50) creates a sliding 50-day average; first 49 rows will be NaN
    hist["MA200"] = hist["Close"].rolling(200).mean()
    fig.add_trace(go.Scatter(x=hist.index, y=hist["MA50"], name="50 MA",
                             line=dict(color="#f6ad55", width=1.5)), row=1, col=1) #orange for 50MA
    fig.add_trace(go.Scatter(x=hist.index, y=hist["MA200"], name="200 MA",
                             line=dict(color="#9f7aea", width=1.5)), row=1, col=1) #purple for 200MA

    colors = ["#1d4731" if c >= o else "#742a2a" for c, o in zip(hist["Close"], hist["Open"])] #colors each volume bar green or red based on if that day closed up or down
    fig.add_trace(go.Bar(x=hist.index, y=hist["Volume"], name="Volume",
                         marker_color=colors, opacity=0.7), row=2, col=1) #opacity=0.7 makes bars slightly transparent

    fig.update_layout(
        template="plotly_dark", paper_bgcolor="#0e1117", plot_bgcolor="#0e1117", #paper_bgcolor is outside the chart, plot_bgcolor is inside
        xaxis_rangeslider_visible=False, height=520, margin=dict(l=0, r=0, t=10, b=0), #removes default plotly range slider and padding
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0) #positions legend horizontally above the chart
    )
    st.plotly_chart(fig, use_container_width=True) #renders the finished chart into the app

    # Company description
    if info and info.get("longBusinessSummary"):
        with st.expander("About " + company_name): #collapsible section, closed by default
            st.write(info["longBusinessSummary"])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — TECHNICALS
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.markdown(f"### Technical Indicators — {ticker_input}")

    df = hist.copy() #copies hist before adding indicator columns so the original isnt modified and other tabs arent affected
    # RSI
    df["RSI"] = ta.momentum.RSIIndicator(df["Close"], window=14).rsi() #RSI measures how fast price has been moving; window=14 is the industry standard lookback period
    # MACD
    macd = ta.trend.MACD(df["Close"]) #tracks the relationship between two exponential moving averages (12-day and 26-day)
    df["MACD"] = macd.macd() #the main macd line
    df["MACD_signal"] = macd.macd_signal() #9-day smoothed version of the macd line
    df["MACD_hist"] = macd.macd_diff() #difference between macd and signal line; shown as the histogram bars
    # Bollinger Bands
    bb = ta.volatility.BollingerBands(df["Close"], window=20) #middle band is 20-day MA; upper and lower are 2 standard deviations away
    df["BB_upper"] = bb.bollinger_hband()
    df["BB_lower"] = bb.bollinger_lband()
    df["BB_mid"] = bb.bollinger_mavg()
    # Stochastic
    stoch = ta.momentum.StochasticOscillator(df["High"], df["Low"], df["Close"]) #compares closing price to the price range over the last 14 days
    df["Stoch_k"] = stoch.stoch() #%K is the raw stochastic value
    df["Stoch_d"] = stoch.stoch_signal() #%D is a smoothed average of %K

    # Current readings
    latest = df.iloc[-1] #gets the most recent row of data
    rsi_val = latest["RSI"]
    rsi_signal = "Overbought" if rsi_val > 70 else ("Oversold" if rsi_val < 30 else "Neutral") #above 70 = may be due for pullback, below 30 = may be due for bounce
    rsi_color = "#742a2a" if rsi_val > 70 else ("#1d4731" if rsi_val < 30 else "#f6ad55") #red if overbought, green if oversold, orange if neutral

    macd_signal_txt = "Bullish" if latest["MACD"] > latest["MACD_signal"] else "Bearish" #macd above signal line = upward momentum building
    macd_color = "#1d4731" if macd_signal_txt == "Bullish" else "#742a2a"

    price_vs_bb = "Above Upper Band" if latest["Close"] > latest["BB_upper"] else \
                  ("Below Lower Band" if latest["Close"] < latest["BB_lower"] else "Inside Bands") #three possible states for where price sits relative to the bands
    bb_color = "#742a2a" if "Above" in price_vs_bb else ("#1d4731" if "Below" in price_vs_bb else "#f6ad55")

    c1, c2, c3, c4 = st.columns(4)
    for col, label, val, sub, color in [
        (c1, "RSI (14)", f"{rsi_val:.1f}", rsi_signal, rsi_color),
        (c2, "MACD Signal", macd_signal_txt, f"MACD: {latest['MACD']:.3f}", macd_color),
        (c3, "Bollinger Bands", price_vs_bb, f"Mid: ${latest['BB_mid']:.2f}", bb_color),
        (c4, "Stochastic %K", f"{latest['Stoch_k']:.1f}", f"%D: {latest['Stoch_d']:.1f}", "#8892a4"),
    ]:
        with col:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">{label}</div>
                <div class="metric-value" style="color:{color}; font-size:18px">{val}</div>
                <div style="color:#8892a4; font-size:12px; margin-top:4px">{sub}</div>
            </div>""", unsafe_allow_html=True)

    # RSI chart
    st.markdown("<div class='section-header'>RSI</div>", unsafe_allow_html=True)
    fig_rsi = go.Figure()
    fig_rsi.add_trace(go.Scatter(x=df.index, y=df["RSI"], name="RSI",
                                  line=dict(color="#1a365d", width=2)))
    fig_rsi.add_hline(y=70, line_dash="dash", line_color="#742a2a", annotation_text="Overbought (70)") #dashed horizontal reference lines at the overbought/oversold thresholds
    fig_rsi.add_hline(y=30, line_dash="dash", line_color="#1d4731", annotation_text="Oversold (30)")
    fig_rsi.update_layout(template="plotly_dark", paper_bgcolor="#0e1117",
                           plot_bgcolor="#0e1117", height=250, margin=dict(l=0,r=0,t=10,b=0))
    st.plotly_chart(fig_rsi, use_container_width=True)

    # MACD chart
    st.markdown("<div class='section-header'>MACD</div>", unsafe_allow_html=True)
    fig_macd = make_subplots(rows=1, cols=1)
    fig_macd.add_trace(go.Scatter(x=df.index, y=df["MACD"], name="MACD",
                                   line=dict(color="#1a365d", width=2)))
    fig_macd.add_trace(go.Scatter(x=df.index, y=df["MACD_signal"], name="Signal",
                                   line=dict(color="#f6ad55", width=1.5)))
    colors_macd = ["#1d4731" if v >= 0 else "#742a2a" for v in df["MACD_hist"]] #green bars when momentum building, red when fading
    fig_macd.add_trace(go.Bar(x=df.index, y=df["MACD_hist"], name="Histogram",
                               marker_color=colors_macd, opacity=0.7))
    fig_macd.update_layout(template="plotly_dark", paper_bgcolor="#0e1117",
                            plot_bgcolor="#0e1117", height=250, margin=dict(l=0,r=0,t=10,b=0))
    st.plotly_chart(fig_macd, use_container_width=True)

    # Bollinger Bands chart
    st.markdown("<div class='section-header'>Bollinger Bands</div>", unsafe_allow_html=True)
    fig_bb = go.Figure()
    fig_bb.add_trace(go.Scatter(x=df.index, y=df["BB_upper"], name="Upper",
                                 line=dict(color="#742a2a", width=1, dash="dash")))
    fig_bb.add_trace(go.Scatter(x=df.index, y=df["BB_lower"], name="Lower",
                                 line=dict(color="#1d4731", width=1, dash="dash"),
                                 fill="tonexty", fillcolor="rgba(66,153,225,0.05)")) #fill="tonexty" shades the area between upper and lower bands
    fig_bb.add_trace(go.Scatter(x=df.index, y=df["BB_mid"], name="Mid",
                                 line=dict(color="#8892a4", width=1)))
    fig_bb.add_trace(go.Scatter(x=df.index, y=df["Close"], name="Price",
                                 line=dict(color="#1a365d", width=2)))
    fig_bb.update_layout(template="plotly_dark", paper_bgcolor="#0e1117",
                          plot_bgcolor="#0e1117", height=300, margin=dict(l=0,r=0,t=10,b=0))
    st.plotly_chart(fig_bb, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — FUNDAMENTALS
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.markdown(f"### Fundamentals — {ticker_input}")

    if not info: #etfs and some index funds dont have the same data as individual stocks
        st.warning("Could not load fundamental data for this ticker.")
    else:
        col_a, col_b = st.columns(2) #two equal columns; valuation and growth on left, health and dividends on right

        with col_a:
            st.markdown("<div class='section-header'>Valuation</div>", unsafe_allow_html=True)
            val_data = {
                "P/E Ratio (TTM)": f"{info.get('trailingPE'):.2f}" if info.get('trailingPE') else "N/A",
                "Forward P/E": f"{info.get('forwardPE'):.2f}" if info.get('forwardPE') else "N/A",
                "Price/Sales": f"{info.get('priceToSalesTrailing12Months'):.2f}" if info.get('priceToSalesTrailing12Months') else "N/A",
                "Price/Book": f"{info.get('priceToBook'):.2f}" if info.get('priceToBook') else "N/A",
                "EV/EBITDA": f"{info.get('enterpriseToEbitda'):.2f}" if info.get('enterpriseToEbitda') else "N/A",
                "PEG Ratio": f"{info.get('pegRatio'):.2f}" if info.get('pegRatio') else "N/A",
            }
            for k, v in val_data.items(): #loops through the dictionary and renders each metric as a row with label on left and value on right
                st.markdown(f"<div style='display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #2d3748'><span style='color:#8892a4'>{k}</span><span style='color:#e2e8f0;font-weight:600'>{v}</span></div>", unsafe_allow_html=True)

            st.markdown("<div class='section-header'>Growth & Profitability</div>", unsafe_allow_html=True)
            growth_data = {
                "Revenue (TTM)": fmt_large(info.get('totalRevenue')),
                "Gross Margin": fmt_pct(info.get('grossMargins')),
                "Operating Margin": fmt_pct(info.get('operatingMargins')),
                "Profit Margin": fmt_pct(info.get('profitMargins')),
                "ROE": fmt_pct(info.get('returnOnEquity')),
                "ROA": fmt_pct(info.get('returnOnAssets')),
            }
            for k, v in growth_data.items():
                st.markdown(f"<div style='display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #2d3748'><span style='color:#8892a4'>{k}</span><span style='color:#e2e8f0;font-weight:600'>{v}</span></div>", unsafe_allow_html=True)

        with col_b:
            st.markdown("<div class='section-header'>Financial Health</div>", unsafe_allow_html=True)
            health_data = {
                "Total Cash": fmt_large(info.get('totalCash')),
                "Total Debt": fmt_large(info.get('totalDebt')),
                "Debt/Equity": f"{info.get('debtToEquity'):.2f}" if info.get('debtToEquity') else "N/A",
                "Current Ratio": f"{info.get('currentRatio'):.2f}" if info.get('currentRatio') else "N/A",
                "Free Cash Flow": fmt_large(info.get('freeCashflow')),
                "Operating Cash Flow": fmt_large(info.get('operatingCashflow')),
            }
            for k, v in health_data.items():
                st.markdown(f"<div style='display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #2d3748'><span style='color:#8892a4'>{k}</span><span style='color:#e2e8f0;font-weight:600'>{v}</span></div>", unsafe_allow_html=True)

            st.markdown("<div class='section-header'>Dividends & Ownership</div>", unsafe_allow_html=True)
            div_data = {
                "Dividend Yield": fmt_pct(info.get('dividendYield')),
                "Dividend Rate": f"${info.get('dividendRate'):.2f}" if info.get('dividendRate') else "N/A",
                "Payout Ratio": fmt_pct(info.get('payoutRatio')),
                "Insider Ownership": fmt_pct(info.get('heldPercentInsiders')),
                "Institution Ownership": fmt_pct(info.get('heldPercentInstitutions')),
                "Short % of Float": fmt_pct(info.get('shortPercentOfFloat')),
            }
            for k, v in div_data.items():
                st.markdown(f"<div style='display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #2d3748'><span style='color:#8892a4'>{k}</span><span style='color:#e2e8f0;font-weight:600'>{v}</span></div>", unsafe_allow_html=True)

    # Multi-stock comparison
    if compare_tickers: #only runs if you entered comparison tickers in the sidebar
        st.markdown("---")
        st.markdown("<div class='section-header'>Multi-Stock Comparison</div>", unsafe_allow_html=True)

        all_tickers = list(set([ticker_input] + compare_tickers)) #set() removes duplicates in case you typed the main ticker again
        rows = []
        for t in all_tickers:
            _, inf = get_stock_data(t, "1mo")
            save_fundamentals(t, inf) #saves each compared stock to the database too
            if inf:
                rows.append({ #builds a list of dictionaries, one per stock, each becomes a row in the comparison table
                    "Ticker": t,
                    "Price": inf.get("currentPrice") or inf.get("regularMarketPrice"),
                    "Market Cap": fmt_large(inf.get("marketCap")),
                    "P/E": round(inf.get("trailingPE"), 2) if inf.get("trailingPE") else None,
                    "Fwd P/E": round(inf.get("forwardPE"), 2) if inf.get("forwardPE") else None,
                    "EPS": inf.get("trailingEps"),
                    "Rev (TTM)": fmt_large(inf.get("totalRevenue")),
                    "Profit Margin": fmt_pct(inf.get("profitMargins")),
                    "ROE": fmt_pct(inf.get("returnOnEquity")),
                    "Beta": round(inf.get("beta"), 2) if inf.get("beta") else None,
                })

        if rows:
            comp_df = pd.DataFrame(rows)
            st.dataframe(comp_df.set_index("Ticker"), use_container_width=True) #set_index makes ticker the row label instead of a regular column

            # P/E comparison bar chart
            pe_data = comp_df[comp_df["P/E"].notna()] #filters out stocks where P/E is missing before charting
            if not pe_data.empty:
                fig_pe = px.bar(pe_data, x="Ticker", y="P/E", title="P/E Ratio Comparison",
                                color="Ticker", color_discrete_sequence=px.colors.qualitative.Set2) #Set2 is a built-in colorblind friendly palette
                fig_pe.update_layout(template="plotly_dark", paper_bgcolor="#0e1117",
                                      plot_bgcolor="#0e1117", height=300, showlegend=False,
                                      margin=dict(l=0,r=0,t=40,b=0))
                st.plotly_chart(fig_pe, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — SQL ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════
with tab4:
    st.markdown("### 🔍 SQL Stock Analysis")
    st.markdown("Query your saved stock data directly with SQL. All fundamentals you've viewed are stored automatically.")

    # Schema reference
    with st.expander("📖 Available Tables & Columns"): #collapsible section so the schema doesnt take up permanent space
        st.markdown("""
**`stock_fundamentals`** — saved each time you view a stock
```
ticker, snapshot_date, price, market_cap, pe_ratio, forward_pe,
eps, revenue, profit_margin, debt_to_equity, roe, dividend_yield,
week_52_high, week_52_low, beta
```

**`watchlist`** — stocks you've added to watchlist
```
ticker, added_date, notes
```

**`portfolio`** — your trades
```
id, ticker, shares, buy_price, buy_date, notes
```
        """)

    # Preset queries
    st.markdown("**Quick Queries**")
    presets = { #dictionary of preset sql queries; keys are button labels, values are the actual sql strings
        "All saved stocks": "SELECT ticker, price, pe_ratio, eps, profit_margin, roe FROM stock_fundamentals ORDER BY snapshot_date DESC",
        "Best profit margins": "SELECT ticker, ROUND(profit_margin*100,2) as profit_margin_pct, ROUND(roe*100,2) as roe_pct FROM stock_fundamentals WHERE profit_margin IS NOT NULL ORDER BY profit_margin DESC", #ROUND() is sql math; multiplies by 100 and rounds to 2 decimal places
        "Lowest P/E ratios": "SELECT ticker, price, pe_ratio, forward_pe FROM stock_fundamentals WHERE pe_ratio IS NOT NULL ORDER BY pe_ratio ASC",
        "High dividend yields": "SELECT ticker, price, ROUND(dividend_yield*100,2) as dividend_yield_pct FROM stock_fundamentals WHERE dividend_yield > 0 ORDER BY dividend_yield DESC",
        "Low debt stocks": "SELECT ticker, price, debt_to_equity, ROUND(profit_margin*100,2) as profit_margin_pct FROM stock_fundamentals WHERE debt_to_equity IS NOT NULL ORDER BY debt_to_equity ASC",
        "My watchlist": "SELECT w.ticker, w.added_date, w.notes, f.price, f.pe_ratio FROM watchlist w LEFT JOIN stock_fundamentals f ON w.ticker = f.ticker", #LEFT JOIN combines watchlist and fundamentals tables on the ticker column
        "Portfolio summary": "SELECT ticker, shares, buy_price, buy_date, notes FROM portfolio ORDER BY buy_date DESC",
    }

    cols_preset = st.columns(4) #creates 4 equal columns to lay the preset buttons across
    selected_preset = None #starts as None; gets set to a sql string when a button is clicked
    preset_keys = list(presets.keys()) #converts the dictionary keys to a list so you can loop through them with an index
    for i, key in enumerate(preset_keys): #enumerate gives you both the index i and the value key as you loop
        with cols_preset[i % 4]: #i % 4 is modulo; cycles through 0,1,2,3,0,1,2,3 to distribute buttons evenly across 4 columns
            if st.button(key, use_container_width=True, key=f"preset_{i}"): #key=f"preset_{i}" gives each button a unique id
                selected_preset = presets[key] #stores the sql string for whichever button was clicked

    # SQL editor
    default_query = selected_preset if selected_preset else "SELECT ticker, price, pe_ratio, eps, profit_margin FROM stock_fundamentals ORDER BY snapshot_date DESC LIMIT 20" #if a preset was clicked use that, otherwise show the default query
    query = st.text_area("SQL Query", value=default_query, height=120) #text editor pre-filled with the selected query

    if st.button("▶ Run Query", type="primary"): #type="primary" makes the button blue
        result_df, error = run_sql(query) #unpacks the two return values from run_sql
        if error:
            st.error(f"SQL Error: {error}") #shows error in red if query failed
        elif result_df is not None and not result_df.empty: #checks both that something came back and that it has actual rows
            st.success(f"{len(result_df)} row(s) returned") #green message with row count
            st.dataframe(result_df, use_container_width=True) #renders the query result as an interactive sortable table

            # Auto chart if numeric columns present
            numeric_cols = result_df.select_dtypes(include="number").columns.tolist() #detects which columns have numeric data
            if len(numeric_cols) >= 1 and "ticker" in result_df.columns: #only shows chart option if theres something to chart
                chart_col = st.selectbox("Chart this column", numeric_cols) #dropdown to pick which metric to visualize
                fig_sql = px.bar(result_df, x="ticker", y=chart_col,
                                 color="ticker", color_discrete_sequence=px.colors.qualitative.Set2,
                                 title=f"{chart_col} by Ticker")
                fig_sql.update_layout(template="plotly_dark", paper_bgcolor="#0e1117",
                                       plot_bgcolor="#0e1117", height=350, showlegend=False,
                                       margin=dict(l=0,r=0,t=40,b=0))
                st.plotly_chart(fig_sql, use_container_width=True)

            # Download
            csv = result_df.to_csv(index=False) #converts dataframe to a csv string without row numbers
            st.download_button("⬇ Download CSV", csv, "query_results.csv", "text/csv") #triggers a file download in the browser when clicked
        else:
            st.info("Query returned no results. Try viewing some stocks first so data is saved.")

    # Watchlist manager
    st.markdown("---")
    st.markdown("<div class='section-header'>Watchlist</div>", unsafe_allow_html=True)
    wl = get_watchlist() #fetches current watchlist from the database
    if not wl.empty: #only renders the table if there are actually stocks in the watchlist
        st.dataframe(wl, use_container_width=True) #displays the watchlist as an interactive table
        remove_ticker = st.text_input("Remove ticker from watchlist") #text box to type the ticker you want to remove
        if st.button("🗑 Remove") and remove_ticker: #the "and remove_ticker" makes sure the box isnt empty before running
            conn = sqlite3.connect(DB_PATH)
            conn.execute("DELETE FROM watchlist WHERE ticker=?", (remove_ticker.upper(),)) #deletes exactly that ticker from the watchlist
            conn.commit()
            conn.close()
            st.rerun() #reruns the entire app so the updated watchlist renders immediately without refreshing the page
    else:
        st.info("Your watchlist is empty. Add stocks from the sidebar.")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — PORTFOLIO
# ══════════════════════════════════════════════════════════════════════════════
with tab5:
    st.markdown("### 💼 Portfolio Tracker")

    col_form, col_port = st.columns([1, 2]) #trade entry form takes one third, holdings table takes two thirds

    with col_form: #everything indented here goes in the left column
        st.markdown("<div class='section-header'>Log a Trade</div>", unsafe_allow_html=True)
        p_ticker = st.text_input("Ticker", key="p_ticker").upper() #forces uppercase so "aapl" and "AAPL" are treated the same
        p_shares = st.number_input("Shares", min_value=0.0, step=1.0, key="p_shares") #step=1.0 means the arrows increment by 1 share at a time
        p_price = st.number_input("Buy Price ($)", min_value=0.0, step=0.01, key="p_price") #step=0.01 means the arrows move by one cent
        p_date = st.date_input("Buy Date", key="p_date") #renders a calendar date picker
        p_notes = st.text_input("Notes", key="p_notes")
        if st.button("➕ Add Trade", type="primary", use_container_width=True):
            if p_ticker and p_shares > 0 and p_price > 0: #validates all required fields have values before saving
                add_portfolio_trade(p_ticker, p_shares, p_price, str(p_date), p_notes) #str(p_date) converts date object to string like "2026-09-04" for storage
                st.success(f"Added {p_shares} shares of {p_ticker} @ ${p_price:.2f}")
                st.rerun() #refreshes so the new trade appears in the table immediately
            else:
                st.warning("Fill in ticker, shares, and price.")

    with col_port: #everything indented here goes in the right column
        st.markdown("<div class='section-header'>Your Holdings</div>", unsafe_allow_html=True)
        port_df = get_portfolio() #fetches all logged trades from the database
        if not port_df.empty: #only renders the table if there are trades logged
            enriched = [] #empty list that gets filled with one dictionary per trade
            for _, row in port_df.iterrows(): #iterrows loops through each trade row; _ discards the index since you dont need it
                try:
                    _, inf = get_stock_data(row["ticker"], "5d") #fetches current price for each position
                    cp = inf.get("currentPrice") or inf.get("regularMarketPrice") if inf else row["buy_price"]
                    gain = (cp - row["buy_price"]) / row["buy_price"] * 100 #standard gain % formula
                    total_gain = (cp - row["buy_price"]) * row["shares"] #per share gain multiplied by number of shares = total dollar P&L
                    enriched.append({ #builds a formatted dictionary for this trade and adds it to the list
                        "Ticker": row["ticker"],
                        "Shares": row["shares"],
                        "Buy Price": f"${row['buy_price']:.2f}", #formats to 2 decimal places with dollar sign
                        "Current": f"${cp:.2f}" if cp else "N/A", #live price fetched from yahoo finance
                        "Gain %": f"{gain:+.2f}%" if cp else "N/A", #the + forces sign to always show (ex. +12.34% not just 12.34%)
                        "Total P&L": f"${total_gain:+.2f}" if cp else "N/A", #total dollar profit or loss on the position
                        "Buy Date": row["buy_date"], #pulled directly from the database
                        "Notes": row["notes"], #any notes you attached when logging the trade
                    })
                except:
                    enriched.append({"Ticker": row["ticker"], "Shares": row["shares"],
                                     "Buy Price": f"${row['buy_price']:.2f}"}) #if a stock fails to fetch (delisted, bad data) adds a partial row so rest of portfolio still shows

            edf = pd.DataFrame(enriched) #converts the list of dictionaries into a dataframe for the live portfolio table
            st.dataframe(edf, use_container_width=True)

            # Delete trade
            del_id = st.number_input("Delete trade by ID", min_value=1, step=1, key="del_id") #the id number shown in the table
            if st.button("🗑 Delete Trade"): #only runs when the button is clicked
                conn = sqlite3.connect(DB_PATH) #opens a connection to run the delete
                conn.execute("DELETE FROM portfolio WHERE id=?", (del_id,)) #deletes exactly that trade by its auto-assigned id
                conn.commit() #saves the deletion to disk
                conn.close() #releases the database connection
                st.rerun() #refreshes the app so the deleted trade disappears from the table immediately
        else:
            st.info("No trades logged yet. Add your first position above.") #shown when portfolio table is empty

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("---")
st.caption("Data via Yahoo Finance · Not financial advice · For educational use only") #st.caption renders small grey text; sits outside all tab blocks so it shows on every tab