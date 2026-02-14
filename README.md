# Overview  
This is a python-based implementation of an trading strategies(algorithimic trading). I have used   
(AngelOne's SmartAPI)[https://smartapi.angelbroking.com/docs] python SDK to execute the strategies. 
# Project Directory  
The project consists of the following files:  
1. **main.py** : The file that makes direct use of SmartAPI's python SDK for performing tasks such as :
                 1. Authorization to the API
                 2. Accessing live stock price
                 3. Placing orders
                 4. Terminate the complete trading system for the day
2. **strategy.py** : This file contains the complete logical structure of the trading strategy.
                     It includes tasks such as making calculations of target price/stoploss and generating buy/sell signals.
# Project setup  
The following steps need to be followed to deploy a strategy:  
1. Refer to (SmartAPI's documentation)[https://smartapi.angelbroking.com/docs] for various features.
2. Create an account and generate your API key and token for authorization purposes.
3. On you local directory run the command *pip install -r requirements_dev.txt* to install depencies.
