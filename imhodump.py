#-*- coding: utf-8 -*-
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

VERSION = (0, 4, 0)


class ImhoDumper():

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

    URL_RATES_TPL = 'http://%s.imhonet.ru/content/%s/rates/%s/'
    START_FROM_RATING = 1

    def __init__(self, username, subject):
        self.username = username
        self.subject = subject
        self.output_filename = 'imho_rates_%s_%s.json' % (subject, username)

    def get_rates(self, html, rating):
        rate_boxes = html.xpath("//div[@class='m-inlineitemslist-describe']")
        for rate_box in rate_boxes:
            heading = rate_box.xpath("div[@class='m-inlineitemslist-describe-h2']/a")[0]
            title_ru = heading.text.strip()
            details_url = heading.get('href').strip()
            logger.info('Обрабатываем "%s" ...' % title_ru)

            # info = rate_box.xpath("div[@class='m-inlineitemslist-describe-gray']")[0].text.strip()          
            block_with_year = rate_box.xpath("div[@class='m-inlineitemslist-describe-gray']/span")[1]
            year = block_with_year.get('data-content')                  

            req_details = requests.get(details_url)
            html_details = etree.HTML(req_details.text)

            try:
                title_orig = html_details.xpath("//div[@class='m-elementprimary-language']")[0].text.strip()
            except (IndexError, AttributeError):
                logger.debug('** Название на языке оригинала не заявлено, наверное наше кино')
                title_orig = None

            logger.debug('Оригинальное название: %s' % title_orig)

            # try:
            #     year = info.split('<br>')[0].strip().split(',')[-1].strip().split(' ')[0].strip()                
            # except AttributeError:
            #     year = None
   

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

    def process_url(self, page_url, rating, recursive=False):

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

        yield from self.get_rates(html, rating)

        if recursive and next_page_url is not None:
            yield from self.process_url(next_page_url, rating, recursive)

    def dump_to_file(self, filename, existing_items=None, start_from_rating=1):
        logger.info('Собираем оценки пользователя %s в файл %s' % (self.username, filename))

        with open(filename, 'w') as f:
            f.write('[')
            try:
                if existing_items:
                    f.write('%s,' % dumps(list(existing_items.values()), indent=4).strip('[]'))
                for rating in range(start_from_rating, 11):
                    for item_data in self.process_url(self.URL_RATES_TPL % (self.username, self.subject, rating), rating, True):
                        if item_data['details_url'] not in existing_items:
                            f.write('%s,' % dumps(item_data, indent=4))
            finally:
                f.write('{}]')

    def load_from_file(self, filename):
        result = OrderedDict()
        if os.path.exists(filename):
            logger.info('Загружаем ранее собранные оценки пользователя %s из файла %s' % (self.username, filename))
            with open(filename, 'r') as f:
                data = f.read()
            result = OrderedDict([(entry['details_url'], entry) for entry in loads(data, object_pairs_hook=OrderedDict) if entry])
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
        logger.info('Создаём html файл с оценками: %s' % target_file)
        with open(target_file, 'w') as f:
            f.write(html_base % {'subject': self.subject, 'rates_num': len(records), 'rating_rows': '\n'.join(rating_rows)})

    def backup_json(self, filename):
        target_filename = '%s.bak%s' % (filename, datetime.datetime.isoformat(datetime.datetime.now()))
        logger.info('Делаем резервную копию файла с оценками: %s' % target_filename)
        shutil.copy(filename, target_filename)

    def dump(self):
        existing_items = self.load_from_file(self.output_filename)
        if existing_items:
            self.backup_json(self.output_filename)
        self.dump_to_file(self.output_filename, existing_items=existing_items, start_from_rating=self.START_FROM_RATING)
        self.make_html(self.output_filename)


if __name__ == '__main__':

    args_parser = argparse.ArgumentParser()
    args_parser.add_argument('username', help='Имя пользователя imhonet')
    args_parser.add_argument('subject', help='Категория: %s' % ', '.join([s for s in ImhoDumper.SUBJECTS.keys()]))
    args_parser.add_argument('--html_only', help='Указывает, что требуется только экспорт уже имеющегося файла с оценками в html', action='store_true')

    parsed = args_parser.parse_args()

    dumper = ImhoDumper(parsed.username, parsed.subject)
    if parsed.html_only:
        dumper.make_html(dumper.output_filename)
    else:
        dumper.dump()
