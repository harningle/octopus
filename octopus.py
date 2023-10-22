#!/usr/local/bin/python3.10
# -*- coding: utf-8 -*-
import asyncio
import configparser
import datetime

import MySQLdb
import pytz
import requests

from notification.graph import Graph
from notification.gmail import gmail_send


def create_table(con: MySQLdb.Connection):
    """Create a table for storing electricity price in MySQL database

    :param con: MySQL connection
    """
    cur = con.cursor()
    cur.execute('CREATE DATABASE IF NOT EXISTS octopus ;')
    cur.execute('USE octopus ;')
    cur.execute('CREATE TABLE IF NOT EXISTS price ('
                'from_period datetime PRIMARY KEY, '
                'to_period datetime, '
                'price FLOAT) ;')
    con.commit()


def get_price(api_key: str, product_code: str) -> list[dict]:
    """
    Get unit rates using Octopus Energy API. See
    https://octopus.energy/dashboard/new/accounts/personal-details/api-access and
    https://developer.octopus.energy/docs/api/#agile-octopus for details.

    :param api_key: API key, e.g. "sk_live_abcdefghijklmnopqrstuvwxyz
    :param product_code: Product code, e.g. "AGILE-18-02-21"
    :return: A json object containing unit rates for each half-hour in the near past and future
    """

    url = f'https://api.octopus.energy/v1/products/{product_code}/electricity-tariffs/' \
          f'E-1R-{product_code}-C/standard-unit-rates/'
    resp = requests.get(url, auth=(api_key, ''))
    return resp.json()


def to_timezone(t: str, tz: str = 'Europe/London') -> str:
    """Convert UTC time to a specific timezone

    :param t: UTC time, e.g. "2021-02-21T00:00:00Z"
    :param tz: Timezone, e.g. "Europe/London"
    :return: Time in the specified timezone, e.g. "2021-02-21T00:00:00+00:00"
    """

    t = datetime.datetime.fromisoformat(t[:-1] + '+00:00')  # https://bugs.python.org/issue35829
    t = t.astimezone(pytz.timezone(tz))  # This will account for DST
    return t.strftime('%Y-%m-%d %H:%M:%S')


def insert_price(con: MySQLdb.Connection, prices: list[dict]):
    """Insert price into MySQL database

    :param con: MySQL connection
    :param prices: A json object containing unit rates for each half-hour
    """

    cur = con.cursor()
    cur.execute('USE octopus ;')
    for p in prices['results']:
        from_period = to_timezone(p['valid_from'])
        to_period = to_timezone(p['valid_to'])
        price = p['value_inc_vat']
        cur.execute(f'INSERT IGNORE INTO price VALUES ("{from_period}", "{to_period}", {price}) ;')
    con.commit()


def get_hours_below_price(con: MySQLdb.Connection, price: float) -> list[[str, str]]:
    """Get hours with electricity price below a specific value

    :param con: MySQL connection
    :param price: Price threshold, e.g. 10.0
    :return: A 2D list of [[from_hour, to_hour], ...]
    """

    # Get today's and tomorrow's date
    today = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S%z') + 'Z'
    today = to_timezone(today).split(' ')[0]  # Only need date
    tomorrow = (datetime.datetime.utcnow() + datetime.timedelta(days=1)) \
        .strftime('%Y-%m-%dT%H:%M:%S%z') + 'Z'
    tomorrow = to_timezone(tomorrow).split(' ')[0]

    # Get hours with price below threshold today and tomorrow
    cur = con.cursor()
    cur.execute('USE octopus ;')
    cur.execute(f'SELECT from_period, to_period FROM price '
                f'WHERE from_period BETWEEN "{today} 00:00:00" AND "{tomorrow} 23:59:59" '
                f'AND price < {price} '
                f'ORDER BY from_period ASC ;')
    hours = cur.fetchall()
    if not hours:
        return []

    # Concat continuous hours
    continuous_hours = [list(hours[0])]
    for hour in hours[1:]:
        if hour[0] == continuous_hours[-1][1]:
            continuous_hours[-1][1] = hour[1]
        else:
            continuous_hours.append(list(hour))

    # Convert time to str. Only need hour and minute, without second
    continuous_hours = [[str(h[0])[0:-3], str(h[1])[0:-3]] for h in continuous_hours]
    return continuous_hours


def format_hours(hours: list[str, str]) -> str:
    """Format hours in HTML table"""

    html = ''
    for h in hours:
        html += f'<tr><td>{h[0]}</td><td></td><td>{h[1]}</td></tr>'
    return html


async def main():
    # Connect to MySQL database
    config = configparser.ConfigParser()
    config.read('config.cfg')
    sql_credentials = config['mysql']
    con = MySQLdb.connect(
        host=sql_credentials['host'],
        user=sql_credentials['user'],
        passwd=sql_credentials['password'],
        charset='utf8mb4'
    )
    # create_table(con)

    # Get price and insert into MySQL database
    octopus_credentials = config['octopus']
    unit_rates = get_price(octopus_credentials['api_key'], octopus_credentials['product_code'])
    insert_price(con, unit_rates)

    # Get hours with low electricity price
    thresholds = [20, 10, 0]
    html = ''
    for t in thresholds:
        hours = get_hours_below_price(con, t)
        html += f'''
        <b>Hours below {t}p/kWh:</b><br>
        <table>
        <tr><th>From</th><th></th><th>To</th></tr>
        '''
        html += format_hours(hours)
        html += '</table><br>'

    # # Init. Graph client
    # config = configparser.ConfigParser()
    # config.read('config.cfg')
    # azure_settings = config['azure']
    # graph: Graph = Graph(azure_settings)
    #
    # # Send email notification
    recipients = config['notification']['recipients']
    # await graph.send_email(emails, 'Octopus price', html)

    # Send email notification via Gmail API
    gmail_send(recipients, 'Octopus price', html)
    pass


if __name__ == '__main__':
    asyncio.run(main())
