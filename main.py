from SmartApi import SmartConnect
from SmartApi.smartWebSocketV2 import SmartWebSocketV2
from strategy import BreakoutStrategy
import pyotp
import threading
import time
import datetime
import smartapi.test.exectuions.envr as envr
import pytz
import logging
import sys
api_key = envr.API_KEY
username = envr.USERNAME
pwd = envr.PWD
smartApi = SmartConnect(api_key)
logging.basicConfig(filename='app.log', level=logging.INFO, format='%(asctime)s - %(message)s')
def login():
    global authToken , feedToken , refreshToken
    try:
        token = envr.TOKEN
        totp = pyotp.TOTP(token).now()
    except Exception as e:
        print("Invalid Token: The provided token is not valid.")
        print(e)
        return False
    correlation_id = "abcde"
    data = smartApi.generateSession(username, pwd, totp)

    if data['status'] == False:
        print("Error in data: " , data)
        return False
    else:
        # login api call
        # logger.info(f"You Credentials: {data}")
        authToken = data['data']['jwtToken']
        refreshToken = data['data']['refreshToken']
        # fetch the feedtoken
        feedToken = smartApi.getfeedToken()
        # fetch User Profile
        res = smartApi.getProfile(refreshToken)
        smartApi.generateToken(refreshToken)
        res=res['data']['exchanges']
        print("Login successufu;")
    return True
def logout():
        try:
                logging.info("Initiating shutdown...")
                smartApi.terminateSession(username)
                logging.info("Cleanup complete. Exiting.")
                print("logout succeful")
        except Exception as e:
                logging.warning(f"Error during shutdown: {e}")
status = "OK"
strategies = {}
active_position = None # Holds ETF nam
sws = None
lock = threading.Lock()
high = {}
stoploss = {}
waiting_for_candle_update = {}
trail_anchor = {}
# Tokens
INDEX_ETF_PAIRS = {
    "NIFTY 50": "NIFTYBEES-EQ",
    "SILVERBESS-EQ": "SILVERBEES-EQ",
    "NIFTY MIDCAP 150": "MID150BEES-EQ"
}
TOKENS = {
    "NIFTY 50": "99926000",
    "NIFTY MIDCAP 150": "99926060",
    "NIFTYBEES-EQ": "10576",
    "MID150BEES-EQ":"8506",
    "SILVERBEES-EQ":"8080"
}
QUANTITIES = {
    "NIFTYBEES-EQ": 100,
    "MID150BEES-EQ": 100,
    "SILVERBEES-EQ": 250
}
EXCHANGE = "NSE"

def safe_ltp(etf_symbol):
    try:
        token = TOKENS[etf_symbol]
        data = smartApi.ltpData(exchange=EXCHANGE, tradingsymbol=etf_symbol, symboltoken=str(token))
        return float(data['data']['ltp']) if data and data.get('data') else None
    except Exception as e:
        logging.warning(f"LTP fetch failed for {etf_symbol}: {e}")
        return None

def shutdown():
    global sws
    try:
        logging.info("Initiating shutdown...")
        sws.close_connection()
        smartApi.terminateSession(username)
        logging.info("Shutdown complete.")
        sys.exit()
        return
    except Exception as e:
        logging.warning(f"Shutdown error: {e}")
        sys.exit()
        return
    return

def wait_until_946():
    global status
    now = datetime.datetime.now(pytz.timezone('Asia/Kolkata')).time()
    while True:
        now = datetime.datetime.now(pytz.timezone('Asia/Kolkata')).time()
        if now >= datetime.time(15, 10):
            print("Too late to start.")
            status = "OVER"
            return
        if now < datetime.time(9, 46):
            time.sleep(30)
        else:
            return
def is_market_open():
        try:
            ltp = smartApi.ltpData(exchange="NSE", tradingsymbol="NIFTYBEES-EQ", symboltoken="10576")
            return ltp.get("data") is not None
        except:
            return False
buy_order_id = None
sell_order_id = None
pending_buy = False
pending_sell = False
order_monitor_running = False
correlation_id = "abc123"
mode = 1  # Full mode (tick data)
exchangeType = 1  # NSE
EXCHANGE = "NSE"
def place_order(etf_symbol, order_type, price):
    try:
        global pending_buy , pending_sell , buy_order_id , sell_order_id
        order = smartApi.placeOrderFullResponse({
            "variety": "NORMAL",
            "tradingsymbol": etf_symbol,
            "symboltoken": str(TOKENS[etf_symbol]),
            "transactiontype": order_type,
            "exchange": EXCHANGE,
            "ordertype": "LIMIT",
            "producttype": "INTRADAY",
            "duration": "DAY",
            "price": round(price, 2),
            "quantity": QUANTITIES[etf_symbol]
        })
        oid = order['data']['orderid']
        if order_type == "BUY":
            buy_order_id = oid
            pending_buy = True
        else:
            sell_order_id = oid
            pending_sell = True
        print(f"{order_type} order placed at limit {price}. ID: {oid}")
        logging.info(f"{order_type} order placed at limit {price} for {etf_symbol}. ID: {oid}")
        return
    except Exception as e:
        logging.warning(f"{order_type} order failed for {etf_symbol}: {e}")
def monitor_order(index_symbol , etf_symbol , order_id, is_buy):
        global pending_buy, pending_sell, order_monitor_running
        global active_position
        global waiting_for_candle_update
        if order_monitor_running:
            print("order running already")
            shutdown()
            return
        order_monitor_running = True
        start = time.time()
        while time.time() - start < 300:
            try:
                orders = smartApi.orderBook()
                for order in orders.get('data', []):
                    if order['orderid'] == order_id and order['status'] == 'complete':
                        if is_buy:
                            active_position = etf_symbol
                            pending_buy = False
                            waiting_for_candle_update[index_symbol] = False
                        else:
                            active_position = None
                            pending_sell = False
                            waiting_for_candle_update[index_symbol] = False
                        print(f"{'Buy' if is_buy else 'Sell'} order executed , position: {active_position}")
                        order_monitor_running = False
                        return
            except Exception as e:
                print(f"Order monitoring failed: {e}")
                shutdown()
                sys.exit()
                return
            time.sleep(10)
        smartApi.cancelOrder(orderid=order_id, variety="NORMAL")
        pending_buy = pending_sell = False
        order_monitor_running = False
        print(f"Order of {etf_symbol} not filled in 5 minutes. Cancelled.")
        return
def on_data(wsapp, message):
    global active_position
    global pending_buy, pending_sell
    global strategies
    global high , stoploss , trail_anchor , waiting_for_candle_update
    global buy_order_id , sell_order_id
    global status
    try:
            with lock:
                token = str(message['token'])
                ltp = message['last_traded_price'] / 100
                for index_symbol, etf_symbol in INDEX_ETF_PAIRS.items():
                    if TOKENS[index_symbol] != token:
                        continue
                    strat = strategies[index_symbol]
                if strat.force_exit_required():
                    if active_position:
                        etf_price = safe_ltp(active_position)
                        idx = [k for k in INDEX_ETF_PAIRS if INDEX_ETF_PAIRS[k]==active_position][0]
                        place_order(active_position, "SELL", etf_price * 0.99)
                        threading.Thread(target=monitor_order, args=(idx , active_position , sell_order_id, False)).start()
                        active_position = None
                    logging.info(f"EOD exit triggered.")
                    shutdown()
                    sys.exit()
                    return

                if active_position==etf_symbol and strat.should_trail_stoploss():
                    print("Should trail stoploss")
                    logging.info("Should trail Stoploss....")
                    if strat.update_trailing_stoploss(ltp) is None:
                        print("Could Not update stoploss..")
                        status = "None"
                        shutdown()
                        return
                    stoploss[index_symbol] = strat.stoploss
                    return

                if not active_position:
                    if strat.is_high_breached(ltp) and (not pending_buy) and (not strat.waiting_for_candle_update):
                        confirm_ltp = safe_ltp(etf_symbol)
                        breakout_confirm = strat.confirm_breakout(confirm_ltp)
                        if breakout_confirm is None:
                            print("Breakout Confrim not working")
                            status = "None"
                            shutdown()
                            return
                        if(confirm_ltp and breakout_confirm):
                            place_order(etf_symbol, "BUY", confirm_ltp * 1.01)
                            threading.Thread(target=monitor_order, args=(index_symbol , etf_symbol , buy_order_id, True)).start()
                            active_position = etf_symbol
                            return
                        return

                elif active_position == etf_symbol and strat.stoploss_hit(ltp):
                    sell_ltp = safe_ltp(etf_symbol)
                    print("Stop loss is hit. Placing Sell order..")
                    place_order(etf_symbol, "SELL", sell_ltp * 0.99)
                    threading.Thread(target=monitor_order, args=(index_symbol , active_position , sell_order_id, False)).start()
                    active_position = None
                    strat.waiting_for_candle_update = True
                    waiting_for_candle_update[index_symbol] = True
                    active_position = None
                    return

                elif strat.waiting_for_candle_update:
                    now = datetime.datetime.now(pytz.timezone('Asia/Kolkata'))
                    if now.minute % 30 == 15:
                        if strat.update_high_stoploss_after_sell() is None:
                            print("High and stoploss could not be updated. Restarting system..")
                            logging.info("High and stoploss could not be updated. Restarting system..")
                            status = "None"
                            return shutdown()
                        strat.waiting_for_candle_update = False
                        high[index_symbol] = strat.high
                        stoploss[index_symbol] = strat.stoploss
                        waiting_for_candle_update[index_symbol] = strat.waiting_for_candle_update 
                        return
                return
    except Exception as e:
        logging.error(f"on_data error shutting down now: {e}")
        shutdown()
        sys.exit()
        return

def on_open(wsapp):
    logging.info("Webscoket Connected.")
    try:
        print("Websocket Connection opened.")
        correlation_id = "abc123"
        mode = 1  # Full mode (tick data)
        exchangeType = 1  # NSE
        EXCHANGE = "NSE"
        tokens = [TOKENS[idx] for idx in INDEX_ETF_PAIRS.keys()]
        res = sws.subscribe(correlation_id , mode , [{
            "exchangeType" : exchangeType,
            "tokens" : tokens
        }])
        logging.info(f"WebSocket subscribed: {res}")
        return
    except Exception as e:
        logging.error(f"WebSocket subscribe failed: {e}")
        return

def run_trading_loop():
    global sws, strategies
    wait_until_946()
    if status == "OVER":
        shutdown()
        return
    if(not is_market_open()):
        print("Market seems closed. Exiting.")
        shutdown()
        sys.exit()
        return 
    print("Market is open. Proceeding..")
    for index_symbol, etf_symbol in INDEX_ETF_PAIRS.items():
        strat = BreakoutStrategy(smartApi, index_symbol, EXCHANGE, TOKENS[index_symbol])
        if index_symbol in high:
            strat.high = high[index_symbol]
            strat.stoploss = stoploss[index_symbol]
            strat.waiting_for_candle_update = waiting_for_candle_update[index_symbol]
            if trail_anchor[index_symbol]:
                strat.trail_anchor = trail_anchor[index_symbol]
                if isinstance(strat.trail_anchor, str):
                    strat.trail_anchor = datetime.datetime.strptime(strat.trail_anchor, "%Y-%m-%d %H:%M:%S")
            else:
                now = datetime.datetime.now(pytz.timezone('Asia/Kolkata')) - datetime.timedelta(minutes=1)
                aligned_minute = (now.minute // 30) * 30
                to_dt = now.replace(minute=aligned_minute, second=0, microsecond=0)
                from_dt = to_dt - datetime.timedelta(minutes=30)
                strat.trail_anchor = from_dt
            print("Restored high and stoploss.")
            logging.info("Restored high and stoploss")
        else:
            print("Fetching first candle..")
            if not strat.initialize_first_candle():
                print("First candle not ready. Waiting for 60 seconds...")
                time.sleep(60)
                if not strat.initialize_first_candle():
                    print("Candle could not be feteched. Resatring system..")
                    status = "None"
                    return shutdown()
                else:
                    print("Candle fetched sucessfully after restart")
        strategies[index_symbol] = strat
    print("Candle fetch succesfull for all indexes")
    print("LTP of indexes and etfs: ")
    for index_symbol , etf_symbol in INDEX_ETF_PAIRS.items():
        print(f"{index_symbol} : {safe_ltp(index_symbol)} , {etf_symbol}: {safe_ltp(etf_symbol)}")
    for index_symbol , etf_symbol in INDEX_ETF_PAIRS.items():
        print(f"for {index_symbol} , High: {strategies[index_symbol].high} , Stoploss: {strategies[index_symbol].stoploss} , ltp: {safe_ltp(index_symbol)} , anchor_time : {strategies[index_symbol].trail_anvchor}") 
    sws = SmartWebSocketV2(auth_token=authToken, api_key=api_key, client_code=username, feed_token=feedToken)
    sws.on_open = on_open
    sws.on_data = on_data
    sws.on_error = lambda ws, err: logging.warning(f"WebSocket error: {err}")
    sws.on_close = lambda ws: logging.warning("WebSocket closed.")
    sws.connect()

def run():
    global high, stoploss, trail_anchor, waiting_for_candle_update, status
    high, stoploss, trail_anchor, waiting_for_candle_update = {}, {}, {}, {}
    while True:
        if datetime.datetime.now(pytz.timezone('Asia/Kolkata')).time() >= datetime.time(15, 10):
            print("Trading session over.")
            sys.exit()
            return
        if not login():
            print("Login failed. Retrying in 2 minutes...")
            time.sleep(120)
            continue
        run_trading_loop()
        logout()
        if status is None:
            print("Restarting in 2 minutes...")
            time.sleep(120)
            continue
        else:
            print("Day complete.")
            sys.exit()
            return

run()

