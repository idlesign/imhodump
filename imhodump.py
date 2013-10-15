#-*- coding: utf-8 -*-
from json import dumps
import requests
import re

from lxml import etree
from datetime import date


URL_RATES_ALL = 'http://idle.imhonet.ru/content/films/rates/all/'
OUTPUT_FILENAME = 'imho_rates.json'


VERSION = (0, 1, 0)
RE_DATE_STR = re.compile(r'(?P<day>\d{1,2})\s(?P<month>\S+)(\s(?P<year>\d{4}))?')
MONTHS = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']


def normalize_date(date_str):
    real_date = date_str.split(',')[-1].strip()
    match = re.search(RE_DATE_STR, real_date)
    date_dict = match.groupdict()
    if date_dict['year'] is None:
        date_dict['year'] = date.today().year
    date_dict['day'] = date_dict['day'].zfill(2)
    date_dict['month'] = str(MONTHS.index(date_dict['month'].encode('utf-8'))).zfill(2)
    return '%s-%s-%s' % (date_dict['year'], date_dict['month'], date_dict['day'])


def get_rates(page_url, recursive=False):
    print('\nСтраница %s ...' % page_url)
    
    req = requests.get(page_url)
    html = etree.HTML(req.text)
    try:
        next_page_url = html.xpath("//div[@class='pager']/a[@class='rarr']")[0].get('href')
    except IndexError:
        next_page_url = None

    rate_boxes = html.xpath("//li[@class='element-type clearfix']")

    for rate_box in rate_boxes:
        heading = rate_box.xpath("div[@class='content']/div[@class='title']/a")[0]
        title_ru = heading.text.strip().encode('utf-8')
        print('Обработка %s ...' % title_ru)

        info = rate_box.xpath("div[@class='content']/div[@class='info']/div[@class='country']")[0]
        rate_data = rate_box.xpath("div[@class='content']/div[@class='widget-compare']/div[@class='other']/span/div[@class='rate-table ']/span/span/i")[0] 
        rate_percent = int(rate_data.get('style').split(' ')[1].strip('%'))
        details_url = heading.get('href').strip()
        try:
            dates_data = rate_box.xpath("div[@class='content']/div[@class='widget-compare']/div[@class='info list-rates-info']")[0].text.split('<br>')
        except IndexError:
            date_watched = date_rated = u'1 января 1970'
        else:
            date_rated = dates_data[0]
            date_watched = date_rated
            if len(dates_data) == 2:
                date_watched = dates_data[1]
        
        req_details = requests.get(details_url)
        html_details = etree.HTML(req_details.text)

        try:
            title_en = html_details.xpath("//div[@class='m-elementprimary-language']")[0].text.strip().encode('utf-8')
        except (IndexError, AttributeError):
            print('    ** Без названия на языке оригинала')
            title_en = None

        try:
            year = info.text.strip().split(',')[-1].strip().split(' ')[0].strip()
        except AttributeError:
            year = None

        item_data = {
            'title_ru': title_ru,
            'title_en': title_en,
            'rate': (rate_percent / 10),
            'year': year,
            'date_rated': normalize_date(date_rated),
            'date_watched': normalize_date(date_watched),
            'details_url': details_url
        }
        yield item_data

    if recursive and next_page_url is not None:
        for line in get_rates(next_page_url, recursive):
            yield line


if __name__ == '__main__':
    with open(OUTPUT_FILENAME, 'wb') as f:
        f.write('[')
        try:
            for line in get_rates(URL_RATES_ALL, True):
                f.write(dumps(line))
                f.write(',')
        finally:
            f.write(']')