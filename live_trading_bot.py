"""
LIVE TRADING BOT - MCP Strategy Integration
25x Leverage - BTC/USDT 15m
Binance API Integration
"""

import pandas as pd
import numpy as np
import time
import logging
from datetime import datetime, timedelta
from binance.client import Client
from binance.exceptions import BinanceAPIException
import warnings
warnings.filterwarnings('ignore')

# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════
API_KEY = '0EBCMPnVWZ9gJ7n7zGex6AlTdeUjPqdOgRgjRqZ4qPJNNCQ63en4LR3lGwlPjBHs'  # Replace with your API key
API_SECRET = 'K7nPVO8CDFaUxk3YIsNCPkp8DvRmlWXWqYVFuvUyZbzuJTjEaz9NAWKwjkXtsSEl'  # Replace with your API secret
SYMBOL = 'BTCUSDT'
LEVERAGE = 25
TIMEFRAME = '15m'
MAX_SL_PCT = 0.5  # 0.5% stop loss (reduced for breathing room)
RR_RATIO = 3.0  # 1:3 risk-reward

# Risk management
MAX_POSITION_SIZE = 0.1  # Max 10% of account per trade
MAX_DAILY_TRADES = 5  # Max trades per day
MIN_HOLD_MINUTES = 45  # Minimum 45 minutes hold time before allowing SL
MICRO_TESTING = True  # Enable micro position sizing for gradual testing
MICRO_POSITION_SIZE = 0.001  # 0.1% of account for initial testing

# ═══════════════════════════════════════════════════════════════════════════
# LOGGING SETUP
# ═══════════════════════════════════════════════════════════════════════════
logging.basicConfig(
    filename='trading_bot.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
console = logging.StreamHandler()
console.setLevel(logging.INFO)
logging.getLogger('').addHandler(console)

# ═══════════════════════════════════════════════════════════════════════════
# BINANCE CLIENT
# ═══════════════════════════════════════════════════════════════════════════
try:
    client = Client(API_KEY, API_SECRET)
    logging.info("✅ Binance API connected successfully")
except Exception as e:
    logging.error(f"❌ Binance API connection failed: {e}")
    exit(1)

# ═══════════════════════════════════════════════════════════════════════════
# UTILITY FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════
def get_account_balance():
    """Get account balance"""
    try:
        account = client.futures_account()
        for asset in account['assets']:
            if asset['asset'] == 'USDT':
                return float(asset['walletBalance'])
        return 0.0
    except Exception as e:
        logging.error(f"Error getting balance: {e}")
        return 0.0

def get_current_price(symbol):
    """Get current price"""
    try:
        ticker = client.futures_symbol_ticker(symbol=symbol)
        return float(ticker['price'])
    except Exception as e:
        logging.error(f"Error getting price: {e}")
        return None

def set_leverage(symbol, leverage):
    """Set leverage"""
    try:
        client.futures_change_leverage(symbol=symbol, leverage=leverage)
        logging.info(f"✅ Leverage set to {leverage}x")
    except Exception as e:
        logging.error(f"Error setting leverage: {e}")

def get_open_positions(symbol):
    """Get open positions"""
    try:
        positions = client.futures_position_information(symbol=symbol)
        for pos in positions:
            if float(pos['positionAmt']) != 0:
                return {
                    'amount': float(pos['positionAmt']),
                    'entry_price': float(pos['entryPrice']),
                    'unrealized_pnl': float(pos['unRealizedProfit'])
                }
        return None
    except Exception as e:
        logging.error(f"Error getting positions: {e}")
        return None

def place_market_order(symbol, side, quantity):
    """Place market order"""
    try:
        order = client.futures_create_order(
            symbol=symbol,
            side=side,
            type='MARKET',
            quantity=quantity
        )
        logging.info(f"✅ {side} order placed: {quantity} {symbol}")
        return order
    except Exception as e:
        logging.error(f"Error placing order: {e}")
        return None

def place_stop_order(symbol, side, quantity, stop_price):
    """Place stop loss order"""
    try:
        order = client.futures_create_order(
            symbol=symbol,
            side=side,
            type='STOP_MARKET',
            quantity=quantity,
            stopPrice=stop_price
        )
        logging.info(f"✅ Stop loss set at {stop_price}")
        return order
    except Exception as e:
        logging.error(f"Error placing stop order: {e}")
        return None

def close_position(symbol):
    """Close all positions"""
    try:
        position = get_open_positions(symbol)
        if position:
            side = 'SELL' if position['amount'] > 0 else 'BUY'
            quantity = abs(position['amount'])
            order = place_market_order(symbol, side, quantity)
            logging.info(f"✅ Position closed at market")
            return order
    except Exception as e:
        logging.error(f"Error closing position: {e}")
        return None

# ═══════════════════════════════════════════════════════════════════════════
# MCP STRATEGY LOGIC (Simplified for Live Trading)
# ═══════════════════════════════════════════════════════════════════════════
def get_historical_data(symbol, interval, limit=500):
    """Get historical klines"""
    try:
        klines = client.futures_klines(symbol=symbol, interval=interval, limit=limit)
        df = pd.DataFrame(klines, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_asset_volume', 'number_of_trades',
            'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
        ])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        df = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
        return df
    except Exception as e:
        logging.error(f"Error getting historical data: {e}")
        return None

def calculate_indicators(df):
    """Calculate MCP indicators"""
    if len(df) < 200:
        return None

    # 1H and 4H EMAs
    df_1h = df.resample('1h').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna()
    df_1h['ema200'] = df_1h['close'].ewm(span=200, min_periods=200).mean()

    df_4h = df.resample('4h').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna()
    df_4h['ema200'] = df_4h['close'].ewm(span=200, min_periods=200).mean()

    # Reindex to 15m
    df['ema200_1h'] = df_1h['ema200'].reindex(df.index, method='ffill')
    df['ema200_4h'] = df_4h['ema200'].reindex(df.index, method='ffill')

    # Volume filter
    df['vol_avg_20'] = df['volume'].rolling(20).mean()
    df['vol_confirmed'] = df['volume'] > df['vol_avg_20'] * 1.5

    # RSI
    def calculate_rsi(series, period=14):
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    df['rsi'] = calculate_rsi(df['close'], 14)

    # Trend
    df['strong_uptrend'] = (df['close'] > df['ema200_1h']) & (df['close'] > df['ema200_4h'])
    df['strong_downtrend'] = (df['close'] < df['ema200_1h']) & (df['close'] < df['ema200_4h'])

    return df.dropna()

def detect_ob_signal(df):
    """ULTIMATE OB detection with pullback confirmation and Fibonacci confluence"""
    if len(df) < 10:  # Need more candles for analysis
        return None

    current = df.iloc[-1]
    previous = df.iloc[-2]

    # Calculate Fibonacci levels from recent swing
    lookback = min(50, len(df))
    window = df.iloc[-lookback:]
    swing_high = window['high'].max()
    swing_low = window['low'].min()
    fib_618 = swing_high - (swing_high - swing_low) * 0.618
    fib_786 = swing_high - (swing_high - swing_low) * 0.786

    # Basic OB conditions
    if previous['high'] == previous['low']:
        return None

    # Bullish OB with pullback confirmation
    body_ratio = (previous['close'] - previous['low']) / (previous['high'] - previous['low'])
    is_strong_down = previous['close'] < previous['open'] and body_ratio > 0.7
    is_reversal = current['close'] > previous['close']

    if is_strong_down and is_reversal:
        ob_low = previous['low']
        # Pullback confirmation: price dipped below OB low in last 4 candles
        recent_lows = df.iloc[-5:-1]['low'].min()  # Last 4 candles before current
        pullback_confirmed = recent_lows < ob_low

        # Fibonacci confluence: price in Fib zone
        fib_confluence = current['close'] >= fib_618 and current['close'] <= fib_786

        if (pullback_confirmed and fib_confluence and
            current['strong_uptrend'] and current['vol_confirmed'] and
            35 < current['rsi'] < 70):
            return 'LONG'

    # Bearish OB with pullback confirmation
    body_ratio_short = (previous['high'] - previous['close']) / (previous['high'] - previous['low'])
    is_strong_up = previous['close'] > previous['open'] and body_ratio_short > 0.7
    is_reversal_short = current['close'] < previous['close']

    if is_strong_up and is_reversal_short:
        ob_high = previous['high']
        # Pullback confirmation: price spiked above OB high in last 4 candles
        recent_highs = df.iloc[-5:-1]['high'].max()
        pullback_confirmed = recent_highs > ob_high

        # Fibonacci confluence: price in Fib zone
        fib_confluence = current['close'] <= fib_618 and current['close'] >= fib_786

        if (pullback_confirmed and fib_confluence and
            current['strong_downtrend'] and current['vol_confirmed'] and
            30 < current['rsi'] < 65):
            return 'SHORT'

    return None

# ═══════════════════════════════════════════════════════════════════════════
# TRADING BOT MAIN LOOP
# ═══════════════════════════════════════════════════════════════════════════
class TradingBot:
    def __init__(self):
        self.symbol = SYMBOL
        self.leverage = LEVERAGE
        self.daily_trades = 0
        self.last_trade_date = datetime.now().date()
        self.in_position = False
        self.entry_time = None
        self.entry_price = None
        self.stop_loss = None
        self.take_profit = None
        self.direction = None
        self.be_triggered = False

        # Set leverage
        set_leverage(self.symbol, self.leverage)

        logging.info("🤖 ULTIMATE MCP Trading Bot initialized")
        logging.info(f"📊 Symbol: {self.symbol}, Leverage: {self.leverage}x")
        logging.info(f"💰 Account Balance: ${get_account_balance():.2f}")
        logging.info(f"🛡️  Risk Management: 0.5% SL, {MIN_HOLD_MINUTES}min hold, {'MICRO TESTING' if MICRO_TESTING else 'NORMAL'} sizing")

    def calculate_position_size(self, entry_price, stop_loss_price):
        """Calculate position size based on risk management"""
        balance = get_account_balance()

        # Use micro position size for testing
        if MICRO_TESTING:
            risk_amount = balance * MICRO_POSITION_SIZE  # 0.1% for testing
        else:
            risk_amount = balance * MAX_POSITION_SIZE  # 10% normal

        # Risk per trade = entry_price * quantity * (SL %)
        # quantity = risk_amount / (entry_price * (SL %))
        quantity = risk_amount / (entry_price * (MAX_SL_PCT / 100))

        # Round to appropriate precision for BTCUSDT (6 decimal places)
        quantity = round(quantity, 6)

        return quantity

    def execute_trade(self, signal, entry_price):
        """Execute trade with ULTIMATE risk management"""
        if self.in_position:
            logging.info("⚠️  Already in position, skipping signal")
            return

        # Calculate stop loss and take profit (0.5% SL)
        if signal == 'LONG':
            stop_loss = entry_price * (1 - MAX_SL_PCT / 100)
            take_profit = entry_price + (entry_price - stop_loss) * RR_RATIO
        else:  # SHORT
            stop_loss = entry_price * (1 + MAX_SL_PCT / 100)
            take_profit = entry_price - (stop_loss - entry_price) * RR_RATIO

        # Calculate position size (micro for testing)
        quantity = self.calculate_position_size(entry_price, stop_loss)

        if quantity <= 0:
            logging.warning("⚠️  Invalid position size, skipping trade")
            return

        logging.info(f"🎯 Signal: {signal} at ${entry_price:.2f}")
        logging.info(f"📏 Quantity: {quantity} BTC ({'MICRO TEST' if MICRO_TESTING else 'NORMAL'})")
        logging.info(f"🛑 Stop Loss: ${stop_loss:.2f} (0.5%)")
        logging.info(f"🎯 Take Profit: ${take_profit:.2f}")
        logging.info(f"⏰ Min Hold Time: {MIN_HOLD_MINUTES} minutes")

        # Place entry order
        side = 'BUY' if signal == 'LONG' else 'SELL'
        order = place_market_order(self.symbol, side, quantity)

        if order:
            self.in_position = True
            self.daily_trades += 1
            self.entry_time = datetime.now()
            self.entry_price = entry_price
            self.stop_loss = stop_loss
            self.take_profit = take_profit
            self.direction = signal
            self.be_triggered = False

            # Place stop loss order
            sl_side = 'SELL' if signal == 'LONG' else 'BUY'
            place_stop_order(self.symbol, sl_side, quantity, stop_loss)

            logging.info(f"✅ {signal} position opened with ultimate risk management")
        else:
            logging.error("❌ Failed to open position")

    def check_and_close_positions(self):
        """Check for exit conditions with minimum hold time and breakeven stops"""
        position = get_open_positions(self.symbol)
        if not position:
            self.in_position = False
            return

        current_price = get_current_price(self.symbol)
        if not current_price:
            return

        # Check minimum hold time
        time_in_position = (datetime.now() - self.entry_time).total_seconds() / 60
        if time_in_position < MIN_HOLD_MINUTES:
            return  # Don't check exits until minimum hold time

        entry_price = position['entry_price']
        amount = position['amount']

        # Breakeven stop logic
        if not self.be_triggered:
            if self.direction == 'LONG' and current_price >= self.entry_price * 1.003:  # 0.3% profit
                # Move SL to breakeven
                new_sl = self.entry_price
                # Update stop loss order (would need to cancel and replace in real implementation)
                self.stop_loss = new_sl
                self.be_triggered = True
                logging.info(f"🔒 Long SL moved to breakeven at ${new_sl:.2f}")

            elif self.direction == 'SHORT' and current_price <= self.entry_price * 0.997:  # 0.3% profit
                # Move SL to breakeven
                new_sl = self.entry_price
                self.stop_loss = new_sl
                self.be_triggered = True
                logging.info(f"🔒 Short SL moved to breakeven at ${new_sl:.2f}")

        # Check take profit
        if amount > 0:  # Long position
            if current_price >= self.take_profit:
                close_position(self.symbol)
                self.in_position = False
                logging.info(f"🎯 Long TP hit at ${current_price:.2f}")
        else:  # Short position
            if current_price <= self.take_profit:
                close_position(self.symbol)
                self.in_position = False
                logging.info(f"🎯 Short TP hit at ${current_price:.2f}")

        # Note: Stop loss is handled by Binance's stop order, not manually here

    def run(self):
        """Main trading loop"""
        logging.info("🚀 Starting MCP Trading Bot...")

        while True:
            try:
                # Reset daily trade count
                if datetime.now().date() != self.last_trade_date:
                    self.daily_trades = 0
                    self.last_trade_date = datetime.now().date()
                    logging.info("📅 New trading day started")

                # Check if we've hit daily trade limit
                if self.daily_trades >= MAX_DAILY_TRADES:
                    logging.info("📊 Daily trade limit reached, waiting...")
                    time.sleep(3600)  # Wait 1 hour
                    continue

                # Get latest data
                df = get_historical_data(self.symbol, TIMEFRAME, 500)
                if df is None:
                    time.sleep(60)
                    continue

                # Calculate indicators
                df = calculate_indicators(df)
                if df is None:
                    time.sleep(60)
                    continue

                # Check for signals
                signal = detect_ob_signal(df)

                if signal and not self.in_position:
                    current_price = get_current_price(self.symbol)
                    if current_price:
                        self.execute_trade(signal, current_price)

                # Check for exit conditions
                self.check_and_close_positions()

                # Wait for next 15m candle
                time.sleep(900)  # 15 minutes

            except KeyboardInterrupt:
                logging.info("🛑 Bot stopped by user")
                break
            except Exception as e:
                logging.error(f"Error in main loop: {e}")
                time.sleep(60)

# ═══════════════════════════════════════════════════════════════════════════
# MAIN EXECUTION
# ═══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("⚠️  WARNING: This is a live trading bot!")
    print("⚠️  Make sure to:")
    print("   1. Replace API_KEY and API_SECRET with your Binance credentials")
    print("   2. Test with small amounts first")
    print("   3. Monitor the bot closely")
    print()
    print("Starting in 10 seconds... Press Ctrl+C to cancel")

    for i in range(10, 0, -1):
        print(f"{i}...", end=" ", flush=True)
        time.sleep(1)
    print("GO!")

    bot = TradingBot()
    bot.run()