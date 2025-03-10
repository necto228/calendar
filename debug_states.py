# debug_states.py

"""
Скрипт для отладки зарегистрированных хендлеров в боте.
В новой версии PyTelegramBotAPI (4.10.0+) каждый хендлер в bot.message_handlers — это dict.
Поэтому мы обращаемся к handler['filters'] вместо handler.filters.
"""

from main import bot, setup_webhook

def list_all_handlers():
    """
    Выводит список всех message_handlers, в том числе проверяет, есть ли у них state.
    """
    print("========== СПИСОК ВСЕХ MESSAGE_HANDLERS ==========\n")

    all_handlers = bot.message_handlers  # Список словарей

    for i, handler in enumerate(all_handlers, start=1):
        # handler сам по себе — dict: {'filters': {...}, 'function': ..., ...}
        # Попробуем получить 'filters'
        filters_info = handler.get('filters', {})
        # В filters_info может быть 'state', если это хендлер по состоянию
        state_info = filters_info.get('state', None)

        print(f"Хендлер #{i}:\n  • handler = {handler}")
        print(f"  • filters = {filters_info}")
        print(f"  • state   = {state_info}\n")

    # Ищем только хендлеры со 'state'
    state_handlers = []
    for handler in all_handlers:
        filters_info = handler.get('filters', {})
        state_info = filters_info.get('state', None)
        if state_info is not None:
            state_handlers.append(state_info)

    print("========== СПИСОК ХЕНДЛЕРОВ СО STATE ==========")
    if not state_handlers:
        print("Нет зарегистрированных state-хендлеров.\n")
    else:
        for st in state_handlers:
            print(f"  • Хендлер для состояния: {st}")
    print()

def main():
    """
    Основная функция: вызывает setup_webhook (если нужно), затем выводит список хендлеров.
    """
    # Устанавливаем вебхук (если вы используете вебхук)
    setup_webhook()

    list_all_handlers()

if __name__ == "__main__":
    main()
