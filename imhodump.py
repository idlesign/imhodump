# -*- coding: utf-8 -*-
import requests
import logging
import os
import shutil
import datetime
import argparse

from lxml import etree
from json import dumps, loads
from math import ceil
from collections import OrderedDict
from urllib.parse import quote


logging.basicConfig()
logger = logging.getLogger(os.path.basename(__file__))
logger.setLevel(logging.INFO)


VERSION = (0, 5, 0)


class ImhoDumper:

    SUBJECT_FILMS = 'films'
    SUBJECT_BOOKS = 'books'
    SUBJECT_GAMES = 'games'
    SUBJECT_SERIES = 'serials'

    TARGET_GOODREADS = 'Goodreads'
    TARGET_KINOPOISK = 'КиноПоиск'
    TARGETS = {
        TARGET_GOODREADS: 'https://www.goodreads.com/search?utf8=%E2%9C%93&q={term}&search_type=books',
        TARGET_KINOPOISK: 'http://www.kinopoisk.ru/index.php?first=no&what=&kp_query={term}',
    }

    SUBJECTS = {
        SUBJECT_FILMS: [TARGET_KINOPOISK],
        SUBJECT_BOOKS: [TARGET_GOODREADS],
        SUBJECT_GAMES: [],
        SUBJECT_SERIES: [TARGET_KINOPOISK]
    }

    URL_RATES_TPL = 'http://user.imhonet.ru/%(user_id)s/content/%(subject)s/rates/%(rating)s/?page=%(page)s'
    START_FROM_RATING = 1

    def __init__(self, user_id, subject):
        self.user_id = user_id
        self.subject = subject
        self.output_filename = 'imho_rates_%s_%s.json' % (subject, user_id)

    def get_rates(self, html, rating):
        items = html.xpath('//div[@class="m-rate-list-item"]')

        def get_meta_content(name):
            try:
                value = html_details.xpath('.//meta[@itemprop="%s"]' % name)[0].get('content').strip()
            except IndexError:
                value = None
            return value

        for item in items:
            heading = item.xpath('.//a[@class="m-rate-item-content-header-link"]')[0].text.strip()
            details_url = item.xpath('.//a[@class="m-rate-item-link"]')[0].get('href').strip()

            logger.info('Обрабатываем "%s" ...', heading)

            response = requests.get(details_url)
            html_details = etree.HTML(response.text)

            html_details = html_details.xpath('//div[@class="_index_content__Nrmux layout_colContent__3D7W7"]')[0]
            year = get_meta_content('dateCreated')
            heading = get_meta_content('name') or heading

            try:
                title_orig = html_details.xpath('.//div[@itemprop="alternativeHeadline"]')[0].text.strip()

            except (IndexError, AttributeError):
                logger.debug('** Название на языке оригинала не заявлено, наверное наше кино')
                title_orig = None

            logger.debug('Оригинальное название: %s', title_orig)
            logger.debug('Год: %s' % year)

            if year is not None:
                heading = heading.replace('(%s)' % year, '').strip()

            item_data = {
                'title_ru': heading,
                'title_orig': title_orig,
                'rating': rating,
                'year': year,
                'details_url': details_url
            }

            if self.subject == self.SUBJECT_FILMS:
                countries = []

                for country in html_details.xpath('.//meta[@itemprop="countryOfOrigin"]') or []:
                    countries.append(country.get('content').strip())

                item_data['country'] = ', '.join(countries)

            yield item_data

    def process_url(self, rating, page, recursive=False):

        page_url = self.URL_RATES_TPL % {
            'user_id': self.user_id, 'subject': self.subject, 'rating': rating, 'page': page}

        logger.info('Обрабатывается страница %s ...', page_url)
        logger.debug('Рейтинг: %s', rating)

        response = requests.get(page_url)

        if response.status_code != 200:
            return {}

        text = response.text
        html = etree.HTML(text)

        yield from self.get_rates(html, rating)

        if recursive:
            yield from self.process_url(rating, page + 1, recursive)

    def dump_to_file(self, filename, existing_items=None, start_from_rating=1):
        logger.info('Собираем оценки пользователя %s в файл %s', self.user_id, filename)

        with open(filename, 'w') as f:
            f.write('[')

            try:
                if existing_items:
                    f.write('%s,' % dumps(list(existing_items.values()), indent=4).strip('[]'))

                for rating in range(start_from_rating, 11):

                    for item_data in self.process_url(rating, 1, True):
                        if not item_data:
                            continue

                        if not existing_items or item_data['details_url'] not in existing_items:
                            line = '%s,' % dumps(item_data, indent=4)
                            f.write(line)
                            f.flush()

            except Exception:
                logger.error('Необработанная ошибка: %s', exc_info=True)

            finally:
                f.write('{}]')

    def load_from_file(self, filename):
        result = OrderedDict()

        if os.path.exists(filename):
            logger.info('Загружаем ранее собранные оценки пользователя %s из файла %s' % (self.user_id, filename))

            with open(filename, 'r') as f:
                data = f.read()

            try:
                data = loads(data, object_pairs_hook=OrderedDict)

            except:
                logger.error('Ошибка загрузки json: %s', exc_info=True)
                return None

            result = OrderedDict([(entry['details_url'], entry) for entry in data if entry])

        return result

    def make_html(self, filename):

        html_base = '''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Оценки подраздела %(subject)s imhonet</title>
            <meta http-equiv="content-type" content="text/html; charset=utf-8" />
            <style>
                body {
                    color: #333;
                    font-family: Verdana, Arial, helvetica, sans-serif;
                }
                h1, h6 {
                    color: #999;
                }
                .rate_block {
                    border-bottom: 1px solid #eee;
                    padding: 0.4em;
                    padding-bottom: 1.2em;
                }
                .rating {
                    font-size: 1.5em;
                }
                .info, .description {
                    display: inline-block;
                    margin-left: 0.7em;
                    vertical-align: middle;
                }
                .rating .current {
                    color: #800;
                }
                .rating .total {
                    font-size: 0.7em;
                    color: #aaa;
                }
                .title_ru {
                    font-size: 1.7em;
                }
                .title_orig {
                    color: #aaa;
                }
                .links {
                    padding-top: 0.5em;
                    font-size: 0.8em;
                }
                .link {
                    display: inline-block;
                    margin-right: 0.5em;
                }
            </style>
        </head>
        <body>
            <h1>Оценки подраздела %(subject)s imhonet</h1>
            <h6>Всего оценок: %(rates_num)s</h6>
            %(rating_rows)s
        </body>
        </html>
        '''

        html_rating_row = '''
        <div class="rate_block">
            <div class="info">
                <div class="year">%(year)s</div>
                <div class="rating">
                    <span class="current">%(rating)s</span><span class="total">/10</span>
                    <span class="current">%(rating_five)s</span><span class="total">/5</span>
                </div>
            </div>
            <div class="description">
                <div class="titles">
                    <div class="title_ru">
                        <label><input type="checkbox"> %(title_ru)s</label>
                    </div>
                    <div class="title_orig">%(title_orig)s</div>
                </div>
                <div class="links">
                    Поиск:
                    %(links)s
                </div>
            </div>
        </div>
        '''

        html_link_row = '''
        <div class="link"><a href="%(link)s" target="_blank">%(title)s</a></div>
        '''

        records = self.load_from_file(filename)

        rating_rows = []
        for record in records.values():
            links = []
            for link_type in self.SUBJECTS[self.subject]:
                for title_type in ('title_orig', 'title_ru'):
                    if record[title_type]:
                        links.append(html_link_row % {
                            'link': self.TARGETS[link_type].replace('{term}', quote(record[title_type])),
                            'title': '%s (%s)' % (link_type, title_type)
                        })

            record['links'] = '\n'.join(links)
            record['rating_five'] = ceil(record['rating'] / 2)
            del record['details_url']
            rating_rows.append(html_rating_row % record)

        target_file = '%s.html' % os.path.splitext(filename)[0]
        logger.info('Создаём html файл с оценками: %s', target_file)

        with open(target_file, 'w') as f:
            f.write(
                html_base % {
                    'subject': self.subject,
                    'rates_num': len(records),
                    'rating_rows': '\n'.join(rating_rows)
                })

    def backup_json(self, filename):
        target_filename = '%s.bak%s' % (filename, datetime.datetime.isoformat(datetime.datetime.now()))
        logger.info('Делаем резервную копию файла с оценками: %s', target_filename)
        shutil.copy(filename, target_filename)

    def dump(self):
        existing_items = self.load_from_file(self.output_filename)
        if existing_items:
            self.backup_json(self.output_filename)
        self.dump_to_file(self.output_filename, existing_items=existing_items, start_from_rating=self.START_FROM_RATING)
        self.make_html(self.output_filename)


if __name__ == '__main__':

    args_parser = argparse.ArgumentParser()
    args_parser.add_argument('user_id', help='ID пользователя imhonet')
    args_parser.add_argument('subject', help='Категория: %s' % ', '.join([s for s in ImhoDumper.SUBJECTS.keys()]))
    args_parser.add_argument(
        '--html_only',
        help='Указывает, что требуется только экспорт уже имеющегося файла с оценками в html', action='store_true')

    parsed = args_parser.parse_args()

    if parsed.subject != ImhoDumper.SUBJECT_FILMS:
        logger.warning(
            'Разбор проверен 2017-04-16 для раздела Фильмы. '
            'Разбор данных из других разделов может не работать.')

    dumper = ImhoDumper(parsed.user_id, parsed.subject)

    if parsed.html_only:
        dumper.make_html(dumper.output_filename)

    else:
        dumper.dump()
