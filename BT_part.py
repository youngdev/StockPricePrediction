"""Back testing part
Stock trading simulation using prediction of trained machine learning models
"""


import pytz
from datetime import datetime
from zipline.algorithm import TradingAlgorithm
from zipline.utils.factory import load_bars_from_yahoo
from zipline.api import (
    order,
    record,
    symbol,
    get_datetime,
    set_long_only)
import matplotlib.pyplot as plt
import pandas as pd
from log import MyLogger
import pickle
from ML_part import cnn_model_fn
import numpy as np
import tensorflow as tf
from tensorflow.contrib import learn
from tensorflow.contrib.learn.python.learn.estimators import model_fn as model_fn_lib


def initialize(context):
    # AAPL
    context.security = symbol('AAPL')

    # Load TP matrix
    pkl_file = open("data/TP_matrixs.pkl", "rb")
    context.TP_matrixs = pickle.load(pkl_file)
    pkl_file.close()

    # Load trained model
    context.cnn_estimator = learn.Estimator(
        model_fn=cnn_model_fn,
        model_dir="model/convnet_model")

    # Threshold for stock price change ratio
    context.threshold_up = 0
    context.threshold_down = 0

    # Algorithm will only take long positions.
    # It will stop if encounters a short position.
    set_long_only()


def handle_data(context, data):
    # Get current date
    now = str(get_datetime('US/Eastern'))[0:11] + "00:00:00+0000"

    # Get current state
    state = context.TP_matrixs.ix[now].values

    # Predict using the estimator
    predictions = context.Q_estimator.predict(
        x=state.astype(np.float32))
    ratio_predict = predictions["results"][0][0]
    mylogger.logger.info(ratio_predict)

    # Execute chosen action
    now = now[0: 10]
    if ratio_predict < context.threshold_down:
        # Sell
        # No short
        try:
            order(context.security, 100)
            mylogger.logger.info(now + ': sell')
        except Exception as e:
            mylogger.logger.info(now + ': No short!')
        action = "sell"
    elif ratio_predict > context.threshold_up:
        # Buy
        # No cover
        if context.portfolio.cash >= data.current(context.security, 'price') * 100:
            order(context.security, 100)
            mylogger.logger.info(now + ': buy')
            mylogger.logger.info(context.portfolio.cash)
        else:
            mylogger.logger.info(now + ': No cover!')
        action = "buy"
    else:
        # Hold
        mylogger.logger.info(now + ': hold')
        action = "hold"

    # Save values for later inspection
    record(AAPL=data.current(context.security, 'price'),
           actions=action)


def analyze(context=None, results=None):
    """Anylyze the result of algorithm"""
    # Total profit and loss
    total_pl = (results['portfolio_value'][-1] - capital_base) / capital_base
    mylogger.logger.info('Total profit and loss: ' + str(total_pl))

    # Hit rate by day
    hit_num = 0
    actions = results['actions'].dropna()
    actions = actions.drop(actions.index[-1])
    hit_record = actions.copy(deep=True)
    for date in hit_record.index:
        loc_current = results['AAPL'].index.get_loc(date)
        change_ratio = (results['AAPL'][loc_current + 1] -
                        results['AAPL'][loc_current]) / results['AAPL'][loc_current]
        # "hit" means that trend and signal match
        # "miss" means that trend and signal dismatch
        if (change_ratio > context.threshold_up and results['actions'][date] == 'buy') or (change_ratio < context.threshold_down and results['actions'][date] == 'sell') or (change_ratio < context.threshold_up and change_ratio > context.threshold_down and results['actions'][date] == 'hold'):
            hit_record[date] = 'hit'
            hit_num += 1
        else:
            hit_record[date] = 'miss'
    # compute hit rate
    hit_rate = hit_num / len(hit_record)
    # Construct hit table
    hit_data = {'signal': actions.values,
                'hit/miss': hit_record.values}
    hit_table = pd.DataFrame(hit_data, index=hit_record.index)
    mylogger.logger.info('Hit table:')
    mylogger.logger.info('Date          signal  hit/miss')
    for i in range(0, len(hit_table)):
        mylogger.logger.info(str(hit_table.index[i])[0: 10] + '    ' +
                             str(hit_table['signal'][i]) + '    ' +
                             str(hit_table['hit/miss'][i]))
    mylogger.logger.info('Hit number:' + str(hit_num) +
                         '/' + str(len(hit_record)))
    mylogger.logger.info('Hit rate:' + str(hit_rate))

    # Draw the figure
    fig = plt.figure(figsize=(12, 7))
    fig.canvas.set_window_title('Stock Trading Algorithm')

    # Subplot 1
    # Comparison between portfolio value and stock value
    ax1 = fig.add_subplot(211)
    ax1.set_ylabel('Comparison between Portfolio Value and Stock Value')
    # Portfolio value
    results['portfolio_value'].plot(ax=ax1,
                                    label='Portfolio')
    # Stock value with the same initialization
    stock_value = results['AAPL'].copy(deep=True)
    flag_first = True
    share_number = 0
    for day in stock_value.index:
        if flag_first:
            share_number = capital_base / stock_value[day]
            stock_value[day] = capital_base
            flag_first = False
        else:
            stock_value[day] *= share_number
    stock_value.plot(ax=ax1,
                     color='k',
                     label='APPL')
    plt.legend(loc='upper left')

    # Subplot 2
    # Marks of actions
    ax2 = fig.add_subplot(212)
    ax2.set_ylabel('Action Marks')
    results['AAPL'].plot(ax=ax2,
                         color='k',
                         label='AAPL Price')
    actions_sell = results['actions'].ix[[
        action == 'sell' for action in results['actions']]]
    actions_buy = results['actions'].ix[[
        action == 'buy' for action in results['actions']]]
    actions_hold = results['actions'].ix[[
        action == 'hold' for action in results['actions']]]
    # Use "v" to represent sell action
    ax2.plot(actions_sell.index,
             results['AAPL'].ix[actions_sell.index],
             'v',
             markersize=2,
             color='g',
             label='Sell')
    # Use "^" to represent buy action
    ax2.plot(actions_buy.index,
             results['AAPL'].ix[actions_buy.index],
             '^',
             markersize=2,
             color='r',
             label='Buy')
    # Use "." to represent hold action
    ax2.plot(actions_hold.index,
             results['AAPL'].ix[actions_hold.index],
             '.',
             markersize=2,
             color='b',
             label='Hold')
    plt.legend(loc='upper left')

    # Save figure into file
    fig_name = 'log/' + directory_log + '/fig' + directory_log + '.png'
    plt.savefig(fig_name)

    # Show figure on the screen
    plt.show()


if __name__ == '__main__':
    # Instantiate log
    mylogger = MyLogger()
    # Log directory
    directory_log = str(datetime.now())[0:19]

    # Load data
    start_date = datetime(2014, 1, 1, 0, 0, 0, 0, pytz.utc)
    end_date = datetime(2016, 1, 1, 0, 0, 0, 0, pytz.utc)
    data = load_bars_from_yahoo(stocks=['AAPL'],
                                start=start_date,
                                end=end_date)

    # Create algorithm object passing in initialize and
    # handle_data functions
    capital_base = 100000
    algo_obj = TradingAlgorithm(initialize=initialize,
                                handle_data=handle_data,
                                analyze=analyze,
                                data_frequency='daily',
                                capital_base=capital_base)

    # Run algorithm
    perf = algo_obj.run(data)