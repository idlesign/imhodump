#-*- coding: utf-8 -*-
import requests
import logging
import os
import shutil
import datetime

from lxml import etree
from json import dumps, loads


logging.basicConfig()
logger = logging.getLogger(os.path.basename(__file__))
logger.setLevel(logging.INFO)


USERNAME = 'idle'


VERSION = (0, 2, 0)

URL_RATES_TPL = 'http://%s.imhonet.ru/content/films/rates/%s/'
OUTPUT_FILENAME = 'imho_rates_%s.json' % USERNAME
START_FROM_RATING = 1


def get_rates(html, rating):
    rate_boxes = html.xpath("//div[@class='m-inlineitemslist-describe']")
    for rate_box in rate_boxes:
        heading = rate_box.xpath("div[@class='m-inlineitemslist-describe-h2']/a")[0]
        title_ru = heading.text.strip()
        details_url = heading.get('href').strip()
        logger.info('Обрабатываем "%s" ...' % title_ru)

        info = rate_box.xpath("div[@class='m-inlineitemslist-describe-gray']")[0].text.strip()

        req_details = requests.get(details_url)
        html_details = etree.HTML(req_details.text)

        try:
            title_orig = html_details.xpath("//div[@class='m-elementprimary-language']")[0].text.strip()
        except (IndexError, AttributeError):
            logger.debug('** Название на языке оригинала не заявлено, наверное наше кино')
            title_orig = None

        logger.debug('Оригинальное название: %s' % title_orig)

        try:
            year = info.split('<br>')[0].strip().split(',')[-1].strip().split(' ')[0].strip()
        except AttributeError:
            year = None

        logger.debug('Год: %s' % year)

        if year is not None:
            title_ru = title_ru.replace('(%s)' % year, '').strip()

        item_data = {
            'title_ru': title_ru,
            'title_orig': title_orig,
            'rating': rating,
            'year': year,
            'details_url': details_url
        }

        yield item_data


def process_url(page_url, rating, recursive=False):

    logger.info('Обрабатывается страница %s ...' % page_url)
    logger.debug('Рейтинг: %s' % rating)

    req = requests.get(page_url)
    text = req.text.replace('<!--noindex-->', ''). replace('<!--/noindex-->', '')
    html = etree.HTML(text)

    try:
        next_page_url = html.xpath("//div[@class='m-pagination']/a")[-1].get('href')
    except IndexError:
        next_page_url = None

    if next_page_url == page_url:
        next_page_url = None

    logger.info('Следующая страница: %s' % next_page_url)

    yield from get_rates(html, rating)

    if recursive and next_page_url is not None:
        yield from process_url(next_page_url, rating, recursive)


def dump_to_file(filename, existing_items=None, start_from_rating=1):
    logger.info('Собираем оценки пользователя %s в файл %s' % (USERNAME, filename))

    with open(filename, 'w') as f:
        f.write('[')
        try:
            if existing_items:
                f.write('%s,' % dumps(list(existing_items.values()), indent=4).strip('[]'))
            for rating in range(start_from_rating, 10):
                for item_data in process_url(URL_RATES_TPL % (USERNAME, rating), rating, True):
                    if item_data['details_url'] not in existing_items:
                        f.write('%s,' % dumps(item_data, indent=4))
        finally:
            f.write('{}]')


def load_from_file(filename):
    result = {}
    if os.path.exists(filename):
        logger.info('Загружаем ранее собранные оценки пользователя %s из файла %s' % (USERNAME, filename))
        with open(filename, 'r') as f:
            data = f.read()
        result = {entry['details_url']: entry for entry in loads(data) if entry}
    return result


def backup_json(filename):
    target_filename = '%s.bak%s' % (filename, datetime.datetime.isoformat(datetime.datetime.now()))
    logger.info('Делаем резервную копию файла с оценками: %s' % target_filename)
    shutil.copy(filename, target_filename)


def json_to_imdb_csv(input_filename):
    target_filename = '%s.csv' % os.path.splitext(os.path.basename(input_filename))[0]
    logger.info('Экспортируем оценки из файла %s в файл %s' % (input_filename, target_filename))
    items = load_from_file(input_filename)
    out_lines = [
        '"position","const","created","modified","description","Title","Title type","Directors","You rated","IMDb Rating","Runtime (mins)","Year","Genres","Num. Votes","Release Date (month/day/year)","URL"',
    ]
    for position, item in enumerate(items.values(), 1):
        line = '"%(position)s","%(id)s","%(created)s","%(modified)s","%(description)s","%(title)s","%(type)s","%(director)s","%(rating)s","%(rating_imdb)s","%(runtime)s","%(year)s","%(genres)s","%(votes)s","%(release_date)s","%(url)s"' % {
            'position': position,
            'id': 'tt0000000',  # По этому идентификатору КиноПоиск производит связь. А у нас он фиктивный %(
            'created': 'Wed Oct 16 00:00:00 2013',
            'modified': '',
            'description': '',
            'title': item['title_ru'].replace('"', '""'),
            'type': '',
            'director': '',
            'rating': item['rating'],
            'rating_imdb': '0.0',
            'runtime': '0',
            'year': item['year'],
            'genres': '',
            'votes': '0',
            'release_date': '',
            'url': item['details_url']
        }
        out_lines.append(line)
    with open(target_filename, 'w') as f:
        f.write('\n'.join(out_lines))


if __name__ == '__main__':
    existing_items = load_from_file(OUTPUT_FILENAME)
    if existing_items:
        backup_json(OUTPUT_FILENAME)
    dump_to_file(OUTPUT_FILENAME, existing_items=existing_items, start_from_rating=START_FROM_RATING)
    json_to_imdb_csv(OUTPUT_FILENAME)
