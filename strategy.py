# Strategy.py

import datetime
import time
import pandas as pd
import logging

class BreakoutStrategy:
    def __init__(self, smartApi, symbol, exchange, token):
        self.smartApi = smartApi
        self.symbol = symbol
        self.exchange = exchange
        self.token = token
        self.high = None
        self.stoploss = None
        self.position = self.is_etf_still_held()
        self.trail_anchor = None
        self.waiting_for_candle_update = False
        self.last_rsi_check_time = None
        self.cached_rsi_value = None
        logging.info("Strategy initialized.")
    def is_etf_still_held(self):
        try:
            holdings = self.smartApi.holding()
            for item in holdings.get("data", []):
                if item["tradingsymbol"] == self.symbol and item["quantity"] >= 1:
                    return True
            return False
        except Exception as e:
            print("Error checking holdings: ", e)
            return True
    def _fetch_candles(self, interval, from_dt, to_dt):
        try:
            candles = self.smartApi.getCandleData({
                "exchange": self.exchange,
                "symboltoken": self.token,
                "interval": interval,
                "fromdate": from_dt.strftime("%Y-%m-%d %H:%M"),
                "todate": to_dt.strftime("%Y-%m-%d %H:%M"),
                "tradingsymbol": self.symbol
            })
            return candles['data'] if 'data' in candles else None
        except Exception as e:
            print("Candle fetch failed:", e)
            return None

    def initialize_first_candle(self):
        now = datetime.datetime.now() - datetime.timedelta(minutes=1)
        aligned_minute = (now.minute // 30) * 30
        to_dt = now.replace(minute=aligned_minute, second=0, microsecond=0)
        from_dt = to_dt - datetime.timedelta(minutes=30)
        self.trail_anchor = from_dt

        candles = self._fetch_candles("THIRTY_MINUTE", from_dt, to_dt)
        if candles:
            self.high = float(candles[-1][2])
            self.stoploss = float(candles[-1][3])
            print(f"Initial high: {self.high}, stoploss: {self.stoploss}")
            return True
        else:
            print("Initial candle fetch returned no data.")
            return False

    def check_rsi(self, period=14):
        now = datetime.datetime.now()
        if (self.last_rsi_check_time) and (self.cached_rsi_value) and (now - self.last_rsi_check_time).total_seconds() < 120:
            return self.cached_rsi_value
        from_dt = now - datetime.timedelta(minutes=75)
        to_dt = now
        candles = self._fetch_candles("FIVE_MINUTE", from_dt, to_dt)
        if candles is None:
            print("RSI candle fetch failed (Something went wrong)")
            return None
        df = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["close"] = pd.to_numeric(df["close"])
        delta = df["close"].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        if (not rsi.empty):
            self.cached_rsi_value = rsi.iloc[-1]
            self.last_rsi_check_time = now
        return rsi.iloc[-1] if not rsi.empty else None

    def is_high_breached(self, ltp):
        return (not self.position) and (round(ltp, 2) > round(self.high, 2))

    def confirm_breakout(self, ltp):
        if ltp >= self.high:
            rsi = self.check_rsi()
            if rsi is None:
                return None  # very important: propagate None on candle failure
            if rsi >= 60:
                print(f"Breakout confirmed with RSI {rsi}")
                return True
        return False

    def should_trail_stoploss(self):
        if (not self.trail_anchor) or (not self.position) or (self.waiting_for_candle_update):
            return False
        try:
            now = datetime.datetime.now()
            if isinstance(self.trail_anchor, str):
                self.trail_anchor = datetime.datetime.strptime(self.trail_anchor, "%Y-%m-%d %H:%M:%S")
                elapsed = now - self.trail_anchor
                return elapsed.total_seconds() % (60 * 15) < 5
        except Exception as e:
                print(f"Error checking trail_stoploss: {e}")
                return False
    def update_trailing_stoploss(self , ltp):
        try:
            print("Trying to update stoploss with ltp: " , ltp , "...")
            if ltp is None:
                print("LTP unavailable for trailing stoploss.")
                return None
            if ltp > self.high:
                print("ltp is greater..")
                delta = ltp - self.high
                new_stoploss = self.stoploss + 0.5 * delta
                print(f"delta: {delta} , new_stoploss {new_stoploss}")
                if new_stoploss > self.stoploss:
                    print(f"Trailing SL update: {self.stoploss} → {new_stoploss}")
                    self.stoploss = new_stoploss
            else:
                print(f"{ltp} < {self.high}")
            return 101
        except Exception as e:
            print("Error updating trailing stoploss:", e)
            return None


    def update_high_stoploss_after_sell(self):
        now = datetime.datetime.now() - datetime.timedelta(minutes=1)
        aligned_minute = (now.minute // 30) * 30
        to_dt = now.replace(minute=aligned_minute, second=0, microsecond=0)
        from_dt = to_dt - datetime.timedelta(minutes=30)
        candles = self._fetch_candles("THIRTY_MINUTE", from_dt, to_dt)
        if candles is None:
            print("No candles found while updating high, stoploss after sell")
            return None
        if candles:
            self.high = float(candles[-1][2])
            self.stoploss = float(candles[-1][3])
            self.trail_anchor = from_dt
            self.waiting_for_candle_update = False
            print(f"Updated high to {self.high}, stoploss to {self.stoploss}")
        return 101

    def stoploss_hit(self, ltp):
        return self.position and ltp <= self.stoploss

    def force_exit_required(self):
        now = datetime.datetime.now().time()
        return now >= datetime.time(15, 10)
