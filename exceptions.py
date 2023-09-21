class WrongHttpStatus(Exception):
    """Ошибка. HTTP статус != 200."""

    pass


class SendMessageError(Exception):
    """Ошибка отправки сообщения."""

    pass


class UnknownHomeworkStatus(Exception):
    """Ошибка. Неизвестный статус домашней работы."""

    pass


class ResponceKeyError(Exception):
    """Ошибка. В ответе отсутсвует ключ Homeworks."""

    pass
