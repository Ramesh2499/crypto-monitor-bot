"""
ENHANCED CRYPTO MONITOR BOT v2.0
24-Hour Trading with Dynamic Kill Switch Calculation
Monitors 10 coins + Daily Kill Switch Price
"""

import requests
import time
import json
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv()

# Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "YOUR_CHAT_ID_HERE")

# Your 10 coins with entry prices
COINS = {
    "BCH": {"name": "Bitcoin Cash", "entry_price": 321.55, "allocation": 100},
    "NEAR": {"name": "NEAR Protocol", "entry_price": 4.43, "allocation": 100},
    "XRP": {"name": "XRP", "entry_price": 1.55, "allocation": 100},
    "ZEC": {"name": "Zcash", "entry_price": 1553.66, "allocation": 100},
    "UNI": {"name": "Uniswap", "entry_price": 9.23, "allocation": 100},
    "DOGE": {"name": "Dogecoin", "entry_price": 0.0989, "allocation": 100},
    "HBAR": {"name": "Hedera", "entry_price": 0.0952, "allocation": 100},
    "XLM": {"name": "Stellar", "entry_price": 0.2127, "allocation": 100},
    "HYPE": {"name": "Hyperliquid", "entry_price": 95.04, "allocation": 100},
    "ADA": {"name": "Cardano", "entry_price": 0.2478, "allocation": 100},
}

# Alert thresholds
PROFIT_TARGET = 1.05  # +5%
STOP_LOSS = 0.92     # -8%
FEAR_GREED_WARNING = 50

# Logged alerts
alerted_coins = set()
btc_kill_switch_sent = False
btc_warning_sent = False
fear_greed_warning_sent = False

def send_telegram_message(text):
    """Send message to Telegram"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML"
        }
        response = requests.post(url, data=data, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"Telegram error: {e}")
        return False

def get_bitcoin_price():
    """Get current Bitcoin price"""
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
        response = requests.get(url, timeout=10)
        data = response.json()
        return data["bitcoin"]["usd"]
    except Exception as e:
        print(f"Error fetching Bitcoin price: {e}")
        return None

def get_bitcoin_market_data():
    """Get Bitcoin OHLCV data for last 7 days"""
    try:
        # Get last 8 days of data (to ensure we have 7 full days)
        url = "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart?vs_currency=usd&days=7"
        response = requests.get(url, timeout=10)
        data = response.json()
        prices = data["prices"]

        # Extract low from prices (they come as [timestamp, price])
        low_7d = min([price[1] for price in prices])
        high_7d = max([price[1] for price in prices])

        return low_7d, high_7d
    except Exception as e:
        print(f"Error fetching Bitcoin market data: {e}")
        return None, None

def calculate_kill_switch(btc_price):
    """
    Calculate dynamic kill switch using hybrid method:
    Kill Switch = LOWER of:
    1. Current BTC Price × 0.97 (-3%)
    2. 7-Day Low
    """
    if not btc_price:
        return None, None, None

    # Method 1: -3% from current price
    kill_switch_percent = btc_price * 0.97

    # Method 2: 7-day low
    low_7d, high_7d = get_bitcoin_market_data()

    if low_7d is None:
        kill_switch = kill_switch_percent
        method_used = "Method 1 (-3%)"
    else:
        # Use the LOWER of the two
        if kill_switch_percent < low_7d:
            kill_switch = kill_switch_percent
            method_used = "Method 1 (-3%)"
        else:
            kill_switch = low_7d
            method_used = "Method 2 (7-day low)"

    return kill_switch, method_used, {"7d_low": low_7d, "7d_high": high_7d, "percent_method": kill_switch_percent}

def get_coin_price(ticker):
    """Get current price from CoinGecko"""
    try:
        coin_map = {
            "BCH": "bitcoin-cash",
            "NEAR": "near",
            "XRP": "ripple",
            "ZEC": "zcash",
            "UNI": "uniswap",
            "DOGE": "dogecoin",
            "HBAR": "hedera",
            "XLM": "stellar",
            "HYPE": "hyperliquid",
            "ADA": "cardano"
        }

        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_map[ticker]}&vs_currencies=usd"
        response = requests.get(url, timeout=10)
        data = response.json()
        price = data[coin_map[ticker]]["usd"]
        return price
    except Exception as e:
        print(f"Error fetching {ticker}: {e}")
        return None

def get_fear_greed_index():
    """Get Fear & Greed Index"""
    try:
        url = "https://api.alternative.me/fng/?limit=1&format=json"
        response = requests.get(url, timeout=10)
        data = response.json()
        return int(data["data"][0]["value"]), data["data"][0]["value_classification"]
    except Exception as e:
        print(f"Error fetching Fear & Greed: {e}")
        return None, None

def calculate_pnl(entry_price, current_price, allocation):
    """Calculate P&L"""
    units = allocation / entry_price
    current_value = units * current_price
    pnl = current_value - allocation
    pnl_percent = (pnl / allocation) * 100
    return pnl, pnl_percent, current_value

def check_coins(kill_switch_price, kill_switch_method):
    """Check all coins for alerts"""
    global alerted_coins, btc_kill_switch_sent, btc_warning_sent, fear_greed_warning_sent

    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Checking coins...")
    print(f"Kill Switch Level: ${kill_switch_price:,.2f} ({kill_switch_method})")

    # Check Bitcoin
    btc_price = get_bitcoin_price()
    if btc_price:
        print(f"Bitcoin: ${btc_price:,.2f}")

        # Check kill switch
        if btc_price < kill_switch_price and not btc_kill_switch_sent:
            msg = f"🚨 <b>KILL SWITCH ACTIVATED!</b>\n\n"
            msg += f"Bitcoin dropped to ${btc_price:,.2f}\n"
            msg += f"Kill Switch Level: ${kill_switch_price:,.2f}\n"
            msg += f"Method: {kill_switch_method}\n"
            msg += f"<b>ACTION: EXIT ALL POSITIONS IMMEDIATELY</b>\n"
            msg += f"⏰ {datetime.now().strftime('%H:%M UTC')}"
            send_telegram_message(msg)
            btc_kill_switch_sent = True
            print("🚨 KILL SWITCH TRIGGERED")

        # Warning level (10% above kill switch)
        warning_level = kill_switch_price * 1.10
        if btc_price < warning_level and not btc_warning_sent:
            msg = f"⚠️ <b>Bitcoin Warning Zone</b>\n\n"
            msg += f"BTC at ${btc_price:,.2f}\n"
            msg += f"Kill Switch: ${kill_switch_price:,.2f}\n"
            msg += f"Difference: ${kill_switch_price - btc_price:,.2f}\n"
            msg += f"Be ready to exit if it drops further\n"
            msg += f"⏰ {datetime.now().strftime('%H:%M UTC')}"
            send_telegram_message(msg)
            btc_warning_sent = True
            print("⚠️ Bitcoin warning sent")

    # Check Fear & Greed
    fg_value, fg_class = get_fear_greed_index()
    if fg_value:
        print(f"Fear & Greed: {fg_value} ({fg_class})")

        if fg_value < FEAR_GREED_WARNING and not fear_greed_warning_sent:
            msg = f"📊 <b>Market Sentiment Shift!</b>\n\n"
            msg += f"Fear & Greed dropped to {fg_value}\n"
            msg += f"Classification: {fg_class}\n"
            msg += f"Market regime may be changing\n"
            msg += f"⏰ {datetime.now().strftime('%H:%M UTC')}"
            send_telegram_message(msg)
            fear_greed_warning_sent = True

    # Check each coin
    for ticker, coin_data in COINS.items():
        current_price = get_coin_price(ticker)

        if current_price is None:
            continue

        entry_price = coin_data["entry_price"]
        allocation = coin_data["allocation"]
        coin_name = coin_data["name"]

        pnl, pnl_percent, current_value = calculate_pnl(entry_price, current_price, allocation)

        print(f"{ticker}: ${current_price:.6f} | P&L: {pnl_percent:+.2f}%")

        # Check for profit target (+5%)
        if current_price >= entry_price * PROFIT_TARGET and f"{ticker}_profit" not in alerted_coins:
            msg = f"🟢 <b>PROFIT TARGET HIT!</b>\n\n"
            msg += f"<b>{coin_name} ({ticker})</b>\n"
            msg += f"Entry: ${entry_price:.6f}\n"
            msg += f"Current: ${current_price:.6f}\n"
            msg += f"P&L: ${pnl:+.2f} ({pnl_percent:+.2f}%)\n"
            msg += f"<b>ACTION: CLOSE THIS POSITION</b>\n"
            msg += f"⏰ {datetime.now().strftime('%H:%M UTC')}"
            send_telegram_message(msg)
            alerted_coins.add(f"{ticker}_profit")
            print(f"✅ Profit alert sent for {ticker}")

        # Check for stop loss (-8%)
        elif current_price <= entry_price * STOP_LOSS and f"{ticker}_loss" not in alerted_coins:
            msg = f"🔴 <b>STOP LOSS HIT!</b>\n\n"
            msg += f"<b>{coin_name} ({ticker})</b>\n"
            msg += f"Entry: ${entry_price:.6f}\n"
            msg += f"Current: ${current_price:.6f}\n"
            msg += f"P&L: ${pnl:+.2f} ({pnl_percent:+.2f}%)\n"
            msg += f"<b>ACTION: CUT THIS POSITION</b>\n"
            msg += f"⏰ {datetime.now().strftime('%H:%M UTC')}"
            send_telegram_message(msg)
            alerted_coins.add(f"{ticker}_loss")
            print(f"🛑 Stop loss alert sent for {ticker}")

def main():
    """Main bot loop"""
    print("=" * 60)
    print("ENHANCED CRYPTO MONITOR BOT v2.0 STARTED")
    print("=" * 60)
    print(f"Bot Token: {TELEGRAM_BOT_TOKEN[:10]}...")
    print(f"Chat ID: {TELEGRAM_CHAT_ID}")
    print(f"Monitoring {len(COINS)} coins")
    print(f"Check interval: Every 30 minutes")
    print(f"Dynamic kill switch: Calculated daily")
    print("=" * 60)

    # Calculate initial kill switch
    btc_price = get_bitcoin_price()
    kill_switch, method, details = calculate_kill_switch(btc_price)

    # Send startup message
    startup_msg = f"🤖 <b>Bot Started (v2.0 Enhanced)!</b>\n\n"
    startup_msg += f"Monitoring 10 coins for 24 hours\n"
    startup_msg += f"✅ Profit target: +5%\n"
    startup_msg += f"❌ Stop loss: -8%\n"
    startup_msg += f"🚨 Kill Switch: ${kill_switch:,.2f}\n"
    startup_msg += f"📊 Method: {method}\n"
    startup_msg += f"Bitcoin Price: ${btc_price:,.2f}\n"
    startup_msg += f"\nStarted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}"
    send_telegram_message(startup_msg)

    # Main loop - check every 30 minutes
    check_count = 0
    while True:
        try:
            # Recalculate kill switch each check (adjusts throughout the day)
            btc_price = get_bitcoin_price()
            kill_switch, method, details = calculate_kill_switch(btc_price)

            check_coins(kill_switch, method)
            check_count += 1
            print(f"Check #{check_count} complete. Next check in 30 minutes...")
            print(f"Kill Switch: ${kill_switch:,.2f} ({method})")
            time.sleep(1800)  # 30 minutes
        except KeyboardInterrupt:
            print("\nBot stopped by user")
            break
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()
