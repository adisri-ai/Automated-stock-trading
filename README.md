# Overview  
This is a python-based implementation of an trading strategies(algorithimic trading). I have used   
**AngelOne's SmartAPI** python SDK to execute the strategies. 
# Project Directory  
The project consists of the following files:  
1. **main.py** : The file that makes direct use of SmartAPI's python SDK for performing tasks such as :
                 1. Authorization to the API
                 2. Accessing live stock price
                 3. Placing orders
                 4. Terminate the complete trading system for the day
2. **strategy.py** : This file contains the complete logical structure of the trading strategy.
                     It includes tasks such as making calculations of target price/stoploss and generating buy/sell signals.
