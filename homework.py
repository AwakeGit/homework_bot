import os
import sys
import time
from http import HTTPStatus

import exceptions
import logging
from logging import Formatter

import requests
import simplejson
import telegram
from dotenv import load_dotenv

load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

logging.basicConfig(
    level=logging.DEBUG,
    filename='main.log',
    format='%(asctime)s, %(levelname)s, %(message)s, %(name)s'
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(stream=sys.stdout)
handler.setFormatter(Formatter(fmt='[%(asctime)s: %(levelname)s] %(message)s'))
logger.addHandler(handler)

LIST_RECEIVED_MESSAGE = 'Список работ получен.'
ERROR_MESSAGE = 'Ошибка при обработке ответа API:'
SEND_ERROR_MESSAGE = 'Ошибка при отправке сообщения:'


def check_tokens():
    """Проверка наличия всех токенов."""
    tokens = {
        'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
        'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
        'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID
    }

    for token_name, token_value in tokens.items():
        if not token_value:
            logger.critical(f'Отсутствует токен: "{token_name}"')
            return False

    return True


def send_message(bot, message):
    """Отправка сообщения в TG и возврат статуса успешной отправки."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug('Сообщение успешно отправлено в чат')
        return True
    except telegram.error.TelegramError as error:
        error_message = f'Сбой при отправке сообщения в чат - {error}'
        logger.error(error_message)
        return False


def get_api_answer(timestamp):
    """Делает запрос к API яндекса."""
    payload = {'from_date': timestamp}
    try:
        homework_statuses = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params=payload,
        )
    except requests.exceptions.RequestException as error:
        raise exceptions.EndpointError(f'Ошибка при запросе к API: {error}')
    if homework_statuses.status_code != HTTPStatus.OK:
        raise exceptions.StatusCodeException(
            'HTTP статус ответа API != 200'
        )
    try:
        return homework_statuses.json()
    except simplejson.errors.JSONDecodeError as error:
        raise exceptions.JsonError(
            f'Невозможно получить данные в JSON: {error}'
        ) from None


def check_response(response):
    """Проверяет ответ API на соответствие документации."""
    if not isinstance(response, dict):
        raise TypeError('response не соответствует документации')

    required_keys = {'homeworks', 'current_date'}
    for key in required_keys:
        if key not in response:
            raise KeyError(f'Отсутствует ключ {key}')

    if not isinstance(response['homeworks'], list):
        raise TypeError('Данные переданы не в виде списка')

    homeworks = response.get('homeworks')
    if not homeworks:
        raise IndexError('Список с домашними работами пуст')

    return homeworks


def parse_status(homework):
    """Извлекает статус домашней работы."""
    homework_name = homework.get('homework_name')
    hw_status = homework.get('status')

    if not homework_name:
        raise KeyError('Отсутствует ключ "homework_name"')

    verdict = HOMEWORK_VERDICTS.get(hw_status)

    if verdict is None:
        raise KeyError('Статуса нет в словаре вердиктов')

    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        return
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    first_status = ''
    error_message = ''

    while True:
        try:
            response = get_api_answer(timestamp)
            check_response(response)
            logger.info(LIST_RECEIVED_MESSAGE)
            new_status = parse_status(response['homeworks'][0])

            if new_status != first_status:
                sent_successfully = send_message(bot, new_status)

                if sent_successfully:
                    first_status = new_status
                    error_message = ''

        except KeyError as key_error:
            new_error_message = f'{ERROR_MESSAGE} {key_error}'
            logger.error(new_error_message)
            if new_error_message != error_message:
                sent_successfully = send_message(bot, new_error_message)
                if sent_successfully:
                    error_message = new_error_message

        except exceptions.SendMessageException as send_error:
            new_error_message = f'{SEND_ERROR_MESSAGE} {send_error}'
            logger.error(new_error_message)
            if new_error_message != error_message:
                sent_successfully = send_message(bot, new_error_message)
                if sent_successfully:
                    error_message = new_error_message

        except Exception as error:
            new_error_message = f'Сбой в работе программы: {error}'
            logger.error(new_error_message)
            if new_error_message != error_message:
                sent_successfully = send_message(bot, new_error_message)
                if sent_successfully:
                    error_message = new_error_message

        finally:
            timestamp = response.get('current_date', timestamp)
            time.sleep(RETRY_PERIOD)
