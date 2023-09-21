import json
import logging
import os
import sys
import time
from datetime import datetime
from http import HTTPStatus

from dotenv import load_dotenv
import exceptions
import requests
from telegram import Bot, TelegramError

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


def check_tokens():
    """Проверяет доступность переменных окружения."""
    return all([TELEGRAM_TOKEN, PRACTICUM_TOKEN, TELEGRAM_CHAT_ID])


def send_message(bot, message):
    """Отправляет сообщение в Telegram чат и выводит информацию в лог."""
    try:
        logging.debug('Начало отправки')
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    except TelegramError as error:
        error_message = f'Не удалось отправить сообщение {error}'
        logging.error(error_message)
        return False
    else:
        logging.info(f'Сообщение отправлено: {message}')
        print(f'[INFO] Сообщение отправлено: {message}')
        return True


def get_api_answer(timestamp):
    """Делает запрос к эндпоинту API-сервиса и выводит информацию в лог."""
    params = {'from_date': timestamp}
    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=params)
    except requests.exceptions.RequestException as error:
        error_message = f'Ошибка при запросе к API: {error}'
        logging.error(error_message)
        raise exceptions.WrongHttpStatus(error_message)
    status_code = response.status_code
    if status_code != HTTPStatus.OK:
        error_message = f'{ENDPOINT} - недоступен. ' \
                        f'Код ответа API: {status_code}'
        logging.error(error_message)
        raise exceptions.WrongHttpStatus(error_message)
    try:
        response = response.json()
    except json.JSONDecodeError as error:
        json_error_message = f'Данные не являются допустимым форматом JSON: ' \
                             f'{error}'
        logging.error(json_error_message)
    return response


def check_response(response):
    """Проверяет валидность ответа."""
    logging.debug('Начало проверки')
    if not isinstance(response, dict):
        raise TypeError('Ошибка в типе ответа API')
    if 'homeworks' not in response or 'current_date' not in response:
        raise KeyError('Пустой ответ от API')
    homeworks = response.get('homeworks')
    if not isinstance(homeworks, list):
        raise TypeError('Homeworks не является списком')
    return homeworks


def parse_status(homework):
    """Извлекает статус проверки домашней работы."""
    if 'homework_name' not in homework:
        raise KeyError('В ответе API отсутствует ключ "homework_name"!')
    if 'status' not in homework:
        raise KeyError('В ответе API отсутствует ключ "status"!')
    homework_name = homework['homework_name']
    homework_status = homework['status']
    if homework_status not in HOMEWORK_VERDICTS:
        error_message = 'Неизвестный статус домашней работы в ответе API'
        logging.error(error_message)
        raise exceptions.UnknownHomeworkStatus(error_message)
    verdict = HOMEWORK_VERDICTS[homework_status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def send_status_message(bot, current_timestamp):
    """Отправляет сообщение о статусе проверки домашней работы в Telegram."""
    response = get_api_answer(current_timestamp)
    homeworks = check_response(response)
    current_timestamp = response.get('current_date', int(time.time()))
    if homeworks:
        homework = homeworks[0]
        timestamp = datetime.fromtimestamp(
            current_timestamp
        ).strftime('%Y-%m-%d %H:%M:%S')
        verdict = parse_status(homework)
        if send_message(bot, f'[{timestamp}] {verdict}'):
            return verdict, True
    return '', False


def send_waiting_message(bot, prev_verdict, prev_verdict_sent):
    """Отправляет сообщение ожидания новой домашней работы в Telegram."""
    status_message = 'Ожидаем проверки новой работы.'
    if not prev_verdict_sent:
        if send_message(bot, status_message):
            return status_message, True
    return prev_verdict, prev_verdict_sent


def send_error_message(bot, error_message, prev_verdict, prev_verdict_sent):
    """Отправляет сообщение об ошибке в Telegram и лог."""
    if error_message != prev_verdict and not prev_verdict_sent:
        send_message(bot, error_message)
        return error_message, True
    return prev_verdict, prev_verdict_sent


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        error_message = 'Отсутствуют переменные окружения!'
        logging.critical(error_message)
        sys.exit('Отсутствуют переменные окружения!')
    bot = Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time())
    prev_verdict = ''
    prev_verdict_sent = False

    while True:
        try:
            verdict, verdict_sent = send_status_message(bot, current_timestamp)
            if verdict_sent:
                prev_verdict = verdict
                prev_verdict_sent = True
                logging.info(f'Статус получен: {verdict}')
                print(f'[INFO] Статус получен: {verdict}')
            else:
                prev_verdict, prev_verdict_sent = send_waiting_message(
                    bot,
                    prev_verdict,
                    prev_verdict_sent
                )
        except Exception as error:
            error_message = f'Сбой в работе бота: {error}'
            logging.error(error_message)
            prev_verdict, prev_verdict_sent = send_error_message(
                bot,
                error_message,
                prev_verdict,
                prev_verdict_sent
            )
            print(f'[ERROR] {error_message}')
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        filename='homework.log',
        format='%(asctime)s: %(levelname)s: %(message)s: %(name)s',
        filemode='w',
        encoding='UTF-8')
    main()
