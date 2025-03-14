import logging
import telebot
from telebot import types
from telebot.handler_backends import State, StatesGroup
import re
import calendar
from datetime import datetime, date, timedelta
from utils.keyboards import get_client_menu_keyboard, get_start_keyboard, get_confirmation_keyboard

logger = logging.getLogger(__name__)

# Состояния для сценариев клиента
class ClientStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_phone = State()
    selecting_service = State()
    selecting_date = State()
    selecting_time = State()
    confirm_appointment = State()
    rating_service = State()
    writing_review = State()
    rescheduling_select_date = State()
    rescheduling_select_time = State()
    waiting_for_support_question = State()  # Состояние для вопросов поддержке

def register_handlers(bot, sheets_service, logging_service, scheduler_service=None):
    """
    Обработчики, связанные с клиентом:
    - Регистрация по реферальной ссылке
    - Запись на прием
    - Просмотр/управление записями
    """
    logger.info("Регистрируем обработчики клиента")

    @bot.message_handler(func=lambda message: message.text == "👤 Я клиент")
    def client_start(message):
        """
        Если пользователь вручную нажал "👤 Я клиент",
        то ему говорят: для регистрации нужна ссылка от специалиста.
        """
        try:
            bot.send_message(
                message.chat.id,
                "Попросите Вашего специалиста прислать вам прямую (реферальную) ссылку для регистрации.",
                reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add(
                    types.KeyboardButton("🔙 Вернуться в начало")
                )
            )
            # Лог
            user_id = message.from_user.id
            username = message.from_user.username or f"{message.from_user.first_name} {message.from_user.last_name or ''}"
            logging_service.log_message(user_id, username, "Нажал кнопку 'Я клиент'", 'user')
        except Exception as e:
            logger.error(f"Ошибка при нажатии 'Я клиент': {e}", exc_info=True)
            bot.send_message(message.chat.id, "Произошла ошибка. Пожалуйста, попробуйте позже.")

    @bot.message_handler(func=lambda message: message.text and message.text.startswith('/start ref'))
    def register_client_by_ref(message):
        """
        Обработчик, который срабатывает, если пользователь набрал команду вида:
        /start refXXX
        (Например, /start ref2)
        Здесь пользователь проходит регистрацию как клиент конкретного специалиста.
        """
        try:
            logger.info(f"Получена команда с реферальным кодом (client.py): {message.text}")
            user_id = message.from_user.id
            username = message.from_user.username or f"{message.from_user.first_name} {message.from_user.last_name or ''}"

            # Удаляем предыдущее состояние, если было
            try:
                bot.delete_state(user_id, message.chat.id)
            except Exception as e_del:
                logger.warning(f"Ошибка при удалении состояния для /start ref: {e_del}")

            # Извлекаем ref_code
            text_parts = message.text.strip().split()
            if len(text_parts) < 2:
                bot.send_message(message.chat.id, "Неверная реферальная ссылка. Попробуйте снова.")
                return

            ref_part = text_parts[1]  # например, "ref2"
            if not ref_part.startswith("ref"):
                bot.send_message(message.chat.id, "Неверная реферальная ссылка. Попробуйте снова.")
                return

            specialist_id = ref_part[3:]  # убираем "ref"
            if not specialist_id.isdigit():
                bot.send_message(message.chat.id, "Неверная реферальная ссылка (ID не число).")
                return

            # Проверяем, есть ли такой специалист
            specialist = sheets_service.get_specialist_by_id(specialist_id)
            if not specialist:
                bot.send_message(
                    message.chat.id,
                    "Специалист по данной ссылке не найден. Убедитесь, что ссылка верна."
                )
                return

            # Логируем переход
            logging_service.log_message(
                user_id,
                username,
                f"Переход по реферальной ссылке специалиста ID={specialist_id}",
                'user'
            )

            # Устанавливаем состояние "ждем имя клиента"
            bot.set_state(user_id, ClientStates.waiting_for_name, message.chat.id)

            # Сохраняем ID специалиста во временные данные
            with bot.retrieve_data(user_id, message.chat.id) as data:
                data['specialist_id'] = specialist_id
                data['specialist_name'] = specialist.get('Имя', 'Специалист')

            # Запрашиваем имя клиента
            bot.send_message(
                message.chat.id,
                f"Добро пожаловать! Вы перешли по ссылке специалиста {specialist.get('Имя', 'Специалист')}.\n"
                "Для регистрации, пожалуйста, укажите ваше имя:"
            )
        except Exception as e:
            logger.error(f"Ошибка при регистрации клиента по реферальной ссылке: {e}", exc_info=True)
            bot.send_message(message.chat.id, "Произошла ошибка при обработке ссылки. Попробуйте позже.")

    @bot.message_handler(state=ClientStates.waiting_for_name)
    def process_client_name(message):
        """
        Состояние: ждем, что клиент введет свое имя при регистрации.
        """
        try:
            # Проверка на "Вернуться в начало" и т.п.
            if message.text in ["👤 Я клиент", "👨‍⚕️ Я специалист", "🔙 Вернуться в начало"]:
                logger.info(f"Получена системная команда вместо имени: {message.text}")
                if message.text == "🔙 Вернуться в начало":
                    bot.delete_state(message.from_user.id, message.chat.id)
                    from utils.keyboards import get_start_keyboard
                    bot.send_message(
                        message.chat.id,
                        "Вы вернулись в начало. Выберите свою роль:",
                        reply_markup=get_start_keyboard()
                    )
                return

            name = message.text.strip()
            if len(name) < 2:
                bot.send_message(message.chat.id, "Имя должно содержать минимум 2 символа. Введите заново:")
                return

            user_id = message.from_user.id

            with bot.retrieve_data(user_id, message.chat.id) as data:
                data['name'] = name
                if 'specialist_id' not in data:
                    # На всякий случай, если потерялось
                    logger.warning("Отсутствует specialist_id в данных пользователя!")
                    bot.send_message(message.chat.id, "Произошла ошибка: нет информации о специалисте.")
                    bot.delete_state(user_id, message.chat.id)
                    return

            username = message.from_user.username or f"{message.from_user.first_name} {message.from_user.last_name or ''}"
            logger.info(f"process_client_name: Пользователь {user_id} ввел имя {name}")
            # Логируем
            logging_service.log_message(user_id, username, f"Ввел имя клиента: {name}", "user")

            # Переходим к запросу телефона
            bot.set_state(user_id, ClientStates.waiting_for_phone, message.chat.id)
            bot.send_message(
                message.chat.id,
                f"Спасибо, {name}! Укажите ваш номер телефона (или напишите 'Пропустить'):"
            )
        except Exception as e:
            logger.error(f"Ошибка process_client_name: {e}", exc_info=True)
            bot.send_message(message.chat.id, "Произошла ошибка. Попробуйте снова.")
            bot.delete_state(message.from_user.id, message.chat.id)

    @bot.message_handler(state=ClientStates.waiting_for_phone)
    def process_client_phone(message):
        """
        Состояние: ждем, что клиент введет телефон.
        Если 'Пропустить' => телефон будет пустым.
        После этого завершаем регистрацию.
        """
        try:
            text = message.text.strip()
            user_id = message.from_user.id
            username = message.from_user.username or f"{message.from_user.first_name} {message.from_user.last_name or ''}"

            if text.lower() == 'пропустить':
                phone = ''
            else:
                phone = re.sub(r'\D', '', text)
                if len(phone) < 10:
                    bot.send_message(message.chat.id, "Формат номера некорректен. Введите заново или 'Пропустить':")
                    return

            with bot.retrieve_data(user_id, message.chat.id) as data:
                name = data.get('name')
                specialist_id = data.get('specialist_id')

            # Регистрируем клиента в Google Sheets, передавая Telegram ID
            client_id = sheets_service.add_client(name, phone, specialist_id, user_id)
            if not client_id:
                bot.send_message(message.chat.id, "Ошибка при сохранении клиента. Попробуйте позже.")
                bot.delete_state(user_id, message.chat.id)
                return

            # Сброс состояния и показываем меню клиента
            bot.delete_state(user_id, message.chat.id)
            bot.send_message(
                message.chat.id,
                "Отлично! Регистрация завершена. Теперь вы можете записаться на прием!",
                reply_markup=get_client_menu_keyboard()
            )
            # Логируем
            logging_service.log_message(user_id, username, f"Завершена регистрация клиента (ID={client_id})", "system")
        except Exception as e:
            logger.error(f"Ошибка process_client_phone: {e}", exc_info=True)
            bot.send_message(message.chat.id, "Произошла ошибка. Попробуйте снова.")
            bot.delete_state(message.from_user.id, message.chat.id)

    @bot.message_handler(func=lambda message: message.text == "📅 Записаться на прием")
    def book_appointment(message):
        """
        Обработчик кнопки "Записаться на прием" в меню клиента.
        Здесь нужно:
        - проверить, что пользователь действительно клиент
        - показать ему список услуг (если есть)
        - далее ввести логику выбора даты/времени
        """
        try:
            # Проверяем, зарегистрирован ли пользователь как клиент
            client = sheets_service.get_client_by_telegram_id(message.from_user.id)
            if not client:
                # Не клиент -> просим ссылку
                bot.send_message(
                    message.chat.id,
                    "Вы не зарегистрированы как клиент. Пожалуйста, получите реферальную ссылку у специалиста.",
                    reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add(
                        types.KeyboardButton("🔙 Вернуться в начало")
                    )
                )
                return

            # Получаем список услуг
            specialist_id = client['id_специалиста']
            services = sheets_service.get_specialist_services(specialist_id)
            if not services:
                bot.send_message(
                    message.chat.id,
                    "У выбранного специалиста пока нет настроенных услуг. Свяжитесь с ним напрямую.",
                    reply_markup=get_client_menu_keyboard()
                )
                return

            # Формируем кнопки с услугами
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
            for svc in services:
                title = svc.get('Название', 'Без названия')
                dur = svc.get('Продолжительность', 30)
                cost = svc.get('Стоимость', 0)
                button_text = f"{title} ({dur} мин, {cost} руб)"
                markup.add(types.KeyboardButton(button_text))
            markup.add(types.KeyboardButton("🔙 Отмена"))

            # Устанавливаем состояние selecting_service
            bot.set_state(message.from_user.id, ClientStates.selecting_service, message.chat.id)
            with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
                data['client_id'] = client['id']
                data['specialist_id'] = specialist_id
                data['services'] = services

            bot.send_message(
                message.chat.id,
                "Выберите услугу из списка:",
                reply_markup=markup
            )
        except Exception as e:
            logger.error(f"Ошибка при нажатии 'Записаться на прием': {e}", exc_info=True)
            bot.send_message(message.chat.id, "Произошла ошибка. Пожалуйста, попробуйте позже.")

    @bot.message_handler(state=ClientStates.selecting_service)
    def process_service_choice(message):
        try:
            if message.text == "🔙 Отмена":
                # Отмена выбора услуги
                bot.delete_state(message.from_user.id, message.chat.id)
                bot.send_message(message.chat.id, "Действие отменено.", reply_markup=get_client_menu_keyboard())
                return

            service_text = message.text.strip()
            # Ищем выбранную услугу
            with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
                services = data.get('services', [])

            chosen_service = None
            for svc in services:
                title = svc.get('Название', 'Без названия')
                dur = svc.get('Продолжительность', 30)
                cost = svc.get('Стоимость', 0)
                if service_text == f"{title} ({dur} мин, {cost} руб)":
                    chosen_service = svc
                    break

            if not chosen_service:
                bot.send_message(message.chat.id, "Пожалуйста, выберите услугу из списка.")
                return

            # Сохраняем выбранную услугу
            with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
                data['selected_service'] = chosen_service
                data['service_name'] = chosen_service.get('Название', '')
                data['service_duration'] = int(chosen_service.get('Продолжительность', 30))
                data['service_cost'] = int(chosen_service.get('Стоимость', 0))
                specialist_id = data.get('specialist_id')

            # Переходим к выбору даты
            bot.set_state(message.from_user.id, ClientStates.selecting_date, message.chat.id)

            # Формируем календарь на текущий месяц
            today = date.today()
            year, month = today.year, today.month
            create_date_calendar(bot, message.chat.id, year, month, int(chosen_service.get('Продолжительность', 30)), specialist_id, sheets_service, scheduler_service)
        except Exception as e:
            logger.error(f"Ошибка process_service_choice: {e}", exc_info=True)
            bot.send_message(message.chat.id, "Произошла ошибка при выборе услуги. Попробуйте позже.")
            bot.delete_state(message.from_user.id, message.chat.id)

    def create_date_calendar(bot_instance, chat_id, year, month, service_duration=30, specialist_id=None, sheets_service=None, scheduler_service=None):
        """
        Вспомогательная функция для создания календаря с визуальным отображением доступности дней.
        Зеленые дни - есть достаточно свободных слотов для выбранной услуги.
        Красные дни - недостаточно свободных слотов.

        Args:
            service_duration: продолжительность выбранной услуги в минутах
            specialist_id: ID специалиста для проверки доступности
        """
        try:
            keyboard = types.InlineKeyboardMarkup(row_width=7)

            # Кнопки навигации по месяцу
            prev_month = month - 1 if month > 1 else 12
            prev_year = year if month > 1 else year - 1
            next_month = month + 1 if month < 12 else 1
            next_year = year if month < 12 else year + 1

            prev_btn = types.InlineKeyboardButton("<<", callback_data=f"prev_{year}_{month}_{service_duration}")
            next_btn = types.InlineKeyboardButton(">>", callback_data=f"next_{year}_{month}_{service_duration}")

            month_names = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", 
                           "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
            month_label = f"{month_names[month-1]} {year}"
            month_btn = types.InlineKeyboardButton(month_label, callback_data="ignore")

            keyboard.row(prev_btn, month_btn, next_btn)

            # Заголовок дней недели
            days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
            header_buttons = [types.InlineKeyboardButton(day, callback_data="ignore") for day in days]
            keyboard.row(*header_buttons)

            # Проверяем доступные дни для выбранного специалиста
            available_days = {}

            # Получаем информацию о доступности дней
            if specialist_id and sheets_service:
                # Начало и конец месяца
                start_date = datetime(year, month, 1).date()
                if month == 12:
                    end_date = datetime(year + 1, 1, 1).date() - timedelta(days=1)
                else:
                    end_date = datetime(year, month + 1, 1).date() - timedelta(days=1)

                # Для каждого дня в месяце проверяем наличие достаточных слотов
                current_date = start_date
                while current_date <= end_date:
                    date_str = current_date.strftime('%Y-%m-%d')

                    # Получаем все доступные слоты на эту дату
                    available_slots = sheets_service.get_available_slots(specialist_id, date_str)

                    # Проверяем, есть ли достаточно последовательных слотов
                    has_enough_slots = check_consecutive_slots(available_slots, service_duration)
                    available_days[date_str] = has_enough_slots

                    current_date += timedelta(days=1)

            # Получаем календарь на текущий месяц
            cal = calendar.monthcalendar(year, month)

            # Формируем календарь
            today_date = date.today()
            for week in cal:
                row = []
                for day_num in week:
                    if day_num == 0:
                        # Пустая ячейка
                        row.append(types.InlineKeyboardButton(" ", callback_data="ignore"))
                    else:
                        # Проверяем, не прошедшая ли это дата
                        current_date = date(year, month, day_num)
                        date_str = current_date.strftime('%Y-%m-%d')

                        if current_date < today_date:
                            # Прошедшая дата - неактивная
                            row.append(types.InlineKeyboardButton(str(day_num), callback_data="ignore"))
                        else:
                            # Определяем доступность слотов
                            is_available = available_days.get(date_str, False)

                            # Формируем текст кнопки с эмодзи
                            btn_text = f"🟢{day_num}" if is_available else f"🔴{day_num}"

                            # Для активных дней формируем callback_data
                            if is_available:
                                callback_data = f"bookdate_{year}_{month}_{day_num}"
                                row.append(types.InlineKeyboardButton(btn_text, callback_data=callback_data))
                            else:
                                # Для недоступных дней указываем специальный callback
                                row.append(types.InlineKeyboardButton(btn_text, callback_data="no_slots"))
                keyboard.row(*row)

            # Кнопка отмены
            keyboard.add(types.InlineKeyboardButton("Отмена", callback_data="cancel"))

            bot_instance.send_message(
                chat_id, 
                "Выберите удобную дату: 🟢 - доступное время, 🔴 - нет доступного времени", 
                reply_markup=keyboard
            )
        except Exception as e:
            logger.error(f"Ошибка в create_date_calendar: {e}", exc_info=True)
            bot_instance.send_message(chat_id, "Произошла ошибка при формировании календаря. Пожалуйста, попробуйте позже.")

    def normalize_date(date_str):
        """
        Нормализует строку даты, удаляя лишние пробелы и символы переноса строки.
        """
        if not date_str:
            return ""
        return date_str.strip()

                def check_consecutive_slots(slots, service_duration):
        """
        Проверяет, есть ли достаточно последовательных свободных слотов
        для услуги указанной продолжительности.

        Args:
            slots: список доступных слотов
            service_duration: продолжительность услуги в минутах

        Returns:
            bool: True если есть достаточно слотов, иначе False
        """
        import logging
        logger = logging.getLogger(__name__)

        if not slots:
            logger.debug(f"check_consecutive_slots: нет слотов")
            return False

        # Преобразуем список слотов в минуты от начала дня для проверки последовательности
        slots_by_time = []
        for slot in slots:
            try:
                time_str = slot.get('Время', '').strip()
                if not time_str:
                    continue

                h, m = map(int, time_str.split(':'))
                time_val = h*60 + m
                slots_by_time.append((time_val, slot.get('id')))
            except (ValueError, KeyError, AttributeError) as e:
                logger.warning(f"Ошибка с форматом времени слота: {e}")
                continue

        # Необходимое количество последовательных слотов (30 мин каждый)
        slot_count = max(1, (service_duration + 29) // 30)  # Округление вверх

        logger.debug(f"check_consecutive_slots: требуется {slot_count} последовательных слотов для {service_duration} минут")

        # Если не хватает слотов в принципе
        if len(slots_by_time) < slot_count:
            logger.debug(f"check_consecutive_slots: недостаточно слотов ({len(slots_by_time)} < {slot_count})")
            return False

        # Сортируем слоты по времени
        slots_by_time.sort()

        # Выводим первые несколько слотов для отладки
        if len(slots_by_time) > 0:
            debug_times = ", ".join([f"{t//60}:{t%60:02d}" for t, _ in slots_by_time[:5]])
            logger.debug(f"check_consecutive_slots: первые слоты: {debug_times}")

        # Ищем последовательные слоты достаточной длительности
        for i in range(len(slots_by_time) - slot_count + 1):
            contiguous = True

            for j in range(1, slot_count):
                prev_time = slots_by_time[i+j-1][0]
                curr_time = slots_by_time[i+j][0]

                # Проверяем, что слоты идут последовательно (с шагом 30 мин)
                if curr_time - prev_time != 30:
                    contiguous = False
                    logger.debug(f"check_consecutive_slots: разрыв между {prev_time//60}:{prev_time%60:02d} и {curr_time//60}:{curr_time%60:02d}")
                    break

            if contiguous:
                start_time = slots_by_time[i][0]
                end_time = slots_by_time[i+slot_count-1][0] + 30
                logger.debug(f"check_consecutive_slots: найдены последовательные слоты с {start_time//60}:{start_time%60:02d} до {end_time//60}:{end_time%60:02d}")
                return True

        logger.debug(f"check_consecutive_slots: не найдено {slot_count} последовательных слотов")
        return False

        Args:
            slots: список доступных слотов
            service_duration: продолжительность услуги в минутах

        Returns:
            bool: True если есть достаточно слотов, иначе False
        """
        import logging
        logger = logging.getLogger(__name__)

        if not slots:
            logger.debug(f"check_consecutive_slots: нет слотов")
            return False

        # Преобразуем список слотов в минуты от начала дня для проверки последовательности
        slots_by_time = []
        for slot in slots:
            try:
                time_str = slot.get('Время', '').strip()
                if not time_str:
                    continue

                h, m = map(int, time_str.split(':'))
                time_val = h*60 + m
                slots_by_time.append((time_val, slot.get('id')))
            except (ValueError, KeyError, AttributeError) as e:
                logger.warning(f"Ошибка с форматом времени слота: {e}")
                continue

        # Необходимое количество последовательных слотов (30 мин каждый)
        slot_count = max(1, (service_duration + 29) // 30)  # Округление вверх

        logger.debug(f"check_consecutive_slots: требуется {slot_count} последовательных слотов для {service_duration} минут")

        # Если не хватает слотов в принципе
        if len(slots_by_time) < slot_count:
            logger.debug(f"check_consecutive_slots: недостаточно слотов ({len(slots_by_time)} < {slot_count})")
            return False

        # Сортируем слоты по времени
        slots_by_time.sort()

        # Выводим первые несколько слотов для отладки
        if len(slots_by_time) > 0:
            debug_times = ", ".join([f"{t//60}:{t%60:02d}" for t, _ in slots_by_time[:5]])
            logger.debug(f"check_consecutive_slots: первые слоты: {debug_times}")

        # Ищем последовательные слоты достаточной длительности
        for i in range(len(slots_by_time) - slot_count + 1):
            contiguous = True

            for j in range(1, slot_count):
                prev_time = slots_by_time[i+j-1][0]
                curr_time = slots_by_time[i+j][0]

                # Проверяем, что слоты идут последовательно (с шагом 30 мин)
                if curr_time - prev_time != 30:
                    contiguous = False
                    logger.debug(f"check_consecutive_slots: разрыв между {prev_time//60}:{prev_time%60:02d} и {curr_time//60}:{curr_time%60:02d}")
                    break

            if contiguous:
                start_time = slots_by_time[i][0]
                end_time = slots_by_time[i+slot_count-1][0] + 30
                logger.debug(f"check_consecutive_slots: найдены последовательные слоты с {start_time//60}:{start_time%60:02d} до {end_time//60}:{end_time%60:02d}")
                return True

        logger.debug(f"check_consecutive_slots: не найдено {slot_count} последовательных слотов")
        return False


        Args:
            slots: список доступных слотов
            service_duration: продолжительность услуги в минутах

        Returns:
            bool: True если есть достаточно слотов, иначе False
        """
        import logging
        logger = logging.getLogger(__name__)

        if not slots:
            logger.debug(f"check_consecutive_slots: нет слотов")
            return False

        # Преобразуем список слотов в минуты от начала дня для проверки последовательности
        slots_by_time = []
        for slot in slots:
            try:
                time_str = slot.get('Время', '').strip()
                if not time_str:
                    continue

                h, m = map(int, time_str.split(':'))
                time_val = h*60 + m
                slots_by_time.append((time_val, slot.get('id')))
            except (ValueError, KeyError, AttributeError) as e:
                logger.warning(f"Ошибка с форматом времени слота: {e}")
                continue

        # Необходимое количество последовательных слотов (30 мин каждый)
        slot_count = max(1, (service_duration + 29) // 30)  # Округление вверх

        logger.debug(f"check_consecutive_slots: требуется {slot_count} последовательных слотов для {service_duration} минут")

        # Если не хватает слотов в принципе
        if len(slots_by_time) < slot_count:
            logger.debug(f"check_consecutive_slots: недостаточно слотов ({len(slots_by_time)} < {slot_count})")
            return False

        # Сортируем слоты по времени
        slots_by_time.sort()

        # Выводим первые несколько слотов для отладки
        if len(slots_by_time) > 0:
            debug_times = ", ".join([f"{t//60}:{t%60:02d}" for t, _ in slots_by_time[:5]])
            logger.debug(f"check_consecutive_slots: первые слоты: {debug_times}")

        # Ищем последовательные слоты достаточной длительности
        for i in range(len(slots_by_time) - slot_count + 1):
            contiguous = True

            for j in range(1, slot_count):
                prev_time = slots_by_time[i+j-1][0]
                curr_time = slots_by_time[i+j][0]

                # Проверяем, что слоты идут последовательно (с шагом 30 мин)
                if curr_time - prev_time != 30:
                    contiguous = False
                    logger.debug(f"check_consecutive_slots: разрыв между {prev_time//60}:{prev_time%60:02d} и {curr_time//60}:{curr_time%60:02d}")
                    break

            if contiguous:
                start_time = slots_by_time[i][0]
                end_time = slots_by_time[i+slot_count-1][0] + 30
                logger.debug(f"check_consecutive_slots: найдены последовательные слоты с {start_time//60}:{start_time%60:02d} до {end_time//60}:{end_time%60:02d}")
                return True

        logger.debug(f"check_consecutive_slots: не найдено {slot_count} последовательных слотов")
        return False

    @bot.callback_query_handler(func=lambda call: call.data == "no_slots")
    def no_available_slots(call):
        """Обработчик нажатия на неактивные даты"""
        bot.answer_callback_query(call.id, "На эту дату нет доступного времени для выбранной услуги", show_alert=True)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("prev_") or call.data.startswith("next_"), 
                              state=[ClientStates.selecting_date, ClientStates.rescheduling_select_date])
    def calendar_nav(call):
        try:
            parts = call.data.split('_')
            direction = parts[0]
            year = int(parts[1])
            month = int(parts[2])
            service_duration = 30

            # Если передана длительность услуги, используем её
            if len(parts) > 3 and parts[3].isdigit():
                service_duration = int(parts[3])

            if direction == 'prev':
                new_month = month - 1 if month > 1 else 12
                new_year = year if month > 1 else year - 1
            else:
                new_month = month + 1 if month < 12 else 1
                new_year = year if month < 12 else year + 1

            # Получаем данные для формирования календаря
            user_id = call.from_user.id
            chat_id = call.message.chat.id
            state = bot.get_state(user_id, chat_id)

            # Получаем ID специалиста
            specialist_id = None
            with bot.retrieve_data(user_id, chat_id) as data:
                specialist_id = data.get('specialist_id')

            # Удаляем предыдущее сообщение с календарём
            try:
                bot.delete_message(chat_id, call.message.message_id)
            except Exception as e_del:
                logger.warning(f"Не удалось удалить сообщение календаря: {e_del}")

            # Формируем новый календарь
            if state == "ClientStates.selecting_date":
                create_date_calendar(bot, chat_id, new_year, new_month, service_duration, specialist_id, sheets_service, scheduler_service)
            else:
                # Для переноса записи
                create_date_calendar(bot, chat_id, new_year, new_month, service_duration, specialist_id, sheets_service, scheduler_service)

            bot.answer_callback_query(call.id)
        except Exception as e:
            logger.error(f"Ошибка в листании календаря: {e}", exc_info=True)
            bot.answer_callback_query(call.id, text="Ошибка при обновлении календаря")

    @bot.callback_query_handler(func=lambda call: call.data.startswith("bookdate_"), state=ClientStates.selecting_date)
    def select_date(call):
        try:
            _, year, month, day = call.data.split('_')
            year, month, day = int(year), int(month), int(day)
            date_str = f"{year}-{month:02d}-{day:02d}"
            user_id = call.from_user.id
            chat_id = call.message.chat.id

            # Получаем данные клиента и специалиста из состояния
            with bot.retrieve_data(user_id, chat_id) as data:
                specialist_id = data.get('specialist_id')
                service_duration = data.get('service_duration', 30)

            # Нормализуем дату для корректного сравнения
            date_str = normalize_date(date_str)

            # Получаем свободные слоты на эту дату
            available_slots = sheets_service.get_available_slots(specialist_id, date_str)

            # Проверяем наличие последовательных слотов для услуги
            has_slots = check_consecutive_slots(available_slots, service_duration)
            if not has_slots:
                bot.answer_callback_query(call.id, text="Нет подходящих интервалов времени для выбранной услуги")
                return

            # Используем SchedulerService если он доступен
            if scheduler_service:
                times = scheduler_service.get_available_times(specialist_id, date_str, service_duration)
                if not times:
                    bot.answer_callback_query(call.id, text="Нет подходящих интервалов времени для выбранной услуги")
                    return

                # Убираем сообщение с календарем
                try:
                    bot.delete_message(chat_id, call.message.message_id)
                except Exception as e_del:
                    logger.warning(f"Не удалось удалить сообщение календаря: {e_del}")

                # Переходим к выбору времени
                bot.set_state(user_id, ClientStates.selecting_time, chat_id)

                # Сохраняем выбранную дату
                with bot.retrieve_data(user_id, chat_id) as data:
                    data['selected_date'] = date_str

                    # Форматируем дату для отображения
                    try:
                        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                        data['formatted_date'] = date_obj.strftime('%d.%m.%Y')
                    except:
                        data['formatted_date'] = date_str

                # Отправляем варианты времени
                keyboard = types.InlineKeyboardMarkup()
                for time_str in times:
                    keyboard.add(types.InlineKeyboardButton(time_str, callback_data=f"booktime_{time_str}"))
                keyboard.add(types.InlineKeyboardButton("Отмена", callback_data="cancel"))

                bot.send_message(chat_id, "Выберите удобное время:", reply_markup=keyboard)
                bot.answer_callback_query(call.id)
                return

            # Если SchedulerService не доступен, используем старую логику
            # Подбираем слоты с учетом длительности услуги
            slot_count = max(1, (service_duration + 29) // 30)  # Округление вверх

            # Составляем список слотов (в минутах от начала дня)
            slots_by_time = []
            for slot in available_slots:
                try:
                    h, m = map(int, slot['Время'].split(':'))
                    time_val = h*60 + m
                    slots_by_time.append((time_val, slot['id']))
                except (ValueError, KeyError) as e:
                    logger.warning(f"Ошибка с форматом времени слота: {e}")
                    continue

            slots_by_time.sort()

            # Ищем последовательные слоты достаточной длительности
            options = []
            for i in range(len(slots_by_time) - slot_count + 1):
                seq = [slots_by_time[i]]
                contiguous = True
                for j in range(1, slot_count):
                    if i+j >= len(slots_by_time):
                        contiguous = False
                        break
                    prev_time = slots_by_time[i+j-1][0]
                    curr_time = slots_by_time[i+j][0]
                    diff = curr_time - prev_time
                    if diff != 30:
                        contiguous = False
                        break

                if contiguous:
                    seq_ids = [slots_by_time[i+k][1] for k in range(slot_count)]
                    start_minutes = slots_by_time[i][0]
                    end_minutes = start_minutes + service_duration
                    start_h = start_minutes // 60
                    start_m = start_minutes % 60
                    end_h = end_minutes // 60
                    end_m = end_minutes % 60
                    start_time_str = f"{start_h:02d}:{start_m:02d}"
                    end_time_str = f"{end_h:02d}:{end_m:02d}"
                    label = f"{start_time_str}" if slot_count == 1 else f"{start_time_str}-{end_time_str}"
                    options.append((label, seq_ids))

            if not options:
                bot.answer_callback_query(call.id, text="Нет свободных времен для выбранной услуги")
                return

            # Убираем сообщение с календарем
            try:
                bot.delete_message(chat_id, call.message.message_id)
            except Exception as e_del:
                logger.warning(f"Не удалось удалить сообщение календаря: {e_del}")

            # Переходим к выбору времени
            bot.set_state(user_id, ClientStates.selecting_time, chat_id)

            # Сохраняем варианты слотов и выбранную дату
            with bot.retrieve_data(user_id, chat_id) as data:
                data['booking_options'] = {str(ids[0]): ids for _, ids in options}
                data['selected_date'] = date_str

                # Форматируем дату для отображения
                try:
                    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                    data['formatted_date'] = date_obj.strftime('%d.%m.%Y')
                except:
                    data['formatted_date'] = date_str

            # Отправляем варианты времени
            keyboard = types.InlineKeyboardMarkup()
            for label, seq_ids in options:
                first_id = seq_ids[0]
                keyboard.add(types.InlineKeyboardButton(label, callback_data=f"booktime_{first_id}"))
            keyboard.add(types.InlineKeyboardButton("Отмена", callback_data="cancel"))

            bot.send_message(chat_id, "Выберите удобное время:", reply_markup=keyboard)
            bot.answer_callback_query(call.id)
            return
        except Exception as e:
            logger.error(f"Ошибка при выборе даты: {e}", exc_info=True)
            bot.answer_callback_query(call.id, text="Ошибка при выборе даты")
    @bot.callback_query_handler(func=lambda call: call.data.startswith("booktime_"), state=ClientStates.selecting_time)
    def select_time(call):
        try:
            time_data = call.data.split('_')[1]
            user_id = call.from_user.id
            chat_id = call.message.chat.id

            with bot.retrieve_data(user_id, chat_id) as data:
                specialist_id = data.get('specialist_id')
                service_name = data.get('service_name', '')
                service_cost = data.get('service_cost', 0)
                service_duration = data.get('service_duration', 30)
                selected_date = data.get('selected_date', '')

                # Форматируем дату для отображения если не было сделано раньше
                if 'formatted_date' not in data:
                    try:
                        date_obj = datetime.strptime(selected_date, '%Y-%m-%d')
                        data['formatted_date'] = date_obj.strftime('%d.%m.%Y')
                    except:
                        data['formatted_date'] = selected_date

                formatted_date = data.get('formatted_date', selected_date)

            # Определяем слоты для бронирования
            if scheduler_service and ':' in time_data:  # Строка времени вида "09:00"
                # Используем SchedulerService для получения IDs слотов
                slot_ids = scheduler_service.get_slot_ids_for_booking(
                    specialist_id, selected_date, time_data, service_duration
                )
                start_time = time_data
            else:  # ID первого слота
                # Используем старую логику
                booking_options = data.get('booking_options', {})
                slot_ids = booking_options.get(time_data, [time_data])

                # Определяем время начала
                all_slots = sheets_service.schedule_sheet.get_all_records()
                start_time = None
                for slot in all_slots:
                    if str(slot.get('id')) == str(slot_ids[0]):
                        start_time = slot.get('Время')
                        break
                start_time = start_time or ''

            # Формируем текст подтверждения
            confirm_text = (
                f"Вы выбрали запись на {service_name} ("
                f"{service_duration} мин) на {formatted_date} в {start_time}. "
                f"Стоимость: {service_cost} руб. Подтвердите запись:"
            )

            # Переходим в состояние подтверждения
            bot.set_state(user_id, ClientStates.confirm_appointment, chat_id)

            # Создаем клавиатуру подтверждения
            keyboard = get_confirmation_keyboard()

            # Заменяем сообщение с выбором времени на сообщение подтверждения
            bot.edit_message_text(confirm_text, chat_id, call.message.message_id, reply_markup=keyboard)

            # Сохраняем данные для бронирования
            with bot.retrieve_data(user_id, chat_id) as data:
                data['slots_to_book'] = slot_ids
                data['start_time'] = start_time
        except Exception as e:
            logger.error(f"Ошибка выбора времени: {e}", exc_info=True)
            bot.answer_callback_query(call.id, text="Ошибка при выборе времени")

    @bot.callback_query_handler(func=lambda call: call.data == "confirm", state=ClientStates.confirm_appointment)
    def confirm_appointment(call):
        try:
            user_id = call.from_user.id
            chat_id = call.message.chat.id

            with bot.retrieve_data(user_id, chat_id) as data:
                slot_ids = data.get('slots_to_book', [])
                service_name = data.get('service_name', '')
                service_cost = data.get('service_cost', 0)
                service_duration = data.get('service_duration', 30)
                selected_date = data.get('selected_date', '')
                start_time = data.get('start_time', '')
                formatted_date = data.get('formatted_date', selected_date)

            client = sheets_service.get_client_by_telegram_id(user_id)
            client_id = client['id'] if client else None
            specialist_id = client['id_специалиста'] if client else None

            if not slot_ids or not client_id:
                bot.answer_callback_query(call.id, "Данные для бронирования отсутствуют")
                return

            # Бронируем все слоты
            success = True
            booked = []
            for sid in slot_ids:
                res = sheets_service.book_appointment(sid, client_id)
                if res:
                    booked.append(sid)
                else:
                    success = False
                    break

            if not success:
                # Откатываем, если частично получилось
                for sid in booked:
                    sheets_service.cancel_appointment(sid)
                bot.edit_message_text("Произошла ошибка при бронировании. Попробуйте снова.", chat_id, call.message.message_id)
                bot.delete_state(user_id, chat_id)
            else:
                # Успешное бронирование
                success_message = (
                    f"Отлично! Вы записаны на {service_name} на {formatted_date} в {start_time}. "
                    f"За 24 часа до приема я пришлю напоминание."
                )
                bot.edit_message_text(success_message, chat_id, call.message.message_id)
                bot.send_message(
                    chat_id,
                    "Вы можете управлять своими записями через меню 'Мои записи'.",
                    reply_markup=get_client_menu_keyboard()
                )
                bot.delete_state(user_id, chat_id)

                # Отправляем уведомление специалисту
                if specialist_id:
                    specialist = sheets_service.get_specialist_by_id(specialist_id)
                    if specialist and specialist.get('Telegram_ID'):
                        try:
                            specialist_telegram_id = specialist.get('Telegram_ID')
                            notification_text = (
                                f"Новая запись!\n"
                                f"Клиент: {client.get('Имя', 'Клиент')}\n"
                                f"Услуга: {service_name}\n"
                                f"Дата: {formatted_date}\n"
                                f"Время: {start_time}\n"
                                f"Телефон: {client.get('Телефон', 'Не указан')}"
                            )
                            bot.send_message(specialist_telegram_id, notification_text)
                        except Exception as notify_err:
                            logger.error(f"Ошибка при отправке уведомления специалисту: {notify_err}")

                # Создаем запись о напоминании
                appt_id = slot_ids[0]  # Используем ID первого слота для напоминаний
                # Если есть scheduler_service, используем его для создания напоминания
                if scheduler_service:
                    try:
                        reminder_id = scheduler_service.add_reminder(
                            appt_id, client_id, selected_date, start_time, "pending", 
                            specialist_id, service_name
                        )
                        logger.info(f"Создано напоминание ID={reminder_id} для записи ID={appt_id}")
                    except:
                        # Пробуем использовать метод sheets_service как запасной вариант
                        sheets_service.add_reminder(appt_id, client_id, selected_date, start_time, "pending")
                else:
                    # Используем метод sheets_service
                    try:
                        sheets_service.add_reminder(appt_id, client_id, selected_date, start_time, "pending")
                    except Exception as reminder_err:
                        logger.error(f"Ошибка при добавлении напоминания: {reminder_err}")

        except Exception as e:
            logger.error(f"Ошибка подтверждения записи: {e}", exc_info=True)
            bot.answer_callback_query(call.id, "Ошибка при подтверждении записи")
            bot.delete_state(call.from_user.id, call.message.chat.id)

    @bot.callback_query_handler(func=lambda call: call.data == "cancel_booking", state=ClientStates.confirm_appointment)
    def cancel_booking(call):
        """Отмена бронирования на этапе подтверждения"""
        try:
            bot.edit_message_text("Бронирование отменено.", call.message.chat.id, call.message.message_id)
            bot.send_message(call.message.chat.id, "Вы можете выбрать другое время или услугу.",
                           reply_markup=get_client_menu_keyboard())
            bot.delete_state(call.from_user.id, call.message.chat.id)
        except Exception as e:
            logger.error(f"Ошибка cancel_booking: {e}", exc_info=True)
            bot.answer_callback_query(call.id, "Ошибка при отмене бронирования")
            bot.delete_state(call.from_user.id, call.message.chat.id)

    @bot.message_handler(func=lambda message: message.text == "🔍 Мои записи")
    def view_appointments(message):
        """
        Обработчик кнопки "Мои записи" для клиента.
        Показывает список всех записей, если есть.
        """
        try:
            client = sheets_service.get_client_by_telegram_id(message.from_user.id)
            if not client:
                bot.send_message(
                    message.chat.id,
                    "Вы не зарегистрированы как клиент. Пожалуйста, получите ссылку от специалиста.",
                    reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add(
                        types.KeyboardButton("🔙 Вернуться в начало")
                    )
                )
                return

            appointments = sheets_service.get_client_appointments(client['id'])
            if not appointments:
                bot.send_message(
                    message.chat.id,
                    "У вас нет активных записей.",
                    reply_markup=get_client_menu_keyboard()
                )
                return

            # Сортируем записи по дате и времени
            appointments.sort(key=lambda a: (a['Дата'], a['Время']))

            text = "Ваши записи:\n"
            for i, appt in enumerate(appointments, start=1):
                # Форматируем дату
                try:
                    date_obj = datetime.strptime(appt['Дата'], '%Y-%m-%d')
                    formatted_date = date_obj.strftime('%d.%m.%Y')
                except:
                    formatted_date = appt['Дата']

                text += f"{i}. {formatted_date} в {appt['Время']}\n"

            keyboard = types.InlineKeyboardMarkup()
            for i, appt in enumerate(appointments, start=1):
                slot_id = appt['id']
                keyboard.row(
                    types.InlineKeyboardButton(f"✏️ {i}", callback_data=f"reschedappt_{slot_id}"),
                    types.InlineKeyboardButton(f"❌ {i}", callback_data=f"cancelappt_{slot_id}")
                )
            keyboard.add(types.InlineKeyboardButton("🔙 Назад", callback_data="cancel"))

            # Сохраняем данные о записях для последующей обработки
            with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
                data['appointments'] = appointments
                data['appointments_text'] = text

            bot.send_message(message.chat.id, text, reply_markup=keyboard)
        except Exception as e:
            logger.error(f"Ошибка при нажатии 'Мои записи': {e}", exc_info=True)
            bot.send_message(message.chat.id, "Произошла ошибка. Пожалуйста, попробуйте позже.")

    @bot.callback_query_handler(func=lambda call: call.data.startswith("cancelappt_"))
    def cancel_appointment_request(call):
        try:
            slot_id = call.data.split('_')[1]
            user_id = call.from_user.id
            chat_id = call.message.chat.id

            # Получаем данные о записи
            with bot.retrieve_data(user_id, chat_id) as data:
                appointments = data.get('appointments', [])

            appt = None
            for a in appointments:
                if str(a.get('id')) == str(slot_id):
                    appt = a
                    break

            if not appt:
                bot.answer_callback_query(call.id, "Запись не найдена.")
                return

            # Форматируем дату
            try:
                date_obj = datetime.strptime(appt['Дата'], '%Y-%m-%d')
                formatted_date = date_obj.strftime('%d.%m.%Y')
            except:
                formatted_date = appt['Дата']

            date_str = formatted_date
            time_str = appt['Время']

            # Скрываем клавиатуру у предыдущего сообщения
            try:
                bot.edit_message_reply_markup(chat_id, call.message.message_id)
            except Exception as e_edit:
                logger.warning(f"Не удалось скрыть клавиатуру: {e_edit}")

            # Создаем клавиатуру подтверждения отмены
            keyboard = types.InlineKeyboardMarkup()
            keyboard.row(
                types.InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirmcancel_{slot_id}"),
                types.InlineKeyboardButton("❌ Отменить", callback_data="cancelcancel")
            )

            # Отправляем запрос на подтверждение отмены
            bot.send_message(chat_id, f"Вы уверены, что хотите отменить запись на {date_str} в {time_str}?", reply_markup=keyboard)

            # Сохраняем ID сообщения со списком записей
            with bot.retrieve_data(user_id, chat_id) as data:
                data['appointments_message_id'] = call.message.message_id
        except Exception as e:
            logger.error(f"Ошибка cancel_appointment_request: {e}", exc_info=True)
            bot.answer_callback_query(call.id, "Ошибка обработки запроса.")

    @bot.callback_query_handler(func=lambda call: call.data.startswith("confirmcancel_"))
    def confirm_cancel_appointment(call):
        try:
            slot_id = call.data.split('_')[1]
            user_id = call.from_user.id
            chat_id = call.message.chat.id

            # Получаем данные о записи для уведомления специалиста
            client = sheets_service.get_client_by_telegram_id(user_id)
            if not client:
                bot.answer_callback_query(call.id, "Клиент не найден.")
                return

            # Получаем информацию о записи перед отменой
            all_slots = sheets_service.schedule_sheet.get_all_records()
            appointment_info = None
            specialist_id = None

            for slot in all_slots:
                if str(slot.get('id')) == str(slot_id):
                    appointment_info = slot
                    specialist_id = slot.get('id_специалиста')
                    break

            # Отменяем запись
            success = sheets_service.cancel_appointment(slot_id)
            if not success:
                bot.answer_callback_query(call.id, "Не удалось отменить запись.")
                return

            # Отправляем уведомление специалисту
            if appointment_info and specialist_id:
                specialist = sheets_service.get_specialist_by_id(specialist_id)
                if specialist and specialist.get('Telegram_ID'):
                    try:
                        # Форматируем дату для красивого отображения
                        date_str = appointment_info['Дата']
                        try:
                            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                            formatted_date = date_obj.strftime('%d.%m.%Y')
                        except:
                            formatted_date = date_str

                        time_str = appointment_info['Время']
                        specialist_telegram_id = specialist.get('Telegram_ID')

                        notification_text = (
                            f"Отмена записи!\n"
                            f"Клиент {client.get('Имя', 'Клиент')} отменил запись на {formatted_date} в {time_str}.\n"
                            f"Слот снова доступен для записи."
                        )
                        bot.send_message(specialist_telegram_id, notification_text)
                    except Exception as notify_err:
                        logger.error(f"Ошибка при отправке уведомления специалисту: {notify_err}")

            # Получаем обновленный список записей
            appointments = sheets_service.get_client_appointments(client['id'])

            # Если есть записи - обновляем сообщение со списком
            if appointments:
                # Сортируем записи по дате и времени
                appointments.sort(key=lambda a: (a['Дата'], a['Время']))

                text = "Ваши записи:\n"
                for i, appt in enumerate(appointments, start=1):
                    # Форматируем дату
                    try:
                        date_obj = datetime.strptime(appt['Дата'], '%Y-%m-%d')
                        formatted_date = date_obj.strftime('%d.%m.%Y')
                    except:
                        formatted_date = appt['Дата']

                    text += f"{i}. {formatted_date} в {appt['Время']}\n"

                keyboard = types.InlineKeyboardMarkup()
                for i, appt in enumerate(appointments, start=1):
                    appt_id = appt['id']
                    keyboard.row(
                        types.InlineKeyboardButton(f"✏️ {i}", callback_data=f"reschedappt_{appt_id}"),
                        types.InlineKeyboardButton(f"❌ {i}", callback_data=f"cancelappt_{appt_id}")
                    )
                keyboard.add(types.InlineKeyboardButton("🔙 Назад", callback_data="cancel"))

                # Обновляем сообщение со списком записей, если можем
                with bot.retrieve_data(user_id, chat_id) as data:
                    orig_msg_id = data.get('appointments_message_id')

                if orig_msg_id:
                    try:
                        bot.edit_message_text(text, chat_id, orig_msg_id, reply_markup=keyboard)
                    except Exception as e_edit:
                        # Если не можем отредактировать - отправляем новое сообщение
                        bot.send_message(chat_id, text, reply_markup=keyboard)
                else:
                    bot.send_message(chat_id, text, reply_markup=keyboard)

                # Обновляем данные о записях
                with bot.retrieve_data(user_id, chat_id) as data:
                    data['appointments'] = appointments
                    data['appointments_text'] = text
            else:
                # Если записей не осталось - сообщаем об этом
                bot.send_message(chat_id, "У вас нет активных записей.", reply_markup=get_client_menu_keyboard())

            # Удаляем сообщение с подтверждением отмены
            try:
                bot.edit_message_text("Запись успешно отменена.", chat_id, call.message.message_id)
            except Exception as e:
                logger.warning(f"Не удалось обновить сообщение подтверждения: {e}")
        except Exception as e:
            logger.error(f"Ошибка confirm_cancel_appointment: {e}", exc_info=True)
            bot.answer_callback_query(call.id, "Ошибка при отмене записи.")

    @bot.callback_query_handler(func=lambda call: call.data == "cancelcancel")
    def cancel_cancel_request(call):
        try:
            user_id = call.from_user.id
            chat_id = call.message.chat.id

            # Получаем данные о записях
            with bot.retrieve_data(user_id, chat_id) as data:
                appointments = data.get('appointments', [])
                orig_msg_id = data.get('appointments_message_id')
                original_text = data.get('appointments_text', "Ваши записи:\n")

            if not appointments or not orig_msg_id:
                bot.answer_callback_query(call.id, "Данные записей не найдены.")
                return

            # Восстанавливаем клавиатуру в сообщении со списком записей
            keyboard = types.InlineKeyboardMarkup()
            for i, appt in enumerate(appointments, start=1):
                sid = appt['id']
                keyboard.row(
                    types.InlineKeyboardButton(f"✏️ {i}", callback_data=f"reschedappt_{sid}"),
                    types.InlineKeyboardButton(f"❌ {i}", callback_data=f"cancelappt_{sid}")
                )
            keyboard.add(types.InlineKeyboardButton("🔙 Назад", callback_data="cancel"))

            # Обновляем сообщение со списком записей
            try:
                bot.edit_message_reply_markup(chat_id, orig_msg_id, reply_markup=keyboard)
            except Exception as e:
                logger.warning(f"Не удалось восстановить клавиатуру: {e}")

            # Удаляем сообщение с запросом подтверждения
            try:
                bot.delete_message(chat_id, call.message.message_id)
            except Exception as e:
                logger.warning(f"Не удалось удалить сообщение: {e}")
                bot.edit_message_text("Действие отменено.", chat_id, call.message.message_id)
        except Exception as e:
            logger.error(f"Ошибка cancel_cancel_request: {e}", exc_info=True)
            bot.answer_callback_query(call.id, "Ошибка.")

    @bot.callback_query_handler(func=lambda call: call.data.startswith("reschedappt_"))
    def reschedule_appointment_request(call):
        """
        Выбор или отмена выбора конкретной даты
        """
        try:
            slot_id = call.data.split('_')[1]
            user_id = call.from_user.id
            chat_id = call.message.chat.id

            # Получаем данные о записи
            with bot.retrieve_data(user_id, chat_id) as data:
                appointments = data.get('appointments', [])

            appt = None
            for a in appointments:
                if str(a.get('id')) == str(slot_id):
                    appt = a
                    break

            if not appt:
                bot.answer_callback_query(call.id, "Запись не найдена.")
                return

            # Форматируем дату
            try:
                date_obj = datetime.strptime(appt['Дата'], '%Y-%m-%d')
                formatted_date = date_obj.strftime('%d.%m.%Y')
            except:
                formatted_date = appt['Дата']

            # Получаем данные о клиенте
            client = sheets_service.get_client_by_telegram_id(user_id)
            if not client:
                bot.answer_callback_query(call.id, "Клиент не найден.")
                return

            # Скрываем клавиатуру у предыдущего сообщения
            try:
                bot.edit_message_reply_markup(chat_id, call.message.message_id)
            except Exception as e_edit:
                logger.warning(f"Не удалось скрыть клавиатуру: {e_edit}")

            # Сохраняем данные для переноса
            with bot.retrieve_data(user_id, chat_id) as data:
                data['reschedule_slot_id'] = slot_id
                data['reschedule_date'] = appt['Дата']
                data['reschedule_time'] = appt['Время']
                data['reschedule_formatted_date'] = formatted_date
                data['specialist_id'] = appt['id_специалиста']
                data['appointments_message_id'] = call.message.message_id

            # Переходим к выбору новой даты
            bot.set_state(user_id, ClientStates.rescheduling_select_date, chat_id)

            # Отправляем сообщение о переносе
            bot.send_message(
                chat_id, 
                f"Вы хотите перенести запись с {formatted_date} в {appt['Время']}. Выберите новую дату:"
            )

            # Определяем длительность услуги для проверки доступности
            service_duration = 30  # По умолчанию 30 минут

            # Найдем все последовательные слоты для этой записи, чтобы определить длительность
            appointment_slots = []
            current_date = appt['Дата']
            client_id = str(client['id'])
            all_slots = sheets_service.schedule_sheet.get_all_records()

            for slot in all_slots:
                if (slot.get('Дата') == current_date and 
                    str(slot.get('id_специалиста')) == str(appt['id_специалиста']) and
                    str(slot.get('id_клиента')) == client_id):
                    appointment_slots.append(slot)

            # Сортируем слоты по времени
            appointment_slots.sort(key=lambda s: s['Время'])

            # Если нашли несколько слотов, вычисляем общую длительность
            if len(appointment_slots) > 1:
                try:
                    first_time = datetime.strptime(appointment_slots[0]['Время'], '%H:%M')
                    last_time = datetime.strptime(appointment_slots[-1]['Время'], '%H:%M')
                    diff_minutes = (last_time - first_time).seconds // 60 + 30  # +30 для последнего слота
                    service_duration = diff_minutes
                except Exception as e_time:
                    logger.warning(f"Ошибка при расчете длительности услуги: {e_time}")

            # Сохраняем длительность услуги для использования при формировании календаря
            with bot.retrieve_data(user_id, chat_id) as data:
                data['service_duration'] = service_duration

            # Показываем календарь для выбора новой даты
            today = date.today()
            year, month = today.year, today.month

            # Создаем календарь с учетом длительности услуги
            create_date_calendar(bot, chat_id, year, month, service_duration, 
                             appt['id_специалиста'], sheets_service, scheduler_service)
        except Exception as e:
            logger.error(f"Ошибка reschedule_appointment_request: {e}", exc_info=True)
            bot.answer_callback_query(call.id, "Ошибка обработки запроса.")

    @bot.callback_query_handler(func=lambda call: call.data.startswith("bookdate_"), state=ClientStates.rescheduling_select_date)
    def select_reschedule_date(call):
        """Выбор даты для переноса записи"""
        try:
            _, year, month, day = call.data.split('_')
            year, month, day = int(year), int(month), int(day)
            date_str = f"{year}-{month:02d}-{day:02d}"
            user_id = call.from_user.id
            chat_id = call.message.chat.id

            # Получаем данные из состояния
            with bot.retrieve_data(user_id, chat_id) as data:
                specialist_id = data.get('specialist_id')
                # Определяем длительность услуги, если сохранена
                service_duration = data.get('service_duration', 30)

            # Нормализуем дату для корректного сравнения
            date_str = normalize_date(date_str)

            # Получаем свободные слоты на эту дату
            available_slots = sheets_service.get_available_slots(specialist_id, date_str)
            if not available_slots:
                bot.answer_callback_query(call.id, text="Нет доступных времен на эту дату")
                return

            # Проверяем наличие последовательных слотов для услуги
            has_slots = check_consecutive_slots(available_slots, service_duration)
            if not has_slots:
                bot.answer_callback_query(call.id, text="Нет подходящих интервалов времени для выбранной услуги")
                return

            # Убираем сообщение с календарем
            try:
                bot.delete_message(chat_id, call.message.message_id)
            except Exception as e_del:
                logger.warning(f"Не удалось удалить сообщение календаря: {e_del}")

            # Переходим к выбору времени
            bot.set_state(user_id, ClientStates.rescheduling_select_time, chat_id)

            # Сохраняем выбранную дату
            with bot.retrieve_data(user_id, chat_id) as data:
                data['new_date'] = date_str
                try:
                    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                    data['new_formatted_date'] = date_obj.strftime('%d.%m.%Y')
                except:
                    data['new_formatted_date'] = date_str

            # Если есть scheduler_service и определена длительность услуги
            if scheduler_service and service_duration:
                # Получаем доступные времена с учетом длительности
                available_times = scheduler_service.get_available_times(
                    specialist_id, date_str, service_duration
                )

                # Создаем клавиатуру с доступными временами
                keyboard = types.InlineKeyboardMarkup()
                for time_str in available_times:
                    keyboard.add(types.InlineKeyboardButton(
                        time_str, callback_data=f"reschedtime_{time_str}"
                    ))
                keyboard.add(types.InlineKeyboardButton("Отмена", callback_data="cancel"))

                bot.send_message(chat_id, "Выберите удобное время:", reply_markup=keyboard)
                bot.answer_callback_query(call.id)
                return

            # Используем стандартную логику, если нет scheduler_service
            # Подбираем слоты с учетом длительности услуги
            slot_count = max(1, (service_duration + 29) // 30)  # Округление вверх

            # Составляем список слотов (в минутах от начала дня)
            slots_by_time = []
            for slot in available_slots:
                try:
                    h, m = map(int, slot['Время'].split(':'))
                    time_val = h*60 + m
                    slots_by_time.append((time_val, slot['id']))
                except (ValueError, KeyError) as e:
                    logger.warning(f"Ошибка с форматом времени слота: {e}")
                    continue

            slots_by_time.sort()

            # Ищем последовательные слоты достаточной длительности
            options = []
            for i in range(len(slots_by_time) - slot_count + 1):
                seq = [slots_by_time[i]]
                contiguous = True
                for j in range(1, slot_count):
                    if i+j >= len(slots_by_time):
                        contiguous = False
                        break
                    prev_time = slots_by_time[i+j-1][0]
                    curr_time = slots_by_time[i+j][0]
                    diff = curr_time - prev_time
                    if diff != 30:
                        contiguous = False
                        break

                if contiguous:
                    seq_ids = [slots_by_time[i+k][1] for k in range(slot_count)]
                    start_minutes = slots_by_time[i][0]
                    end_minutes = start_minutes + service_duration
                    start_h = start_minutes // 60
                    start_m = start_minutes % 60
                    end_h = end_minutes // 60
                    end_m = end_minutes % 60
                    start_time_str = f"{start_h:02d}:{start_m:02d}"
                    end_time_str = f"{end_h:02d}:{end_m:02d}"
                    label = f"{start_time_str}" if slot_count == 1 else f"{start_time_str}-{end_time_str}"
                    options.append((label, seq_ids))

            if not options:
                bot.answer_callback_query(call.id, text="Нет подходящих интервалов времени для выбранной услуги")
                return

            # Сохраняем варианты слотов
            with bot.retrieve_data(user_id, chat_id) as data:
                data['booking_options'] = {str(ids[0]): ids for _, ids in options}

            # Создаем клавиатуру с доступными временами
            keyboard = types.InlineKeyboardMarkup()
            for label, seq_ids in options:
                first_id = seq_ids[0]
                keyboard.add(types.InlineKeyboardButton(label, callback_data=f"reschedtime_{first_id}"))
            keyboard.add(types.InlineKeyboardButton("Отмена", callback_data="cancel"))

            bot.send_message(chat_id, "Выберите удобное время:", reply_markup=keyboard)
            bot.answer_callback_query(call.id)
        except Exception as e:
            logger.error(f"Ошибка select_reschedule_date: {e}", exc_info=True)
            bot.answer_callback_query(call.id, text="Ошибка при выборе даты")

    @bot.callback_query_handler(func=lambda call: call.data.startswith("reschedtime_"), state=ClientStates.rescheduling_select_time)
    def select_reschedule_time(call):
        """
        Выбор времени для переноса записи
        """
        try:
            time_data = call.data.split('_')[1]
            user_id = call.from_user.id
            chat_id = call.message.chat.id

            # Получаем данные из состояния
            with bot.retrieve_data(user_id, chat_id) as data:
                old_slot_id = data.get('reschedule_slot_id')
                old_date = data.get('reschedule_formatted_date')
                old_time = data.get('reschedule_time')
                new_date = data.get('new_formatted_date')
                specialist_id = data.get('specialist_id')
                new_date_raw = data.get('new_date')
                service_duration = data.get('service_duration', 30)

            # Получаем информацию о новом времени
            if scheduler_service and ':' in time_data:  # Выбрано время в формате HH:MM
                new_time = time_data
                # Получаем ID слота для бронирования
                slot_ids = scheduler_service.get_slot_ids_for_booking(
                    specialist_id, new_date_raw, new_time, service_duration
                )
                if not slot_ids:
                    bot.answer_callback_query(call.id, "Ошибка: слот не найден для бронирования")
                    return
                new_slot_id = slot_ids[0]  # Берем ID первого слота
            else:  # Выбран конкретный слот по ID
                new_slot_id = time_data
                # Получаем информацию о слоте
                all_slots = sheets_service.schedule_sheet.get_all_records()
                new_time = None
                for slot in all_slots:
                    if str(slot.get('id')) == str(new_slot_id):
                        new_time = slot.get('Время')
                        break

                if not new_time:
                    bot.answer_callback_query(call.id, "Ошибка: время не найдено")
                    return

            # Формируем текст подтверждения
            confirm_text = (
                f"Вы хотите перенести запись с {old_date} {old_time} на {new_date} {new_time}. "
                f"Подтвердите действие:"
            )

            # Создаем клавиатуру подтверждения
            keyboard = types.InlineKeyboardMarkup()
            keyboard.row(
                types.InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirmreschedule_{old_slot_id}_{new_slot_id}"),
                types.InlineKeyboardButton("❌ Отменить", callback_data="cancelreschedule")
            )

            # Заменяем сообщение с выбором времени на сообщение подтверждения
            bot.edit_message_text(confirm_text, chat_id, call.message.message_id, reply_markup=keyboard)
        except Exception as e:
            logger.error(f"Ошибка select_reschedule_time: {e}", exc_info=True)
            bot.answer_callback_query(call.id, text="Ошибка при выборе времени")

    @bot.callback_query_handler(func=lambda call: call.data.startswith("confirmreschedule_"))
    def confirm_reschedule(call):
        """
        Подтверждение переноса записи
        """
        try:
            # Извлекаем ID слотов
            _, old_slot_id, new_slot_id = call.data.split('_')
            user_id = call.from_user.id
            chat_id = call.message.chat.id

            # Получаем данные из состояния
            with bot.retrieve_data(user_id, chat_id) as data:
                old_date = data.get('reschedule_formatted_date')
                old_time = data.get('reschedule_time')
                new_date = data.get('new_formatted_date')
                appointments_message_id = data.get('appointments_message_id')

            # Получаем информацию о клиенте
            client = sheets_service.get_client_by_telegram_id(user_id)
            if not client:
                bot.answer_callback_query(call.id, "Клиент не найден.")
                return

            client_id = client['id']

            # Получаем информацию о новом времени
            all_slots = sheets_service.schedule_sheet.get_all_records()
            new_time = None
            specialist_id = None
            for slot in all_slots:
                if str(slot.get('id')) == str(new_slot_id):
                    new_time = slot.get('Время')
                    specialist_id = slot.get('id_специалиста')
                    break

            if not new_time:
                bot.answer_callback_query(call.id, "Время не найдено.")
                return

            # Выполняем перенос записи
            # 1. Бронируем новый слот
            booking_success = sheets_service.book_appointment(new_slot_id, client_id)
            if not booking_success:
                bot.answer_callback_query(call.id, "Ошибка при бронировании нового времени.")
                return

            # 2. Отменяем старый слот
            cancel_success = sheets_service.cancel_appointment(old_slot_id)
            if not cancel_success:
                # Если не удалось отменить старую запись, отменяем и новую
                sheets_service.cancel_appointment(new_slot_id)
                bot.answer_callback_query(call.id, "Ошибка при отмене старой записи.")
                return

            # Перенос успешен
            success_message = f"Ваша запись успешно перенесена с {old_date} {old_time} на {new_date} {new_time}."
            bot.edit_message_text(success_message, chat_id, call.message.message_id)

            # Обновляем список записей, если нужно
            if appointments_message_id:
                # Получаем обновленный список записей
                appointments = sheets_service.get_client_appointments(client_id)
                if appointments:
                    # Сортируем записи по дате и времени
                    appointments.sort(key=lambda a: (a['Дата'], a['Время']))

                    text = "Ваши записи:\n"
                    for i, appt in enumerate(appointments, start=1):
                        # Форматируем дату
                        try:
                            date_obj = datetime.strptime(appt['Дата'], '%Y-%m-%d')
                            formatted_date = date_obj.strftime('%d.%m.%Y')
                        except:
                            formatted_date = appt['Дата']

                        text += f"{i}. {formatted_date} в {appt['Время']}\n"

                    keyboard = types.InlineKeyboardMarkup()
                    for i, appt in enumerate(appointments, start=1):
                        appt_id = appt['id']
                        keyboard.row(
                            types.InlineKeyboardButton(f"✏️ {i}", callback_data=f"reschedappt_{appt_id}"),
                            types.InlineKeyboardButton(f"❌ {i}", callback_data=f"cancelappt_{appt_id}")
                        )
                    keyboard.add(types.InlineKeyboardButton("🔙 Назад", callback_data="cancel"))

                    try:
                        bot.edit_message_text(text, chat_id, appointments_message_id, reply_markup=keyboard)
                    except Exception as e_edit:
                        logger.warning(f"Не удалось обновить список записей: {e_edit}")

                    # Обновляем данные о записях
                    with bot.retrieve_data(user_id, chat_id) as data:
                        data['appointments'] = appointments
                        data['appointments_text'] = text

            # Сбрасываем состояние
            bot.delete_state(user_id, chat_id)

            # Отправляем уведомление специалисту
            if specialist_id:
                specialist = sheets_service.get_specialist_by_id(specialist_id)
                if specialist and specialist.get('Telegram_ID'):
                    try:
                        specialist_telegram_id = specialist.get('Telegram_ID')
                        notification_text = (
                            f"Перенос записи!\n"
                            f"Клиент: {client.get('Имя', 'Клиент')}\n"
                            f"Старая дата: {old_date} {old_time}\n"
                            f"Новая дата: {new_date} {new_time}\n"
                            f"Телефон: {client.get('Телефон', 'Не указан')}"
                        )
                        bot.send_message(specialist_telegram_id, notification_text)
                    except Exception as notify_err:
                        logger.error(f"Ошибка при отправке уведомления специалисту: {notify_err}")
        except Exception as e:
            logger.error(f"Ошибка confirm_reschedule: {e}", exc_info=True)
            bot.answer_callback_query(call.id, "Ошибка при переносе записи.")
            bot.delete_state(call.from_user.id, call.message.chat.id)

    @bot.callback_query_handler(func=lambda call: call.data == "cancelreschedule")
    def cancel_reschedule(call):
        """
        Отмена переноса записи
        """
        try:
            user_id = call.from_user.id
            chat_id = call.message.chat.id

            # Сбрасываем состояние
            bot.delete_state(user_id, chat_id)

            # Сообщаем об отмене
            bot.edit_message_text("Перенос записи отменен.", chat_id, call.message.message_id)

            # Восстанавливаем список записей
            with bot.retrieve_data(user_id, chat_id) as data:
                appointments = data.get('appointments', [])
                appointments_message_id = data.get('appointments_message_id')
                appointments_text = data.get('appointments_text', "Ваши записи:\n")

            if appointments and appointments_message_id:
                keyboard = types.InlineKeyboardMarkup()
                for i, appt in enumerate(appointments, start=1):
                    appt_id = appt['id']
                    keyboard.row(
                        types.InlineKeyboardButton(f"✏️ {i}", callback_data=f"reschedappt_{appt_id}"),
                        types.InlineKeyboardButton(f"❌ {i}", callback_data=f"cancelappt_{appt_id}")
                    )
                keyboard.add(types.InlineKeyboardButton("🔙 Назад", callback_data="cancel"))

                try:
                    bot.edit_message_reply_markup(chat_id, appointments_message_id, reply_markup=keyboard)
                except Exception as e_edit:
                    logger.warning(f"Не удалось восстановить клавиатуру: {e_edit}")
        except Exception as e:
            logger.error(f"Ошибка cancel_reschedule: {e}", exc_info=True)
            bot.answer_callback_query(call.id, "Ошибка.")

    @bot.callback_query_handler(func=lambda call: call.data == "cancel")
    def cancel_callback(call):
        try:
            user_id = call.from_user.id
            chat_id = call.message.chat.id

            # Сбрасываем состояние, если есть
            try:
                bot.delete_state(user_id, chat_id)
            except Exception as e_state:
                logger.warning(f"Ошибка при сбросе состояния: {e_state}")

            # Проверяем, кто пользователь - клиент или специалист
            client = sheets_service.get_client_by_telegram_id(user_id)
            if client:
                # Клиент
                bot.edit_message_text("Действие отменено.", chat_id, call.message.message_id)
                bot.send_message(chat_id, "Действие отменено.", reply_markup=get_client_menu_keyboard())
                return

            specialist = sheets_service.get_specialist_by_telegram_id(user_id)
            if specialist:
                # Специалист
                from handlers.specialist import get_specialist_menu_keyboard
                bot.edit_message_text("Действие отменено.", chat_id, call.message.message_id)
                bot.send_message(chat_id, "Действие отменено.", reply_markup=get_specialist_menu_keyboard())
                return

            # Не зарегистрирован
            bot.edit_message_text("Действие отменено.", chat_id, call.message.message_id)
            bot.send_message(chat_id, "Действие отменено.", reply_markup=get_start_keyboard())
        except Exception as e:
            logger.error(f"Ошибка в обработке cancel: {e}", exc_info=True)
            bot.answer_callback_query(call.id)

    @bot.message_handler(func=lambda message: message.text == "ℹ️ Информация")
    def info_handler(message):
        """
        Обработчик кнопки "Информация" для клиента.
        """
        client = sheets_service.get_client_by_telegram_id(message.from_user.id)
        if not client:
            bot.send_message(
                message.chat.id,
                "Вы не зарегистрированы как клиент. Пожалуйста, получите реферальную ссылку у специалиста.",
                reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add(
                    types.KeyboardButton("🔙 Вернуться в начало")
                )
            )
            return

        # Получаем специалиста клиента
        specialist_id = client['id_специалиста']
        specialist = sheets_service.get_specialist_by_id(specialist_id)

        info_text = "📋 Информация о записи\n\n"

        if specialist:
            info_text += f"Ваш специалист: {specialist.get('Имя', 'Не указано')}\n"
            info_text += f"Специализация: {specialist.get('Специализация', 'Не указана')}\n\n"

        # Добавляем информацию о услугах
        services = sheets_service.get_specialist_services(specialist_id)
        if services:
            info_text += "Доступные услуги:\n"
            for svc in services:
                name = svc.get('Название', 'Без названия')
                duration = svc.get('Продолжительность', '')
                cost = svc.get('Стоимость', '')
                info_text += f"• {name} ({duration} мин, {cost} руб)\n"

        # Добавляем кнопки для оставления отзыва и FAQ
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("⭐ Оставить отзыв", callback_data="leave_review"))
        keyboard.add(types.InlineKeyboardButton("❓ Часто задаваемые вопросы", callback_data="show_faq"))
        keyboard.add(types.InlineKeyboardButton("💬 Задать вопрос", callback_data="ask_support"))

        bot.send_message(message.chat.id, info_text, reply_markup=keyboard)

    @bot.callback_query_handler(func=lambda call: call.data == "show_faq")
    def show_faq(call):
        """
        Показывает FAQ для клиента
        """
        try:
            # Загружаем FAQ клиента
            from utils.faq_client import client_faq

            # Создаем инлайн клавиатуру для разделов FAQ
            keyboard = types.InlineKeyboardMarkup(row_width=1)
            for i, section in enumerate(client_faq.keys()):
                keyboard.add(types.InlineKeyboardButton(section, callback_data=f"faq_section_{i}"))

            keyboard.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_info"))

            bot.edit_message_text(
                "Выберите раздел справки:",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=keyboard
            )

            bot.answer_callback_query(call.id)
        except Exception as e:
            logger.error(f"Ошибка при показе FAQ: {e}", exc_info=True)
            bot.answer_callback_query(call.id, "Ошибка при загрузке справки")

    @bot.callback_query_handler(func=lambda call: call.data.startswith("faq_section_"))
    def show_faq_section(call):
        """
        Показывает выбранный раздел FAQ
        """
        try:
            section_index = int(call.data.split("_")[2])
            from utils.faq_client import client_faq

            sections = list(client_faq.keys())
            if section_index < 0 or section_index >= len(sections):
                bot.answer_callback_query(call.id, "Раздел не найден")
                return

            section_name = sections[section_index]
            section_content = client_faq[section_name]

            # Формируем текст раздела
            text = f"<b>{section_name}</b>\n\n{section_content}\n\n"
            text += "Если у вас остались вопросы, вы можете задать их напрямую нашей поддержке."

            # Создаем клавиатуру для возврата
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("🔙 К разделам", callback_data="show_faq"))
            keyboard.add(types.InlineKeyboardButton("💬 Задать вопрос", callback_data="ask_support"))

            bot.edit_message_text(
                text,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=keyboard,
                parse_mode="HTML"
            )

            bot.answer_callback_query(call.id)
        except Exception as e:
            logger.error(f"Ошибка при показе раздела FAQ: {e}", exc_info=True)
            bot.answer_callback_query(call.id, "Ошибка при загрузке раздела")

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_info")
    def back_to_info(call):
        """
        Возврат к информационному сообщению
        """
        try:
            # Удаляем текущее сообщение
            bot.delete_message(call.message.chat.id, call.message.message_id)
            # Повторно вызываем обработчик кнопки "Информация"
            info_handler_content = info_handler(call.message)
            bot.answer_callback_query(call.id)
        except Exception as e:
            logger.error(f"Ошибка при возврате к информации: {e}", exc_info=True)
            bot.answer_callback_query(call.id, "Ошибка")

    @bot.callback_query_handler(func=lambda call: call.data == "ask_support")
    def ask_support_request(call):
        """
        Обработчик кнопки "Задать вопрос поддержке"
        """
        try:
            bot.edit_message_text(
               "Пожалуйста, напишите ваш вопрос. Специалист поддержки ответит вам в ближайшее время:",
                call.message.chat.id,
                call.message.message_id
            )

            # Переводим пользователя в состояние ожидания вопроса
            bot.set_state(call.from_user.id, ClientStates.waiting_for_support_question, call.message.chat.id)
            bot.answer_callback_query(call.id)
        except Exception as e:
            logger.error(f"Ошибка при запросе поддержки: {e}", exc_info=True)
            bot.answer_callback_query(call.id, "Ошибка")

    @bot.message_handler(state=ClientStates.waiting_for_support_question)
    def process_support_question(message):
        """
        Обрабатывает вопрос клиента к поддержке
        """
        try:
            question = message.text.strip()
            user_id = message.from_user.id
            username = message.from_user.username or f"{message.from_user.first_name} {message.from_user.last_name or ''}"

            if not question:
                bot.send_message(message.chat.id, "Пожалуйста, введите ваш вопрос или нажмите 'Отмена'.")
                return

            # Получаем информацию о клиенте
            client = sheets_service.get_client_by_telegram_id(user_id)
            client_info = ""
            if client:
                client_info = f"Клиент: {client.get('Имя', 'Неизвестно')}\nID: {client['id']}\nТел: {client.get('Телефон', 'Не указан')}"

            # Формируем сообщение для администратора
            admin_message = (
                f"📩 Новый вопрос от клиента\n\n"
                f"От: {username} (Telegram ID: {user_id})\n"
                f"{client_info}\n\n"
                f"Вопрос: {question}\n\n"
                f"Для ответа используйте команду: /reply {user_id} [ваш ответ]"
            )

            # Получаем список администраторов из settings или constants
            try:
                from settings import ADMIN_IDS
                admin_ids = ADMIN_IDS
            except ImportError:
                # Если нет списка в settings, используем указанный ID
                admin_ids = [611331106]  # ID администратора из задания

            # Отправляем вопрос администраторам
            sent = False
            for admin_id in admin_ids:
                try:
                    bot.send_message(admin_id, admin_message)
                    sent = True
                except Exception as admin_err:
                    logger.error(f"Ошибка при отправке сообщения админу {admin_id}: {admin_err}")

            # Уведомляем клиента
            if sent:
                bot.send_message(
                    message.chat.id, 
                    "Ваш вопрос отправлен службе поддержки. Мы ответим вам в ближайшее время.",
                    reply_markup=get_client_menu_keyboard()
                )
            else:
                bot.send_message(
                    message.chat.id,
                    "К сожалению, произошла ошибка при отправке вашего вопроса. Пожалуйста, попробуйте позже.",
                    reply_markup=get_client_menu_keyboard()
                )

            # Сбрасываем состояние
            bot.delete_state(user_id, message.chat.id)

            # Логируем
            logging_service.log_message(user_id, username, f"Отправил вопрос в поддержку: {question}", "user")
        except Exception as e:
            logger.error(f"Ошибка при обработке вопроса поддержке: {e}", exc_info=True)
            bot.send_message(
                message.chat.id, 
                "Произошла ошибка при обработке вашего вопроса. Пожалуйста, попробуйте позже.",
                reply_markup=get_client_menu_keyboard()
            )
            bot.delete_state(message.from_user.id, message.chat.id)

    @bot.callback_query_handler(func=lambda call: call.data == "leave_review")
    def leave_review_request(call):
        """
        Обработчик кнопки "Оставить отзыв"
        """
        user_id = call.from_user.id
        chat_id = call.message.chat.id

        # Получаем данные о клиенте
        client = sheets_service.get_client_by_telegram_id(user_id)
        if not client:
            bot.answer_callback_query(call.id, "Ошибка: данные клиента не найдены.")
            return

        # Переходим к оценке
        bot.set_state(user_id, ClientStates.rating_service, chat_id)

        # Показываем клавиатуру с кнопками оценки
        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=5)
        keyboard.row(
            types.KeyboardButton("⭐⭐⭐⭐⭐"),
            types.KeyboardButton("⭐⭐⭐⭐"),
            types.KeyboardButton("⭐⭐⭐"),
            types.KeyboardButton("⭐⭐"),
            types.KeyboardButton("⭐")
        )
        keyboard.add(types.KeyboardButton("Отменить"))

        bot.send_message(
            chat_id,
            "Пожалуйста, оцените качество услуг:",
            reply_markup=keyboard
        )

        # Удаляем предыдущее сообщение
        try:
            bot.delete_message(chat_id, call.message.message_id)
        except:
            pass

    @bot.message_handler(state=ClientStates.rating_service)
    def process_rating(message):
        try:
            rating_text = message.text.strip()

            if rating_text == "Отменить":
                bot.delete_state(message.from_user.id, message.chat.id)
                bot.send_message(
                    message.chat.id,
                    "Оставление отзыва отменено.",
                    reply_markup=get_client_menu_keyboard()
                )
                return

            # Получаем рейтинг по количеству звезд
            rating_map = {
                "⭐⭐⭐⭐⭐": 5,
                "⭐⭐⭐⭐": 4,
                "⭐⭐⭐": 3,
                "⭐⭐": 2,
                "⭐": 1
            }

            rating = rating_map.get(rating_text)
            if not rating:
                # Если ввели число напрямую
                try:
                    rating = int(rating_text)
                    if rating < 1 or rating > 5:
                        raise ValueError("Рейтинг должен быть от 1 до 5")
                except:
                    bot.send_message(
                        message.chat.id,
                        "Пожалуйста, оцените от 1 до 5 звезд или нажмите 'Отменить':"
                    )
                    return

            user_id = message.from_user.id

            # Получаем данные о клиенте и специалисте
            client = sheets_service.get_client_by_telegram_id(user_id)
            if not client:
                bot.send_message(message.chat.id, "Ошибка: данные клиента не найдены.")
                bot.delete_state(user_id, message.chat.id)
                return

            client_id = client['id']
            specialist_id = client['id_специалиста']

            # Сохраняем рейтинг
            with bot.retrieve_data(user_id, message.chat.id) as data:
                data['rating'] = rating

            # Переходим к запросу комментария
            bot.set_state(user_id, ClientStates.writing_review, message.chat.id)
            bot.send_message(
                message.chat.id,
                "Спасибо за вашу оценку! Хотите оставить комментарий или пожелания?",
                reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).row(
                    types.KeyboardButton("Пропустить")
                )
            )
        except Exception as e:
            logger.error(f"Ошибка process_rating: {e}", exc_info=True)
            bot.send_message(message.chat.id, "Произошла ошибка. Попробуйте позже.")
            bot.delete_state(message.from_user.id, message.chat.id)

    @bot.message_handler(state=ClientStates.writing_review)
    def process_review(message):
        try:
            text = message.text.strip()
            user_id = message.from_user.id

            # Получаем данные о клиенте
            client = sheets_service.get_client_by_telegram_id(user_id)
            if not client:
                bot.send_message(message.chat.id, "Ошибка: данные клиента не найдены.")
                bot.delete_state(user_id, message.chat.id)
                return

            client_id = client['id']
            specialist_id = client['id_специалиста']

            # Получаем рейтинг из состояния
            with bot.retrieve_data(user_id, message.chat.id) as data:
                rating = data.get('rating', 5)

            # Оставляем комментарий, только если он не "Пропустить"
            comment = "" if text == "Пропустить" else text

            # Сохраняем отзыв
            success = sheets_service.add_review(client_id, specialist_id, rating, comment)

            if success:
                bot.send_message(
                    message.chat.id,
                    "Спасибо за ваш отзыв! Он поможет нам стать лучше.",
                    reply_markup=get_client_menu_keyboard()
                )

                # Уведомляем специалиста о новом отзыве
                if specialist_id:
                    specialist = sheets_service.get_specialist_by_id(specialist_id)
                    if specialist and specialist.get('Telegram_ID'):
                        try:
                            specialist_telegram_id = specialist.get('Telegram_ID')
                            stars = "⭐" * rating

                            notification_text = (
                                f"⭐ Новый отзыв от клиента {client.get('Имя', 'Клиент')}!\n\n"
                                f"Оценка: {stars} ({rating}/5)\n"
                            )

                            if comment:
                                notification_text += f"Комментарий: {comment}"

                            bot.send_message(specialist_telegram_id, notification_text)
                        except Exception as notify_err:
                            logger.error(f"Ошибка при отправке уведомления специалисту о новом отзыве: {notify_err}")
            else:
                bot.send_message(
                    message.chat.id,
                    "Произошла ошибка при сохранении отзыва. Пожалуйста, попробуйте позже.",
                    reply_markup=get_client_menu_keyboard()
                )

            # Сбрасываем состояние
            bot.delete_state(user_id, message.chat.id)
        except Exception as e:
            logger.error(f"Ошибка process_review: {e}", exc_info=True)
            bot.send_message(message.chat.id, "Произошла ошибка. Попробуйте позже.")
            bot.delete_state(message.from_user.id, message.chat.id)