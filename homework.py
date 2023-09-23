import os
import logging.config
import time
from http import HTTPStatus

import requests
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

logger = logging.getLogger(__name__)


def check_tokens() -> bool:
    """Проверка наличия токенов."""
    check = True
    if not PRACTICUM_TOKEN:
        check = False
        logger.critical('Отсутствуют переменная PRACTICUM_TOKEN')
        raise Exception('Отсутствует PRACTICUM_TOKEN')
    if not TELEGRAM_TOKEN:
        check = False
        logger.critical('Отсутствуют переменная TELEGRAM_TOKEN')
        raise Exception('Отсутствует TELEGRAM_TOKEN')
    if not TELEGRAM_CHAT_ID:
        check = False
        logger.critical('Отсутствуют переменная TELEGRAM_CHAT_ID')
        raise Exception('Отсутствует TELEGRAM_CHAT_ID')
    return check


def get_api_answer(timestamp):
    """Запрос к API."""
    try:
        response = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params={'from_date': timestamp}
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as error:
        logger.error(
            f'Ошибка при запросе к основному API: {error}. '
            f'Данные: ENDPOINT={ENDPOINT}, '
            f'headers={HEADERS}, '
            f'from_date={timestamp}'
        )
        raise ConnectionError(
            f'Ошибка сервера. {error},'
            f'URL{ENDPOINT}, '
            f'HEADERS, params, TIMEOUT'
        )
    if response.status_code != HTTPStatus.OK:
        logger.error(f'Нет доступа к API. Код ответа: {response.status_code}')
        raise requests.RequestException('Нет доступа к API')
    try:
        return response.json()
    except Exception as error:
        logger.error(f'Ответ сервера не в формате json. {error}')


def check_response(response) -> list:
    """Проверка ответа API на соответствие документации."""
    if type(response) is not dict:
        logger.error('Объект response не является словарем')
        raise TypeError('Объект response не является словарем')
    if 'homeworks' not in response.keys():
        logger.error('Нет ключа "homeworks"')
        raise KeyError('Нет ключа "homeworks"')
    if type(response['homeworks']) is not list:
        logger.error('Данные ответа не являются списком')
        raise TypeError('Данные ответа не являются списком')
    return response['homeworks']


def parse_status(homework) -> str:
    """Извлечение информации о домашней работе."""
    homework_name = homework.get('homework_name')
    homework_status = homework.get('status')
    if homework_name is None:
        logger.error(
            'Отсутствует ключ "homework_name". '
            f'homework_name={homework_name}'
        )
        raise KeyError('Отсутствует ключ "homework_name"')
    if homework_status is None:
        logger.error(
            'Отсутствует ключ "homework_status". '
            f'homework_status={homework_status}'
        )
        raise KeyError('Отсутствует ключ "homework_status"')
    if homework_status not in HOMEWORK_VERDICTS.keys():
        logger.error(
            f'Недокументированный статус. homework_status={homework_status}'
        )
        raise KeyError('Недокументированный статус')

    verdict = HOMEWORK_VERDICTS[homework_status]

    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def send_message(bot, message) -> bool:
    """Отправка сообщения."""
    try:
        bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message,
        )
        logger.debug('Сообщение отправлено')
        return True
    except Exception as error:
        logger.error(f'Не удалось отправить сообщение. {error}')
        return False


def main():
    """Основная логика работы бота."""
    logger.info('Начало работы бота')
    if not check_tokens():
        logger.critical('Некоторые переменные окружения недоступны')
        raise KeyError('Некоторые переменные окружения недоступны')
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = 0
    prev_report = 'Предыдущий отчет'
    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)
            if homeworks:
                message = parse_status(homeworks[0])
            if message != prev_report:
                if send_message(bot, message) is True:
                    prev_report = message
                    timestamp = response.get('current_date', timestamp)
            else:
                logger.debug('Нет новых статусов')
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.exception(error)
            if message != prev_report:
                success = send_message(bot, message)
                if not success:
                    logger.error('Не удалось отправить сообщение')
                prev_report = message
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    logging.config.fileConfig('logger.conf', disable_existing_loggers=False)
    main()
