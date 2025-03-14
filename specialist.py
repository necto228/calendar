# handlers/specialist.py
import logging
import telebot
from telebot import types
from telebot.handler_backends import State, StatesGroup
from datetime import datetime, date, timedelta
import calendar
import re

logger = logging.getLogger(__name__)


# Состояния для специалиста
class SpecialistStates(StatesGroup):
    # Регистрация
    waiting_for_name = State()
    waiting_for_specialization = State()
    waiting_for_timezone = State()

    # Настройка стандартного расписания
    waiting_for_month_selection = State()  # Новое состояние для выбора месяца
    waiting_for_standard_days = State()
    waiting_for_standard_start = State()
    waiting_for_standard_end = State()
    waiting_for_standard_break = State()
    waiting_for_schedule_confirmation = State()  # Для подтверждения смены расписания

    # Настройка особых дней
    waiting_for_special_date = State()
    waiting_for_special_option = State()
    waiting_for_special_start = State()
    waiting_for_special_end = State()

    # Работа с календарем
    waiting_for_calendar_action = State()
    waiting_for_slot_time = State()  # Для выбора времени для закрытия

    # Настройка услуг
    waiting_for_service_name = State()
    waiting_for_service_duration = State()
    waiting_for_service_price = State()

    # Рассылка сообщений
    waiting_for_recipients_choice = State()
    waiting_for_broadcast_date = State()
    waiting_for_message_text = State()
    waiting_for_message_text_confirm = State()

    # Вопрос в поддержку
    waiting_for_support_question = State()

    # Прочее (можно расширять при необходимости)
    waiting_for_referral_stats = State()


# --- Вспомогательные функции для клавиатур ---
def get_specialist_menu_keyboard():
    """
    Главное меню специалиста (оптимизированное)
    """
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    # Часто используемые функции
    markup.add("📅 Мой календарь", "📆 Управление расписанием")
    markup.add("🔄 Обновить расписание", "🕒 Закрыть/открыть время")
    
    # Менее часто используемые функции вынесены в подменю
    markup.add("⚙️ Дополнительные функции", "❓ FAQ")
    
    return markup

def get_additional_functions_keyboard():
    """
    Дополнительные функции специалиста
    """
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("📋 Настройка услуг", "👥 Мои клиенты")
    markup.add("📢 Рассылка сообщений", "🔗 Реферальная ссылка")
    markup.add("💳 Управление подпиской", "💬 Поддержка")
    markup.add("🔙 Назад в меню специалиста")
    return markup

def get_schedule_menu_keyboard():
    """
    Меню "Управление расписанием"
    """
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("📆 Настроить стандартное расписание")
    markup.add("📌 Настроить особые дни")
    markup.add("🕒 Закрыть/открыть время")
    markup.add("🔙 Назад в меню специалиста")
    return markup


def get_working_days_keyboard(selected_days):
    """
    Инлайн-клавиатура для выбора рабочих дней недели.
    Выбранные дни помечаются галочкой.
    """
    days_of_week = [
        "Понедельник", "Вторник", "Среда",
        "Четверг", "Пятница", "Суббота", "Воскресенье"
    ]
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    for day in days_of_week:
        btn_text = f"✅ {day}" if day in selected_days else day
        keyboard.add(types.InlineKeyboardButton(btn_text, callback_data=f"toggle_work_{day}"))
    keyboard.add(types.InlineKeyboardButton("Готово", callback_data="working_days_done"))
    return keyboard

def normalize_date(date_str):
    """
    Нормализует строку даты, удаляя лишние пробелы, символы переноса строки и апострофы.
    Приводит дату к формату YYYY-MM-DD для корректного сравнения.
    """
    if not date_str:
        return ""

    # Удаляем пробелы, символы переноса строки и апострофы
    date_str = date_str.strip().strip("'").strip('"')

    # Проверяем формат даты и при необходимости преобразуем
    try:
        # Проверяем разные форматы даты
        for fmt in ['%Y-%m-%d', '%d.%m.%Y', '%Y/%m/%d', '%d-%m-%Y']:
            try:
                date_obj = datetime.strptime(date_str, fmt)
                return date_obj.strftime('%Y-%m-%d')
            except ValueError:
                continue

        # Если не удалось распознать стандартный формат, пробуем разбить строку
        if '/' in date_str:
            parts = date_str.split('/')
        elif '-' in date_str:
            parts = date_str.split('-')
        elif '.' in date_str:
            parts = date_str.split('.')
        else:
            # Если не смогли разобрать, возвращаем как есть
            return date_str

        if len(parts) == 3:
            # Пытаемся угадать формат по длине года
            if len(parts[0]) == 4:  # Год-месяц-день
                return f"{parts[0]}-{int(parts[1]):02d}-{int(parts[2]):02d}"
            elif len(parts[2]) == 4:  # День-месяц-год
                return f"{parts[2]}-{int(parts[1]):02d}-{int(parts[0]):02d}"

        # Если не смогли разобрать, возвращаем как есть
        return date_str
    except Exception as e:
        # В случае ошибки возвращаем исходную строку
        logger.warning(f"Ошибка при нормализации даты '{date_str}': {e}")
        return date_str

def get_calendar_keyboard(year, month, selected_dates=None, specialist_id=None, sheets_service=None, mode="select"):
    """
    Инлайн-клавиатура календаря для выбора дат.
    selected_dates – набор дат в формате YYYY-MM-DD, которые помечаются галочкой.
    mode - режим календаря ("select" или "view")
    """
    if selected_dates is None:
        selected_dates = []

    keyboard = types.InlineKeyboardMarkup(row_width=7)

    # Кнопка с названием месяца и стрелками переключения
    month_names = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
                  "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
    month_label = f"{month_names[month - 1]} {year}"

    # Навигация по месяцам
    prev_year = year if month > 1 else year - 1
    prev_month = month - 1 if month > 1 else 12
    next_year = year if month < 12 else year + 1
    next_month = month + 1 if month < 12 else 1

    # Создаем колбеки с учетом режима
    mode_prefix = "view_" if mode == "view" else ""
    btn_prev = types.InlineKeyboardButton("<<", callback_data=f"{mode_prefix}calendar_nav_{prev_year}_{prev_month}")
    btn_next = types.InlineKeyboardButton(">>", callback_data=f"{mode_prefix}calendar_nav_{next_year}_{next_month}")
    btn_month = types.InlineKeyboardButton(month_label, callback_data="ignore")

    keyboard.row(btn_prev, btn_month, btn_next)

    # Заголовок дней недели
    days_header = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    header_btns = [types.InlineKeyboardButton(d, callback_data="ignore") for d in days_header]
    keyboard.row(*header_btns)

    # Получаем данные о днях для режима просмотра
    day_statuses = {}  # Словарь, где ключ - дата, значение - статус (busy, free, mixed, closed)

    if mode == "view" and specialist_id and sheets_service:
        from datetime import datetime, timedelta
        start_date = datetime(year, month, 1).date()
        # Получаем последний день месяца
        if month == 12:
            end_date = datetime(year + 1, 1, 1).date() - timedelta(days=1)
        else:
            end_date = datetime(year, month + 1, 1).date() - timedelta(days=1)

        # Получаем все записи за выбранный период
        all_slots = sheets_service.schedule_sheet.get_all_records()

        # Фильтруем слоты для специалиста
        specialist_slots = []
        for slot in all_slots:
            if str(slot.get('id_специалиста')) == str(specialist_id):
                # Нормализуем дату для корректного сравнения
                slot_date = normalize_date(slot.get('Дата', ''))
                slot['Дата'] = slot_date
                specialist_slots.append(slot)

        # Проверяем каждый день на наличие слотов разных типов
        current_date = start_date
        while current_date <= end_date:
            date_str = current_date.strftime('%Y-%m-%d')

            # Слоты на текущую дату
            date_slots = [s for s in specialist_slots if s.get('Дата') == date_str]

            if date_slots:
                # Проверяем наличие слотов разных типов
                busy_slots = [s for s in date_slots if s.get('Статус') == 'Занято' and s.get('id_клиента')]
                free_slots = [s for s in date_slots if s.get('Статус') == 'Свободно']
                closed_slots = [s for s in date_slots if s.get('Статус') == 'Закрыто' or 
                              (s.get('Статус') == 'Занято' and not s.get('id_клиента'))]

                # Определяем статус дня
                if busy_slots and (free_slots or closed_slots):
                    day_statuses[date_str] = 'mixed'  # Смешанный (занятые и другие слоты)
                elif busy_slots:
                    day_statuses[date_str] = 'busy'   # Только занятые слоты
                elif free_slots:
                    day_statuses[date_str] = 'free'   # Только свободные слоты
                elif closed_slots:
                    day_statuses[date_str] = 'closed' # Только закрытые слоты

            current_date += timedelta(days=1)

    cal = calendar.monthcalendar(year, month)
    today = date.today()
    for week in cal:
        row = []
        for day_num in week:
            if day_num == 0:
                row.append(types.InlineKeyboardButton(" ", callback_data="ignore"))
            else:
                date_str = f"{year}-{month:02d}-{day_num:02d}"
                btn_text = str(day_num)

                # Проверяем, не прошедшая ли дата
                current_date = date(year, month, day_num)
                if current_date < today:
                    row.append(types.InlineKeyboardButton(str(day_num), callback_data="ignore"))
                    continue

                # Разные форматы отображения для разных режимов
                if mode == "select":
                    if date_str in selected_dates:
                        btn_text = f"✅ {day_num}"
                    callback_data = f"calendar_select_{date_str}"
                else:  # view mode
                    # Проверяем статус дня и меняем отображение
                    day_status = day_statuses.get(date_str)
                    if day_status == 'busy':
                        btn_text = f"🟢{day_num}"  # Зеленый - только занятые
                    elif day_status == 'free':
                        btn_text = f"⚪{day_num}"  # Белый - только свободные
                    elif day_status == 'mixed':
                        btn_text = f"🟡{day_num}"  # Желтый - смешанные
                    elif day_status == 'closed':
                        btn_text = f"🔴{day_num}"  # Красный - только закрытые

                    callback_data = f"view_day_{date_str}"

                row.append(types.InlineKeyboardButton(btn_text, callback_data=callback_data))
        keyboard.row(*row)

    # Кнопка подтверждения
    if mode == "select":
        keyboard.add(types.InlineKeyboardButton("Готово", callback_data="calendar_done"))
    else:
        # Добавляем легенду для режима просмотра
        legend_text = "🟢-записи  ⚪-свободно  🟡-смешанно  🔴-закрыто"
        keyboard.add(types.InlineKeyboardButton(legend_text, callback_data="ignore"))
        keyboard.add(types.InlineKeyboardButton("Назад", callback_data="back_to_calendar"))

    return keyboard
def get_month_selection_keyboard():
    """Клавиатура для выбора месяца настройки расписания"""
    keyboard = types.InlineKeyboardMarkup(row_width=3)
    
    # Получаем текущую дату
    today = date.today()
    current_month = today.month
    current_year = today.year
    
    # Добавляем кнопки для текущего и следующих 5 месяцев
    month_names = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
                   "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
    
    for i in range(6):
        month = (current_month + i - 1) % 12 + 1
        year = current_year + (current_month + i - 1) // 12
        month_name = month_names[month - 1]
        
        if i == 0:
            month_text = f"Текущий ({month_name})"
        else:
            month_text = f"{month_name} {year}"
            
        keyboard.add(types.InlineKeyboardButton(
            month_text, 
            callback_data=f"month_{year}_{month}"
        ))
    
    keyboard.add(types.InlineKeyboardButton("Отмена", callback_data="cancel"))
    return keyboard


# =====================================
# Основная функция регистрации хендлеров
# =====================================
def register_handlers(bot: telebot.TeleBot, sheets_service, logging_service, scheduler_service=None):
    """
    Регистрирует все хендлеры, связанные со специалистом:
    - Регистрация специалиста
    - Управление расписанием (стандартные дни, особые дни)
    - Настройка услуг
    - Мои клиенты
    - Рассылка сообщений
    - Реферальная ссылка
    """
    logger.info("Начало регистрации обработчиков specialist.py")

    # =========================
    # 1. Регистрация специалиста
    # =========================
    @bot.message_handler(func=lambda message: message.text == "👨‍⚕️ Я специалист")
    def specialist_start(message):
        """
        Обработчик кнопки "Я специалист" в самом начале.
        """
        try:
            user_id = message.from_user.id
            username = message.from_user.username or f"{message.from_user.first_name} {message.from_user.last_name or ''}"
            logging_service.log_message(user_id, username, "Нажал кнопку 'Я специалист'", 'user')

            # Сброс состояния, если было
            try:
                bot.delete_state(user_id, message.chat.id)
            except Exception as e_del:
                logger.warning(f"Ошибка при удалении состояния: {e_del}")

            # Проверяем, зарегистрирован ли уже
            specialist = sheets_service.get_specialist_by_telegram_id(user_id)
            if specialist:
                # Уже зарегистрирован
                welcome_text = (
                    f"Здравствуйте, {specialist.get('Имя', 'Специалист')}!\n"
                    "Вы уже зарегистрированы как специалист.\n"
                    "Выберите действие из меню:"
                )
                bot.send_message(message.chat.id, welcome_text, reply_markup=get_specialist_menu_keyboard())
                return

            # Начинаем процесс регистрации
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            markup.add("🔙 Вернуться в начало")
            bot.send_message(
                message.chat.id,
                "Для регистрации как Специалист, пожалуйста, укажите ваше полное имя:",
                reply_markup=markup
            )
            bot.set_state(user_id, SpecialistStates.waiting_for_name, message.chat.id)
        except Exception as e:
            logger.error(f"Ошибка при начале регистрации специалиста: {e}", exc_info=True)
            bot.send_message(message.chat.id, "Произошла ошибка. Пожалуйста, попробуйте позже.")

    @bot.message_handler(state=SpecialistStates.waiting_for_name)
    def process_specialist_name(message):
        """
        Состояние: ждем ввод имени специалиста
        """
        try:
            if message.text in ["👨‍⚕️ Я специалист", "👤 Я клиент", "🔙 Вернуться в начало"]:
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
                bot.send_message(message.chat.id, "Имя слишком короткое. Введите не менее 2 символов:")
                return
                
            user_id = message.from_user.id
            with bot.retrieve_data(user_id, message.chat.id) as data:
                data['name'] = name
                
            bot.set_state(user_id, SpecialistStates.waiting_for_specialization, message.chat.id)
            bot.send_message(message.chat.id, f"Спасибо, {name}! Теперь укажите вашу специализацию:")
        except Exception as e:
            logger.error(f"Ошибка process_specialist_name: {e}", exc_info=True)
            bot.send_message(message.chat.id, "Произошла ошибка. Попробуйте позже.")

    @bot.message_handler(state=SpecialistStates.waiting_for_specialization)
    def process_specialist_specialization(message):
        """
        Состояние: ждем ввод специализации
        """
        try:
            if message.text == "🔙 Вернуться в начало":
                bot.delete_state(message.from_user.id, message.chat.id)
                from utils.keyboards import get_start_keyboard
                bot.send_message(
                    message.chat.id,
                    "Вы вернулись в начало. Выберите свою роль:",
                    reply_markup=get_start_keyboard()
                )
                return
                
            spec = message.text.strip()
            if len(spec) < 2:
                bot.send_message(message.chat.id, "Слишком короткая специализация. Уточните, пожалуйста:")
                return
                
            user_id = message.from_user.id
            with bot.retrieve_data(user_id, message.chat.id) as data:
                data['specialization'] = spec
                
            bot.set_state(user_id, SpecialistStates.waiting_for_timezone, message.chat.id)
            
            # Предлагаем варианты часовых поясов
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
            timezones = [
                "Europe/Moscow",  # МСК
                "Europe/Kaliningrad",  # Калининград
                "Europe/Samara",  # Самара
                "Asia/Yekaterinburg",  # Екатеринбург
                "Asia/Omsk",  # Омск
                "Asia/Krasnoyarsk",  # Красноярск
                "Asia/Irkutsk",  # Иркутск
                "Asia/Yakutsk",  # Якутск
                "Asia/Vladivostok",  # Владивосток
                "Asia/Kamchatka"  # Камчатка
            ]
            for tz in timezones:
                markup.add(types.KeyboardButton(tz))
            markup.add(types.KeyboardButton("🔙 Вернуться в начало"))
            
            bot.send_message(
                message.chat.id, 
                "Укажите ваш часовой пояс (выберите из списка или введите вручную в формате 'Europe/Moscow'):",
                reply_markup=markup
            )
        except Exception as e:
            logger.error(f"Ошибка process_specialist_specialization: {e}", exc_info=True)
            bot.send_message(message.chat.id, "Произошла ошибка. Попробуйте позже.")

    @bot.message_handler(state=SpecialistStates.waiting_for_timezone)
    def process_specialist_timezone(message):
        """
        Состояние: ждем ввод часового пояса
        """
        try:
            if message.text == "🔙 Вернуться в начало":
                bot.delete_state(message.from_user.id, message.chat.id)
                from utils.keyboards import get_start_keyboard
                bot.send_message(
                    message.chat.id,
                    "Вы вернулись в начало. Выберите свою роль:",
                    reply_markup=get_start_keyboard()
                )
                return
                
            tz = message.text.strip()
            user_id = message.from_user.id
            
            with bot.retrieve_data(user_id, message.chat.id) as data:
                name = data.get('name')
                specialization = data.get('specialization')
                
            # Регистрируем специалиста, передавая Telegram ID
            new_id = sheets_service.add_specialist(name, specialization, tz, user_id)
            if not new_id:
                bot.send_message(message.chat.id, "Ошибка при регистрации. Попробуйте позже.")
                bot.delete_state(user_id, message.chat.id)
                return
                
            # Генерируем реферальную ссылку
            bot_username = bot.get_me().username
            ref_link = f"https://t.me/{bot_username}?start=ref{new_id}"
            
            # Обновляем реферальную ссылку в БД
            sheets_service.update_specialist_referral_link(new_id, ref_link)
            
            # Сформируем приветствие
            welcome_text = (
                f"Отлично, {name}!\n"
                f"Вы зарегистрированы как специалист ({specialization}).\n"
                "Первые 3 месяца использование бота бесплатно.\n"
                "Теперь вы можете настроить ваше расписание, услуги и управлять клиентами.\n"
                "Выберите действие из меню:"
            )
            
            bot.send_message(
                message.chat.id,
                welcome_text,
                reply_markup=get_specialist_menu_keyboard()
            )
            bot.delete_state(user_id, message.chat.id)

            # Лог
            username = message.from_user.username or f"{message.from_user.first_name} {message.from_user.last_name or ''}"
            logging_service.log_message(user_id, username, f"Зарегистрирован специалист ID={new_id}", "system")
        except Exception as e:
            logger.error(f"Ошибка process_specialist_timezone: {e}", exc_info=True)
            bot.send_message(message.chat.id, "Произошла ошибка. Попробуйте позже.")
            bot.delete_state(message.from_user.id, message.chat.id)

    # =====================
    # 2. Главное меню и подменю
    # =====================
    @bot.message_handler(func=lambda m: m.text == "🔙 Назад в меню специалиста")
    def back_to_specialist_menu(message):
        """
        Возвращаемся в главное меню специалиста
        """
        try:
            user_id = message.from_user.id
            
            # Удаляем состояние, если есть
            try:
                bot.delete_state(user_id, message.chat.id)
            except Exception as e_del:
                logger.warning(f"Ошибка при удалении состояния: {e_del}")
                
            specialist = sheets_service.get_specialist_by_telegram_id(user_id)
            if not specialist:
                bot.send_message(
                    message.chat.id,
                    "Вы не зарегистрированы как специалист.",
                    reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add(
                        types.KeyboardButton("🔙 Вернуться в начало")
                    )
                )
                return
                
            bot.send_message(
                message.chat.id,
                f"Возвращаемся в меню специалиста, {specialist.get('Имя', 'Специалист')}.",
                reply_markup=get_specialist_menu_keyboard()
            )
        except Exception as e:
            logger.error(f"Ошибка back_to_specialist_menu: {e}", exc_info=True)
            bot.send_message(message.chat.id, "Произошла ошибка. Попробуйте позже.")

    @bot.message_handler(func=lambda m: m.text == "⚙️ Дополнительные функции")
    def additional_functions_menu(message):
        """Показывает дополнительное меню для специалиста"""
        try:
            user_id = message.from_user.id
            specialist = sheets_service.get_specialist_by_telegram_id(user_id)
            
            if not specialist:
                bot.send_message(
                    message.chat.id,
                    "Вы не зарегистрированы как специалист.",
                    reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add(
                        types.KeyboardButton("🔙 Вернуться в начало")
                    )
                )
                return
            
            bot.send_message(
                message.chat.id,
                "Выберите нужный пункт меню:",
                reply_markup=get_additional_functions_keyboard()
            )
        except Exception as e:
            logger.error(f"Ошибка additional_functions_menu: {e}", exc_info=True)
            bot.send_message(message.chat.id, "Произошла ошибка. Попробуйте позже.")

    @bot.message_handler(func=lambda m: m.text == "💳 Управление подпиской")
    def subscription_management(message):
        """
        Управление подпиской специалиста
        """
        try:
            user_id = message.from_user.id
            specialist = sheets_service.get_specialist_by_telegram_id(user_id)
            
            if not specialist:
                bot.send_message(
                    message.chat.id,
                    "Вы не зарегистрированы как специалист.",
                    reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add(
                        types.KeyboardButton("🔙 Вернуться в начало")
                    )
                )
                return
            
            # В реальности здесь будет логика получения данных о подписке
            # Пока что показываем заглушку
            
            # Текущая дата
            today = date.today()
            # Дата через 3 месяца после регистрации (заглушка)
            three_months_later = today + timedelta(days=90)
            
            subscription_text = (
                "💳 Информация о вашей подписке\n\n"
                "Статус: Активна ✅\n"
                f"Дата окончания пробного периода: {three_months_later.strftime('%d.%m.%Y')}\n"
                "Тариф: Пробный (бесплатно)\n\n"
                "В настоящее время действует акция: все новые пользователи получают 3 месяца бесплатного использования!"
            )
            
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("💰 Продлить подписку", callback_data="extend_subscription"))
            
            bot.send_message(message.chat.id, subscription_text, reply_markup=keyboard)
        except Exception as e:
            logger.error(f"Ошибка subscription_management: {e}", exc_info=True)
            bot.send_message(message.chat.id, "Произошла ошибка. Попробуйте позже.")

    @bot.callback_query_handler(func=lambda call: call.data == "extend_subscription")
    def extend_subscription(call):
        """Обработчик кнопки продления подписки"""
        try:
            bot.answer_callback_query(call.id)
            
            subscription_text = (
                "🎉 Отличные новости! 🎉\n\n"
                "В связи с запуском сервиса, все подписки на данный момент БЕСПЛАТНЫ!\n\n"
                "Наслаждайтесь полным функционалом без ограничений. "
                "О запуске платных тарифов мы уведомим вас заранее."
            )
            
            bot.send_message(call.message.chat.id, subscription_text)
        except Exception as e:
            logger.error(f"Ошибка extend_subscription: {e}", exc_info=True)
            bot.answer_callback_query(call.id, "Произошла ошибка. Попробуйте позже.")

    @bot.message_handler(func=lambda m: m.text == "💬 Поддержка")
    def support_request(message):
        """
        Обработчик кнопки "Поддержка" для специалиста
        """
        try:
            user_id = message.from_user.id
            specialist = sheets_service.get_specialist_by_telegram_id(user_id)
            
            if not specialist:
                bot.send_message(
                    message.chat.id,
                    "Вы не зарегистрированы как специалист.",
                    reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add(
                        types.KeyboardButton("🔙 Вернуться в начало")
                    )
                )
                return
            
            # Показываем FAQ и возможность задать вопрос
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("❓ Часто задаваемые вопросы", callback_data="show_specialist_faq"))
            keyboard.add(types.InlineKeyboardButton("✉️ Задать вопрос поддержке", callback_data="ask_specialist_support"))
            
            bot.send_message(
                message.chat.id,
                "Выберите действие:",
                reply_markup=keyboard
            )
        except Exception as e:
            logger.error(f"Ошибка support_request: {e}", exc_info=True)
            bot.send_message(message.chat.id, "Произошла ошибка. Попробуйте позже.")

    @bot.callback_query_handler(func=lambda call: call.data == "show_specialist_faq")
    def show_specialist_faq(call):
        """
        Показывает FAQ для специалиста
        """
        try:
            # Загружаем FAQ специалиста
            from utils.faq_specialist import specialist_faq
            
            # Создаем инлайн клавиатуру для разделов FAQ
            keyboard = types.InlineKeyboardMarkup(row_width=1)
            for i, section in enumerate(specialist_faq.keys()):
                keyboard.add(types.InlineKeyboardButton(section, callback_data=f"spec_faq_section_{i}"))
            
            keyboard.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_support"))
            
            bot.edit_message_text(
                "Выберите раздел справки:",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=keyboard
            )
            
            bot.answer_callback_query(call.id)
        except Exception as e:
            logger.error(f"Ошибка при показе FAQ специалиста: {e}", exc_info=True)
            bot.answer_callback_query(call.id, "Ошибка при загрузке справки")

    @bot.callback_query_handler(func=lambda call: call.data.startswith("spec_faq_section_"))
    def show_specialist_faq_section(call):
        """
        Показывает выбранный раздел FAQ для специалиста
        """
        try:
            section_index = int(call.data.split("_")[3])
            from utils.faq_specialist import specialist_faq
            
            sections = list(specialist_faq.keys())
            if section_index < 0 or section_index >= len(sections):
                bot.answer_callback_query(call.id, "Раздел не найден")
                return
                
            section_name = sections[section_index]
            section_content = specialist_faq[section_name]
            
            # Формируем текст раздела
            text = f"<b>{section_name}</b>\n\n{section_content}\n\n"
            text += "Если у вас остались вопросы, вы можете задать их напрямую нашей поддержке."
            
            # Создаем клавиатуру для возврата
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("🔙 К разделам", callback_data="show_specialist_faq"))
            keyboard.add(types.InlineKeyboardButton("✉️ Задать вопрос", callback_data="ask_specialist_support"))
            
            bot.edit_message_text(
                text,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            
            bot.answer_callback_query(call.id)
        except Exception as e:
            logger.error(f"Ошибка при показе раздела FAQ специалиста: {e}", exc_info=True)
            bot.answer_callback_query(call.id, "Ошибка при загрузке раздела")

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_support")
    def back_to_support(call):
        """
        Возврат к выбору действий поддержки
        """
        try:
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("❓ Часто задаваемые вопросы", callback_data="show_specialist_faq"))
            keyboard.add(types.InlineKeyboardButton("✉️ Задать вопрос поддержке", callback_data="ask_specialist_support"))
            
            bot.edit_message_text(
                "Выберите действие:",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=keyboard
            )
            
            bot.answer_callback_query(call.id)
        except Exception as e:
            logger.error(f"Ошибка при возврате к поддержке: {e}", exc_info=True)
            bot.answer_callback_query(call.id, "Ошибка")

    @bot.callback_query_handler(func=lambda call: call.data == "ask_specialist_support")
    def ask_specialist_support_request(call):
        """
        Обработчик кнопки "Задать вопрос поддержке" для специалиста
        """
        try:
            bot.edit_message_text(
                "Пожалуйста, напишите ваш вопрос. Специалист поддержки ответит вам в ближайшее время:",
                call.message.chat.id,
                call.message.message_id
            )
            
            # Переводим пользователя в состояние ожидания вопроса
            bot.set_state(call.from_user.id, SpecialistStates.waiting_for_support_question, call.message.chat.id)
            bot.answer_callback_query(call.id)
        except Exception as e:
            logger.error(f"Ошибка при запросе поддержки: {e}", exc_info=True)
            bot.answer_callback_query(call.id, "Ошибка")

    @bot.message_handler(state=SpecialistStates.waiting_for_support_question)
    def process_specialist_support_question(message):
        """
        Обрабатывает вопрос специалиста к поддержке
        """
        try:
            question = message.text.strip()
            user_id = message.from_user.id
            username = message.from_user.username or f"{message.from_user.first_name} {message.from_user.last_name or ''}"
            
            if not question:
                bot.send_message(message.chat.id, "Пожалуйста, введите ваш вопрос или нажмите 'Отмена'.")
                return
                
            # Получаем информацию о специалисте
            specialist = sheets_service.get_specialist_by_telegram_id(user_id)
            specialist_info = ""
            if specialist:
                specialist_info = (
                    f"Специалист: {specialist.get('Имя', 'Неизвестно')}\n"
                    f"ID: {specialist['id']}\n"
                    f"Специализация: {specialist.get('Специализация', 'Не указана')}"
                )
            
            # Формируем сообщение для администратора
            admin_message = (
                f"📩 Новый вопрос от специалиста\n\n"
                f"От: {username} (Telegram ID: {user_id})\n"
                f"{specialist_info}\n\n"
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
            
            # Уведомляем специалиста
            if sent:
                bot.send_message(
                    message.chat.id, 
                    "Ваш вопрос отправлен службе поддержки. Мы ответим вам в ближайшее время.",
                    reply_markup=get_specialist_menu_keyboard()
                )
            else:
                bot.send_message(
                    message.chat.id,
                    "К сожалению, произошла ошибка при отправке вашего вопроса. Пожалуйста, попробуйте позже.",
                    reply_markup=get_specialist_menu_keyboard()
                )
            
            # Сбрасываем состояние
            bot.delete_state(user_id, message.chat.id)
            
            # Логируем
            logging_service.log_message(user_id, username, f"Отправил вопрос в поддержку: {question}", "user")
        except Exception as e:
            logger.error(f"Ошибка при обработке вопроса поддержке от специалиста: {e}", exc_info=True)
            bot.send_message(
                message.chat.id, 
                "Произошла ошибка при обработке вашего вопроса. Пожалуйста, попробуйте позже.",
                reply_markup=get_specialist_menu_keyboard()
            )
            bot.delete_state(message.from_user.id, message.chat.id)

    @bot.message_handler(func=lambda m: m.text == "❓ FAQ")
    def main_faq_button(message):
        """
        Обработчик главной кнопки FAQ в меню специалиста
        """
        user_id = message.from_user.id
        specialist = sheets_service.get_specialist_by_telegram_id(user_id)
        
        if not specialist:
            bot.send_message(
                message.chat.id,
                "Вы не зарегистрированы как специалист.",
                reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add(
                    types.KeyboardButton("🔙 Вернуться в начало")
                )
            )
            return
        
        try:
            # Загружаем FAQ специалиста
            from utils.faq_specialist import specialist_faq
            
            # Создаем инлайн клавиатуру для разделов FAQ
            keyboard = types.InlineKeyboardMarkup(row_width=1)
            for i, section in enumerate(specialist_faq.keys()):
                keyboard.add(types.InlineKeyboardButton(section, callback_data=f"spec_faq_section_{i}"))
            
            keyboard.add(types.InlineKeyboardButton("✉️ Задать вопрос", callback_data="ask_specialist_support"))
            
            bot.send_message(
                message.chat.id,
                "Выберите раздел справки:",
                reply_markup=keyboard
            )
        except Exception as e:
            logger.error(f"Ошибка при показе FAQ специалиста из меню: {e}", exc_info=True)
            bot.send_message(message.chat.id, "Ошибка при загрузке справки. Попробуйте позже.")

    # =====================
    # 3. Просмотр календаря и управление записями
    # =====================
        @bot.message_handler(func=lambda m: m.text == "📅 Мой календарь")
        def view_my_calendar(message):
        """
        Показывает календарь с отметками о записях для текущего месяца
        """
        try:
            user_id = message.from_user.id
            specialist = sheets_service.get_specialist_by_telegram_id(user_id)

            if not specialist:
                bot.send_message(
                    message.chat.id,
                    "Вы не зарегистрированы как специалист.",
                    reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add(
                        types.KeyboardButton("🔙 Вернуться в начало")
                    )
                )
                return

            # Показываем календарь на текущий месяц
            today = date.today()
            year, month = today.year, today.month

            calendar_kb = get_calendar_keyboard(
                year, month, 
                specialist_id=specialist['id'], 
                sheets_service=sheets_service,
                mode="view"
            )

            bot.send_message(
                message.chat.id,
                "Ваш календарь записей. Дни с записями отмечены 🟢, свободные дни ⚪, смешанные дни 🟡, закрытые дни 🔴. "
                "Выберите день для просмотра записей:",
                reply_markup=calendar_kb
            )
        except Exception as e:
            logger.error(f"Ошибка view_my_calendar: {e}", exc_info=True)
            bot.send_message(message.chat.id, "Произошла ошибка. Попробуйте позже.")

            
            if not specialist:
                bot.send_message(
                    message.chat.id,
                    "Вы не зарегистрированы как специалист.",
                    reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add(
                        types.KeyboardButton("🔙 Вернуться в начало")
                    )
                )
                return
            
            # Показываем календарь на текущий месяц
            today = date.today()
            year, month = today.year, today.month
            
            calendar_kb = get_calendar_keyboard(
                year, month, 
                specialist_id=specialist['id'], 
                sheets_service=sheets_service,
                mode="view"
            )
            
            bot.send_message(
                message.chat.id,
                "Ваш календарь записей. Дни с записями отмечены 🟢. Выберите день для просмотра записей:",
                reply_markup=calendar_kb
            )
        except Exception as e:
            logger.error(f"Ошибка view_my_calendar: {e}", exc_info=True)
            bot.send_message(message.chat.id, "Произошла ошибка. Попробуйте позже.")

    @bot.callback_query_handler(func=lambda call: call.data.startswith("view_calendar_nav_"))
    def view_calendar_nav(call):
        """
        Навигация по календарю просмотра записей
        """
        try:
            _, year, month = call.data.split('_')[2:]
            year = int(year)
            month = int(month)
            
            user_id = call.from_user.id
            specialist = sheets_service.get_specialist_by_telegram_id(user_id)
            
            if not specialist:
                bot.answer_callback_query(call.id, "Ошибка: специалист не найден")
                return
            
            calendar_kb = get_calendar_keyboard(
                year, month, 
                specialist_id=specialist['id'], 
                sheets_service=sheets_service,
                mode="view"
            )
            
            bot.edit_message_reply_markup(
                call.message.chat.id,
                call.message.message_id,
                reply_markup=calendar_kb
            )
            
            bot.answer_callback_query(call.id)
        except Exception as e:
            logger.error(f"Ошибка view_calendar_nav: {e}", exc_info=True)
            bot.answer_callback_query(call.id, "Ошибка при навигации по календарю")

        @bot.callback_query_handler(func=lambda call: call.data.startswith("view_day_"))
        def view_day_appointments(call):
        """
        Просмотр записей на выбранный день
        """
        try:
            date_str = call.data.split('_')[2]
            user_id = call.from_user.id
            chat_id = call.message.chat.id

            specialist = sheets_service.get_specialist_by_telegram_id(user_id)
            if not specialist:
                bot.answer_callback_query(call.id, "Ошибка: специалист не найден")
                return

            specialist_id = specialist['id']

            # Форматируем дату для отображения
            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                formatted_date = date_obj.strftime('%d.%m.%Y')
            except:
                formatted_date = date_str

            # Получаем все слоты на эту дату
            all_slots = sheets_service.schedule_sheet.get_all_records()
            day_slots = []
            normalized_date = normalize_date(date_str)

            for slot in all_slots:
                slot_date = normalize_date(slot.get('Дата', ''))
                if (str(slot.get('id_специалиста')) == str(specialist_id) and 
                    slot_date == normalized_date):
                    day_slots.append(slot)

            # Сортируем слоты по времени
            day_slots.sort(key=lambda s: s['Время'])

            # Разделяем слоты на категории: занятые, свободные и закрытые
            busy_slots = [slot for slot in day_slots if slot.get('Статус') == 'Занято' and slot.get('id_клиента')]
            free_slots = [slot for slot in day_slots if slot.get('Статус') == 'Свободно']
            closed_slots = [slot for slot in day_slots if slot.get('Статус') == 'Закрыто' or 
                          (slot.get('Статус') == 'Занято' and not slot.get('id_клиента'))]

            # Готовим текст сообщения
            if not day_slots:
                text = f"На {formatted_date} нет настроенного расписания."
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("🔙 К календарю", callback_data="back_to_calendar"))

                bot.edit_message_text(
                    text,
                    chat_id,
                    call.message.message_id,
                    reply_markup=keyboard
                )
                bot.answer_callback_query(call.id)
                return

            text = f"Расписание на {formatted_date}:\n\n"

            # Информация о занятых слотах
            if busy_slots:
                text += "🟢 <b>Занятые слоты:</b>\n"
                for i, slot in enumerate(busy_slots, 1):
                    # Находим информацию о клиенте
                    client_id = slot.get('id_клиента')
                    client_info = "Клиент не найден"

                    if client_id:
                        client = sheets_service.get_client_by_id(client_id)
                        if client:
                            client_info = f"{client.get('Имя', 'Без имени')} (тел: {client.get('Телефон', 'Не указан')})"

                    text += f"{i}. {slot['Время']} - {client_info}\n"
                text += "\n"
            else:
                text += "🟢 <b>Занятые слоты:</b> нет записей клиентов.\n\n"

            # Информация о свободных слотах
            if free_slots:
                text += "⚪ <b>Свободные слоты:</b>\n"
                for i, slot in enumerate(free_slots, 1):
                    text += f"{i}. {slot['Время']}\n"
                text += "\n"
            else:
                text += "⚪ <b>Свободные слоты:</b> нет доступных слотов.\n\n"
                
            # Информация о закрытых слотах
            if closed_slots:
                text += "🔴 <b>Закрытые слоты:</b>\n"
                for i, slot in enumerate(closed_slots, 1):
                    text += f"{i}. {slot['Время']}\n"
                text += "\n"

            # Создаем клавиатуру для управления записями
            keyboard = types.InlineKeyboardMarkup()
            
            # Добавляем кнопки для отмены каждой занятой записи
            for i, slot in enumerate(busy_slots, 1):
                slot_id = slot['id']
                time = slot['Время']
                keyboard.add(types.InlineKeyboardButton(
                    f"❌ Отменить запись в {time}", 
                    callback_data=f"cancel_client_appt_{slot_id}"
                ))
            
            # Кнопка для закрытия свободных слотов
            if free_slots:
                keyboard.add(types.InlineKeyboardButton(
                    "🔒 Закрыть свободные слоты", 
                    callback_data=f"close_all_slots_{date_str}"
                ))
                
            # Кнопки для открытия закрытых слотов
            for i, slot in enumerate(closed_slots, 1):
                slot_id = slot['id']
                time = slot['Время']
                keyboard.add(types.InlineKeyboardButton(
                    f"🔓 Открыть слот в {time}", 
                    callback_data=f"open_time_{slot_id}"
                ))
            
            keyboard.add(types.InlineKeyboardButton("🔙 К календарю", callback_data="back_to_calendar"))
            
            # Отправляем сообщение с информацией
            bot.edit_message_text(
                text,
                chat_id,
                call.message.message_id,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            
            bot.answer_callback_query(call.id)
        except Exception as e:
            logger.error(f"Ошибка view_day_appointments: {e}", exc_info=True)
            bot.answer_callback_query(call.id, "Ошибка при просмотре записей")
def view_day_appointments(call):
    """
    Просмотр записей на выбранный день
    """
    try:
        date_str = call.data.split('_')[2]
        user_id = call.from_user.id
        chat_id = call.message.chat.id

        specialist = sheets_service.get_specialist_by_telegram_id(user_id)
        if not specialist:
            bot.answer_callback_query(call.id, "Ошибка: специалист не найден")
            return

        specialist_id = specialist['id']

        # Форматируем дату для отображения
        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            formatted_date = date_obj.strftime('%d.%m.%Y')
        except:
            formatted_date = date_str

        # Получаем все слоты на эту дату
        all_slots = sheets_service.schedule_sheet.get_all_records()
        day_slots = []
        normalized_date = normalize_date(date_str)

        for slot in all_slots:
            slot_date = normalize_date(slot.get('Дата', ''))
            if (str(slot.get('id_специалиста')) == str(specialist_id) and 
                slot_date == normalized_date):
                day_slots.append(slot)

        # Сортируем слоты по времени
        day_slots.sort(key=lambda s: s['Время'])

        # Разделяем слоты на категории: занятые, свободные и закрытые
        busy_slots = [slot for slot in day_slots if slot.get('Статус') == 'Занято' and slot.get('id_клиента')]
        free_slots = [slot for slot in day_slots if slot.get('Статус') == 'Свободно']
        closed_slots = [slot for slot in day_slots if slot.get('Статус') == 'Закрыто' or 
                        (slot.get('Статус') == 'Занято' and not slot.get('id_клиента'))]

        # Готовим текст сообщения
        if not day_slots:
            text = f"На {formatted_date} нет настроенного расписания."
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(types.InlineKeyboardButton("🔙 К календарю", callback_data="back_to_calendar"))
            
            bot.edit_message_text(
                text,
                chat_id,
                call.message.message_id,
                reply_markup=keyboard
            )
            bot.answer_callback_query(call.id)
            return

        text = f"Расписание на {formatted_date}:\n\n"

        # Информация о занятых слотах
        if busy_slots:
            text += "🟢 <b>Занятые слоты:</b>\n"
            for i, slot in enumerate(busy_slots, 1):
                # Находим информацию о клиенте
                client_id = slot.get('id_клиента')
                client_info = "Клиент не найден"
                
                if client_id:
                    client = sheets_service.get_client_by_id(client_id)
                    if client:
                        client_info = f"{client.get('Имя', 'Без имени')} (тел: {client.get('Телефон', 'Не указан')})"
                
                text += f"{i}. {slot['Время']} - {client_info}\n"
            text += "\n"
        else:
            text += "🟢 <b>Занятые слоты:</b> нет записей клиентов.\n\n"

        # Информация о свободных слотах
        if free_slots:
            text += "⚪ <b>Свободные слоты:</b>\n"
            for i, slot in enumerate(free_slots, 1):
                text += f"{i}. {slot['Время']}\n"
            text += "\n"
        else:
            text += "⚪ <b>Свободные слоты:</b> нет доступных слотов.\n\n"
            
        # Информация о закрытых слотах
        if closed_slots:
            text += "🔴 <b>Закрытые слоты:</b>\n"
            for i, slot in enumerate(closed_slots, 1):
                text += f"{i}. {slot['Время']}\n"
            text += "\n"

        # Создаем клавиатуру для управления записями
        keyboard = types.InlineKeyboardMarkup()
        
        # Добавляем кнопки для отмены каждой занятой записи
        for i, slot in enumerate(busy_slots, 1):
            slot_id = slot['id']
            time = slot['Время']
            keyboard.add(types.InlineKeyboardButton(
                f"❌ Отменить запись в {time}", 
                callback_data=f"cancel_client_appt_{slot_id}"
            ))
        
        # Кнопка для закрытия свободных слотов
        if free_slots:
            keyboard.add(types.InlineKeyboardButton(
                "🔒 Закрыть свободные слоты", 
                callback_data=f"close_all_slots_{date_str}"
            ))
            
        # Кнопки для открытия закрытых слотов
        for i, slot in enumerate(closed_slots, 1):
            slot_id = slot['id']
            time = slot['Время']
            keyboard.add(types.InlineKeyboardButton(
                f"🔓 Открыть слот в {time}", 
                callback_data=f"open_time_{slot_id}"
            ))
        
        keyboard.add(types.InlineKeyboardButton("🔙 К календарю", callback_data="back_to_calendar"))
        
        # Отправляем сообщение с информацией
        bot.edit_message_text(
            text,
            chat_id,
            call.message.message_id,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        bot.answer_callback_query(call.id)
    except Exception as e:
        logger.error(f"Ошибка view_day_appointments: {e}", exc_info=True)
        bot.answer_callback_query(call.id, "Ошибка при просмотре записей")

    
            specialist = sheets_service.get_specialist_by_telegram_id(user_id)
            if not specialist:
                bot.answer_callback_query(call.id, "Ошибка: специалист не найден")
                return
    
            specialist_id = specialist['id']
    
            # Форматируем дату для отображения
            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                formatted_date = date_obj.strftime('%d.%m.%Y')
            except:
                formatted_date = date_str
    
            # Получаем все слоты на эту дату
            all_slots = sheets_service.schedule_sheet.get_all_records()
            day_slots = []
            normalized_date = normalize_date(date_str)
    
            for slot in all_slots:
                slot_date = normalize_date(slot.get('Дата', ''))
                if (str(slot.get('id_специалиста')) == str(specialist_id) and 
                    slot_date == normalized_date):
                    day_slots.append(slot)
    
            # Сортируем слоты по времени
            day_slots.sort(key=lambda s: s['Время'])
    
            # Разделяем слоты на категории: занятые, свободные и закрытые
            busy_slots = [slot for slot in day_slots if slot.get('Статус') == 'Занято' and slot.get('id_клиента')]
            free_slots = [slot for slot in day_slots if slot.get('Статус') == 'Свободно']
            closed_slots = [slot for slot in day_slots if slot.get('Статус') == 'Закрыто' or 
                            (slot.get('Статус') == 'Занято' and not slot.get('id_клиента'))]
    
            # Готовим текст сообщения
            if not day_slots:
                text = f"На {formatted_date} нет настроенного расписания."
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("🔙 К календарю", callback_data="back_to_calendar"))
                
                bot.edit_message_text(
                    text,
                    chat_id,
                    call.message.message_id,
                    reply_markup=keyboard
                )
                bot.answer_callback_query(call.id)
                return
    
            text = f"Расписание на {formatted_date}:\n\n"
    
            # Информация о занятых слотах
            if busy_slots:
                text += "🟢 <b>Занятые слоты:</b>\n"
                for i, slot in enumerate(busy_slots, 1):
                    # Находим информацию о клиенте
                    client_id = slot.get('id_клиента')
                    client_info = "Клиент не найден"
                    
                    if client_id:
                        client = sheets_service.get_client_by_id(client_id)
                        if client:
                            client_info = f"{client.get('Имя', 'Без имени')} (тел: {client.get('Телефон', 'Не указан')})"
                    
                    text += f"{i}. {slot['Время']} - {client_info}\n"
                text += "\n"
            else:
                text += "🟢 <b>Занятые слоты:</b> нет записей клиентов.\n\n"
    
            # Информация о свободных слотах
            if free_slots:
                text += "⚪ <b>Свободные слоты:</b>\n"
                for i, slot in enumerate(free_slots, 1):
                    text += f"{i}. {slot['Время']}\n"
                text += "\n"
            else:
                text += "⚪ <b>Свободные слоты:</b> нет доступных слотов.\n\n"
                
            # Информация о закрытых слотах
            if closed_slots:
                text += "🔴 <b>Закрытые слоты:</b>\n"
                for i, slot in enumerate(closed_slots, 1):
                    text += f"{i}. {slot['Время']}\n"
                text += "\n"
    
            # Создаем клавиатуру для управления записями
            keyboard = types.InlineKeyboardMarkup()
            
            # Добавляем кнопки для отмены каждой занятой записи
            for i, slot in enumerate(busy_slots, 1):
                slot_id = slot['id']
                time = slot['Время']
                keyboard.add(types.InlineKeyboardButton(
                    f"❌ Отменить запись в {time}", 
                    callback_data=f"cancel_client_appt_{slot_id}"
                ))
            
            # Кнопка для закрытия свободных слотов
            if free_slots:
                keyboard.add(types.InlineKeyboardButton(
                    "🔒 Закрыть свободные слоты", 
                    callback_data=f"close_all_slots_{date_str}"
                ))
                
            # Кнопки для открытия закрытых слотов
            for i, slot in enumerate(closed_slots, 1):
                slot_id = slot['id']
                time = slot['Время']
                keyboard.add(types.InlineKeyboardButton(
                    f"🔓 Открыть слот в {time}", 
                    callback_data=f"open_time_{slot_id}"
                ))
            
            keyboard.add(types.InlineKeyboardButton("🔙 К календарю", callback_data="back_to_calendar"))
            
            # Отправляем сообщение с информацией
            bot.edit_message_text(
                text,
                chat_id,
                call.message.message_id,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            
            bot.answer_callback_query(call.id)
        except Exception as e:
            logger.error(f"Ошибка view_day_appointments: {e}", exc_info=True)
            bot.answer_callback_query(call.id, "Ошибка при просмотре записей")

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_calendar")
    def back_to_calendar(call):
        """
        Возврат к просмотру календаря
        """
        try:
            user_id = call.from_user.id
            specialist = sheets_service.get_specialist_by_telegram_id(user_id)
            
            if not specialist:
                bot.answer_callback_query(call.id, "Ошибка: специалист не найден")
                return
            
            # Показываем календарь на текущий месяц
            today = date.today()
            year, month = today.year, today.month
            
            calendar_kb = get_calendar_keyboard(
                year, month, 
                specialist_id=specialist['id'], 
                sheets_service=sheets_service,
                mode="view"
            )
            
            bot.edit_message_text(
                "Ваш календарь записей. Дни с записями отмечены 🟢. Выберите день для просмотра записей:",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=calendar_kb
            )
            
            bot.answer_callback_query(call.id)
        except Exception as e:
            logger.error(f"Ошибка back_to_calendar: {e}", exc_info=True)
            bot.answer_callback_query(call.id, "Ошибка при возврате к календарю")

    @bot.callback_query_handler(func=lambda call: call.data.startswith("cancel_client_appt_"))
    def cancel_client_appointment(call):
        """
        Отмена записи клиента специалистом
        """
        try:
            slot_id = call.data.split('_')[3]
            user_id = call.from_user.id
            chat_id = call.message.chat.id
            
            specialist = sheets_service.get_specialist_by_telegram_id(user_id)
            if not specialist:
                bot.answer_callback_query(call.id, "Ошибка: специалист не найден")
                return
            
            # Получаем информацию о записи перед отменой
            all_slots = sheets_service.schedule_sheet.get_all_records()
            appointment_info = None
            client_id = None
            
            for slot in all_slots:
                if str(slot.get('id')) == str(slot_id):
                    appointment_info = slot
                    client_id = slot.get('id_клиента')
                    break
            
            if not appointment_info or not client_id:
                bot.answer_callback_query(call.id, "Запись не найдена")
                return
            
            # Форматируем дату для отображения
            date_str = appointment_info['Дата']
            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                formatted_date = date_obj.strftime('%d.%m.%Y')
            except:
                formatted_date = date_str
            
            time_str = appointment_info['Время']
            
            # Создаем клавиатуру для подтверждения отмены
            keyboard = types.InlineKeyboardMarkup()
            keyboard.row(
                types.InlineKeyboardButton(
                    "✅ Подтвердить", 
                    callback_data=f"confirm_spec_cancel_{slot_id}_{date_str}"
                ),
                types.InlineKeyboardButton(
                    "❌ Отменить", 
                    callback_data=f"view_day_{date_str}"
                )
            )
            
            # Отправляем запрос на подтверждение
            bot.edit_message_text(
                f"Вы действительно хотите отменить запись на {formatted_date} в {time_str}?",
                chat_id,
                call.message.message_id,
                reply_markup=keyboard
            )
            
            bot.answer_callback_query(call.id)
        except Exception as e:
            logger.error(f"Ошибка cancel_client_appointment: {e}", exc_info=True)
            bot.answer_callback_query(call.id, "Ошибка при отмене записи")

    @bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_spec_cancel_"))
    def confirm_specialist_cancel_appointment(call):
        """
        Подтверждение отмены записи клиента специалистом
        """
        try:
            parts = call.data.split('_')
            slot_id = parts[3]
            date_str = parts[4]
            
            user_id = call.from_user.id
            chat_id = call.message.chat.id
            
            specialist = sheets_service.get_specialist_by_telegram_id(user_id)
            if not specialist:
                bot.answer_callback_query(call.id, "Ошибка: специалист не найден")
                return
            
            # Получаем информацию о записи перед отменой
            all_slots = sheets_service.schedule_sheet.get_all_records()
            appointment_info = None
            client_id = None
            
            for slot in all_slots:
                if str(slot.get('id')) == str(slot_id):
                    appointment_info = slot
                    client_id = slot.get('id_клиента')
                    break
            
            if not appointment_info or not client_id:
                bot.answer_callback_query(call.id, "Запись не найдена")
                return
            
            # Находим информацию о клиенте
            client = sheets_service.get_client_by_id(client_id)
            
            # Отменяем запись
            success = sheets_service.cancel_appointment(slot_id)
            if not success:
                bot.answer_callback_query(call.id, "Не удалось отменить запись")
                return
            
            # Форматируем дату для отображения
            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                formatted_date = date_obj.strftime('%d.%m.%Y')
            except:
                formatted_date = date_str
            
            time_str = appointment_info['Время']
            
            # Отправляем уведомление клиенту
            if client and client.get('Telegram_ID'):
                client_telegram_id = client.get('Telegram_ID')
                notification_text = (
                    f"❗ Ваша запись на {formatted_date} в {time_str} была отменена специалистом.\n"
                    f"Пожалуйста, выберите другое время для записи."
                )
                try:
                    bot.send_message(client_telegram_id, notification_text)
                except Exception as notify_err:
                    logger.error(f"Ошибка при отправке уведомления клиенту: {notify_err}")
            
            # Возвращаемся к просмотру дня
            view_day_appointments_callback = types.CallbackQuery(
                id=call.id,
                from_user=call.from_user,
                chat_instance=call.chat_instance,
                message=call.message,
                data=f"view_day_{date_str}"
            )
            view_day_appointments(view_day_appointments_callback)
            
            # Дополнительно отправляем уведомление об успешной отмене
            bot.answer_callback_query(call.id, "Запись успешно отменена", show_alert=True)
        except Exception as e:
            logger.error(f"Ошибка confirm_specialist_cancel_appointment: {e}", exc_info=True)
            bot.answer_callback_query(call.id, "Ошибка при отмене записи")

    @bot.callback_query_handler(func=lambda call: call.data.startswith("close_all_slots_"))
    def close_all_free_slots(call):
        """
        Закрытие всех свободных слотов на выбранную дату
        """
        try:
            date_str = call.data.split('_')[3]
            # Нормализуем дату перед использованием
            date_str = normalize_date(date_str)
            user_id = call.from_user.id

            specialist = sheets_service.get_specialist_by_telegram_id(user_id)
            if not specialist:
                bot.answer_callback_query(call.id, "Ошибка: специалист не найден")
                return

            specialist_id = specialist['id']

            # Закрываем свободные слоты
            closed = sheets_service.close_day_slots(specialist_id, date_str)
            
            if closed:
                bot.answer_callback_query(call.id, "Свободные слоты успешно закрыты", show_alert=True)
                
                # Обновляем просмотр дня
                view_day_appointments_callback = types.CallbackQuery(
                    id=call.id,
                    from_user=call.from_user,
                    chat_instance=call.chat_instance,
                    message=call.message,
                    data=f"view_day_{date_str}"
                )
                view_day_appointments(view_day_appointments_callback)
            else:
                bot.answer_callback_query(call.id, "Нет свободных слотов для закрытия", show_alert=True)
        except Exception as e:
            logger.error(f"Ошибка close_all_free_slots: {e}", exc_info=True)
            bot.answer_callback_query(call.id, "Ошибка при закрытии слотов")
            # =====================
            # 4. Управление расписанием и закрытие определенного времени
            # =====================
    @bot.message_handler(func=lambda m: m.text == "🕒 Закрыть/открыть время")
    def close_specific_time(message):
        """
        Закрытие определенного временного слота в расписании
        """
        try:
            user_id = message.from_user.id
            specialist = sheets_service.get_specialist_by_telegram_id(user_id)
    
            if not specialist:
                bot.send_message(
                    message.chat.id,
                    "Вы не зарегистрированы как специалист.",
                    reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add(
                        types.KeyboardButton("🔙 Вернуться в начало")
                    )
                )
                return
    
            # Запрашиваем дату
            today = date.today()
            year, month = today.year, today.month
    
            calendar_kb = get_calendar_keyboard(
                year, month, 
                specialist_id=specialist['id'], 
                sheets_service=sheets_service
            )
    
            bot.send_message(
                message.chat.id,
                "Выберите дату, в которой хотите закрыть определенное время:",
                reply_markup=calendar_kb
            )
    
            # Устанавливаем состояние
            bot.set_state(user_id, SpecialistStates.waiting_for_calendar_action, message.chat.id)
        except Exception as e:
            logger.error(f"Ошибка close_specific_time: {e}", exc_info=True)
            bot.send_message(message.chat.id, "Произошла ошибка. Попробуйте позже.")

    @bot.callback_query_handler(func=lambda call: call.data.startswith("calendar_select_"), 
                               state=SpecialistStates.waiting_for_calendar_action)
    def select_date_for_action(call):
        """
        Выбор даты для закрытия/открытия временных слотов
        """
        try:
            date_str = call.data.split('_')[2]
            # Нормализуем дату перед использованием
            date_str = normalize_date(date_str)
            user_id = call.from_user.id
            chat_id = call.message.chat.id
            
            specialist = sheets_service.get_specialist_by_telegram_id(user_id)
            if not specialist:
                bot.answer_callback_query(call.id, "Ошибка: специалист не найден")
                return
            specialist_id = specialist['id']

            # Форматируем дату для отображения
            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                formatted_date = date_obj.strftime('%d.%m.%Y')
            except:
                formatted_date = date_str

            # Получаем все слоты на эту дату
            all_slots = sheets_service.schedule_sheet.get_all_records()
            day_slots = []
            normalized_date = normalize_date(date_str)
            
            for slot in all_slots:
                slot_date = normalize_date(slot.get('Дата', ''))
                if (str(slot.get('id_специалиста')) == str(specialist_id) and 
                    slot_date == normalized_date):
                    day_slots.append(slot)

            # Сортируем слоты по времени
            day_slots.sort(key=lambda s: s['Время'])

            # Разделяем слоты на занятые и свободные
            busy_slots = [slot for slot in day_slots if slot.get('Статус') == 'Занято']
            free_slots = [slot for slot in day_slots if slot.get('Статус') == 'Свободно']

            if not day_slots:
                bot.answer_callback_query(call.id, "На эту дату нет настроенного расписания")
                return

            # Сохраняем выбранную дату в состояние
            with bot.retrieve_data(user_id, chat_id) as data:
                data['selected_date'] = date_str
                data['formatted_date'] = formatted_date

            # Создаем клавиатуру для выбора времени
            keyboard = types.InlineKeyboardMarkup()

            # Добавляем свободные слоты (можно закрыть)
            if free_slots:
                for slot in free_slots:
                    time = slot['Время']
                    slot_id = slot['id']
                    keyboard.add(types.InlineKeyboardButton(
                        f"🔒 Закрыть {time}", 
                        callback_data=f"close_time_{slot_id}"
                    ))

            # Добавляем занятые слоты (нельзя открыть, если занято клиентом)
            for slot in busy_slots:
                time = slot['Время']
                slot_id = slot['id']
                # Если статус "Закрыто" - его можно открыть
                if not slot.get('id_клиента'):
                    keyboard.add(types.InlineKeyboardButton(
                        f"🔓 Открыть {time}", 
                        callback_data=f"open_time_{slot_id}"
                    ))
                else:
                    keyboard.add(types.InlineKeyboardButton(
                        f"👤 Занято {time} (клиент)", 
                        callback_data="ignore"
                    ))

            keyboard.add(types.InlineKeyboardButton("🔙 Отмена", callback_data="cancel_time_action"))

            # Переходим к выбору времени
            bot.set_state(user_id, SpecialistStates.waiting_for_slot_time, chat_id)

            # Отправляем сообщение с выбором времени
            bot.send_message(
                chat_id,
                f"Выберите время для действия на {formatted_date}:",
                reply_markup=keyboard
            )

            # Удаляем сообщение с календарем
            try:
                bot.delete_message(chat_id, call.message.message_id)
            except Exception as e_del:
                logger.warning(f"Не удалось удалить сообщение с календарем: {e_del}")

            bot.answer_callback_query(call.id)
        except Exception as e:
            logger.error(f"Ошибка select_date_for_action: {e}", exc_info=True)
            bot.answer_callback_query(call.id, "Ошибка при выборе даты")

    @bot.callback_query_handler(func=lambda call: call.data.startswith("close_time_"), 
                               state=SpecialistStates.waiting_for_slot_time)
    def close_specific_time_slot(call):
        """
        Закрытие конкретного временного слота
        """
        try:
            slot_id = call.data.split('_')[2]
            user_id = call.from_user.id
            chat_id = call.message.chat.id

            specialist = sheets_service.get_specialist_by_telegram_id(user_id)
            if not specialist:
                bot.answer_callback_query(call.id, "Ошибка: специалист не найден")
                return

            # Проверяем, что слот все еще свободен
            all_slots = sheets_service.schedule_sheet.get_all_records()
            target_slot = None

            for slot in all_slots:
                if str(slot.get('id')) == str(slot_id):
                    target_slot = slot
                    break

            if not target_slot:
                bot.answer_callback_query(call.id, "Ошибка: слот не найден")
                return

            if target_slot.get('Статус') != 'Свободно':
                bot.answer_callback_query(call.id, "Этот слот уже недоступен для закрытия")
                return

            # Закрываем слот
            all_slots = sheets_service.schedule_sheet.get_all_records()
            row_idx = None
            for idx, slot in enumerate(all_slots, start=2):  # +2 т.к. первая строка - заголовки
                if str(slot.get('id')) == str(slot_id):
                    row_idx = idx
                    break

            if row_idx:
                # Получаем заголовки для определения индекса колонки
                headers = sheets_service.schedule_sheet.row_values(1)
                status_col = headers.index('Статус') + 1

                # Меняем статус на "Закрыто"
                sheets_service.schedule_sheet.update_cell(row_idx, status_col, 'Закрыто')

                # Получаем информацию о дате и времени
                date_str = target_slot.get('Дата', '')
                time_str = target_slot.get('Время', '')

                try:
                    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                    formatted_date = date_obj.strftime('%d.%m.%Y')
                except:
                    formatted_date = date_str

                bot.answer_callback_query(call.id, f"Время {time_str} на {formatted_date} успешно закрыто", show_alert=True)

                # Сбрасываем состояние и возвращаемся в меню
                bot.delete_state(user_id, chat_id)
                bot.send_message(
                    chat_id,
                    f"Слот на {formatted_date} в {time_str} закрыт.",
                    reply_markup=get_specialist_menu_keyboard()
                )

                # Удаляем сообщение с выбором времени
                try:
                    bot.delete_message(chat_id, call.message.message_id)
                except Exception as e_del:
                    logger.warning(f"Не удалось удалить сообщение: {e_del}")
            else:
                bot.answer_callback_query(call.id, "Ошибка: слот не найден в расписании")
        except Exception as e:
            logger.error(f"Ошибка close_specific_time_slot: {e}", exc_info=True)
            bot.answer_callback_query(call.id, "Ошибка при закрытии слота")
            bot.delete_state(call.from_user.id, call.message.chat.id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("open_time_"), 
                               state=SpecialistStates.waiting_for_slot_time)
    def open_specific_time_slot(call):
        """
        Открытие закрытого временного слота
        """
        try:
            slot_id = call.data.split('_')[2]
            user_id = call.from_user.id
            chat_id = call.message.chat.id

            specialist = sheets_service.get_specialist_by_telegram_id(user_id)
            if not specialist:
                bot.answer_callback_query(call.id, "Ошибка: специалист не найден")
                return

            # Проверяем, что слот закрыт и не занят клиентом
            all_slots = sheets_service.schedule_sheet.get_all_records()
            target_slot = None

            for slot in all_slots:
                if str(slot.get('id')) == str(slot_id):
                    target_slot = slot
                    break

            if not target_slot:
                bot.answer_callback_query(call.id, "Ошибка: слот не найден")
                return

            if target_slot.get('Статус') != 'Закрыто' or target_slot.get('id_клиента'):
                bot.answer_callback_query(call.id, "Этот слот недоступен для открытия")
                return

            # Открываем слот
            all_slots = sheets_service.schedule_sheet.get_all_records()
            row_idx = None
            for idx, slot in enumerate(all_slots, start=2):  # +2 т.к. первая строка - заголовки
                if str(slot.get('id')) == str(slot_id):
                    row_idx = idx
                    break

            if row_idx:
                # Получаем заголовки для определения индекса колонки
                headers = sheets_service.schedule_sheet.row_values(1)
                status_col = headers.index('Статус') + 1

                # Меняем статус на "Свободно"
                sheets_service.schedule_sheet.update_cell(row_idx, status_col, 'Свободно')

                # Получаем информацию о дате и времени
                date_str = target_slot.get('Дата', '')
                time_str = target_slot.get('Время', '')

                try:
                    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                    formatted_date = date_obj.strftime('%d.%m.%Y')
                except:
                    formatted_date = date_str

                bot.answer_callback_query(call.id, f"Время {time_str} на {formatted_date} успешно открыто", show_alert=True)

                # Сбрасываем состояние и возвращаемся в меню
                bot.delete_state(user_id, chat_id)
                bot.send_message(
                    chat_id,
                    f"Слот на {formatted_date} в {time_str} теперь доступен для записи.",
                    reply_markup=get_specialist_menu_keyboard()
                )

                # Удаляем сообщение с выбором времени
                try:
                    bot.delete_message(chat_id, call.message.message_id)
                except Exception as e_del:
                    logger.warning(f"Не удалось удалить сообщение: {e_del}")
            else:
                bot.answer_callback_query(call.id, "Ошибка: слот не найден в расписании")
        except Exception as e:
            logger.error(f"Ошибка open_specific_time_slot: {e}", exc_info=True)
            bot.answer_callback_query(call.id, "Ошибка при открытии слота")
            bot.delete_state(call.from_user.id, call.message.chat.id)

    @bot.callback_query_handler(func=lambda call: call.data == "cancel_time_action", 
                               state=SpecialistStates.waiting_for_slot_time)
    def cancel_time_action(call):
        """
        Отмена действия с временным слотом
        """
        try:
            user_id = call.from_user.id
            chat_id = call.message.chat.id

            # Сбрасываем состояние
            bot.delete_state(user_id, chat_id)

            # Возвращаемся в меню
            bot.send_message(
                chat_id,
                "Действие отменено.",
                reply_markup=get_specialist_menu_keyboard()
            )

            # Удаляем сообщение с выбором времени
            try:
                bot.delete_message(chat_id, call.message.message_id)
            except Exception as e_del:
                logger.warning(f"Не удалось удалить сообщение: {e_del}")

            bot.answer_callback_query(call.id)
        except Exception as e:
            logger.error(f"Ошибка cancel_time_action: {e}", exc_info=True)
            bot.answer_callback_query(call.id, "Ошибка при отмене действия")
            bot.delete_state(call.from_user.id, call.message.chat.id)

    # =====================
    # 5. Обновленная настройка стандартного расписания
    # =====================
    @bot.message_handler(func=lambda m: m.text == "📆 Управление расписанием")
    def manage_schedule(message):
        """
        Переход в меню "Управление расписанием"
        """
        try:
            user_id = message.from_user.id
            specialist = sheets_service.get_specialist_by_telegram_id(user_id)

            if not specialist:
                bot.send_message(
                    message.chat.id,
                    "Вы не зарегистрированы как специалист.",
                    reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add(
                        types.KeyboardButton("🔙 Вернуться в начало")
                    )
                )
                return

            bot.send_message(
                message.chat.id,
                "Выберите действие для управления расписанием:",
                reply_markup=get_schedule_menu_keyboard()
            )
        except Exception as e:
            logger.error(f"Ошибка manage_schedule: {e}", exc_info=True)
            bot.send_message(message.chat.id, "Произошла ошибка. Попробуйте позже.")

    @bot.message_handler(func=lambda m: m.text == "🔄 Обновить расписание")
    def quick_update_schedule(message):
        """
        Быстрый переход к обновлению стандартного расписания
        """
        try:
            user_id = message.from_user.id
            specialist = sheets_service.get_specialist_by_telegram_id(user_id)

            if not specialist:
                bot.send_message(
                    message.chat.id,
                    "Вы не зарегистрированы как специалист.",
                    reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add(
                        types.KeyboardButton("🔙 Вернуться в начало")
                    )
                )
                return

            # Показываем выбор месяца для настройки
            keyboard = get_month_selection_keyboard()

            bot.send_message(
                message.chat.id,
                "Выберите месяц, для которого хотите настроить стандартное расписание:",
                reply_markup=keyboard
            )

            # Устанавливаем состояние
            bot.set_state(user_id, SpecialistStates.waiting_for_month_selection, message.chat.id)
        except Exception as e:
            logger.error(f"Ошибка quick_update_schedule: {e}", exc_info=True)
            bot.send_message(message.chat.id, "Произошла ошибка. Попробуйте позже.")

    @bot.message_handler(func=lambda m: m.text == "📆 Настроить стандартное расписание")
    def configure_standard_schedule(message):
        """
        Начинаем настройку стандартного расписания (выбор рабочих дней)
        """
        try:
            user_id = message.from_user.id
            specialist = sheets_service.get_specialist_by_telegram_id(user_id)

            if not specialist:
                bot.send_message(
                    message.chat.id,
                    "Вы не зарегистрированы как специалист.",
                    reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add(
                        types.KeyboardButton("🔙 Вернуться в начало")
                    )
                )
                return

            # Показываем выбор месяца для настройки
            keyboard = get_month_selection_keyboard()

            bot.send_message(
                message.chat.id,
                "Выберите месяц, для которого хотите настроить стандартное расписание:",
                reply_markup=keyboard
            )

            # Устанавливаем состояние
            bot.set_state(user_id, SpecialistStates.waiting_for_month_selection, message.chat.id)
        except Exception as e:
            logger.error(f"Ошибка configure_standard_schedule: {e}", exc_info=True)
            bot.send_message(message.chat.id, "Ошибка. Повторите позже.")

    @bot.callback_query_handler(func=lambda call: call.data.startswith("month_"), 
                               state=SpecialistStates.waiting_for_month_selection)
    def process_month_selection(call):
        """
        Обработка выбора месяца для настройки расписания
        """
        try:
            _, year, month = call.data.split('_')
            year = int(year)
            month = int(month)

            user_id = call.from_user.id
            chat_id = call.message.chat.id

            specialist = sheets_service.get_specialist_by_telegram_id(user_id)
            if not specialist:
                bot.answer_callback_query(call.id, "Ошибка: специалист не найден")
                return

            specialist_id = specialist['id']

            # Сохраняем данные о выбранном месяце
            with bot.retrieve_data(user_id, chat_id) as data:
                data['target_year'] = year
                data['target_month'] = month

                # Формируем строковое представление месяца для отображения
                month_names = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
                             "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
                month_str = month_names[month - 1]
                data['target_month_str'] = f"{month_str} {year}"

            # Проверяем, есть ли уже записи на этот месяц
            all_slots = sheets_service.schedule_sheet.get_all_records()

            # Получаем первый и последний день месяца
            if month == 12:
                next_year = year + 1
                next_month = 1
            else:
                next_year = year
                next_month = month + 1

            start_date = datetime(year, month, 1).date()
            end_date = datetime(next_year, next_month, 1).date() - timedelta(days=1)

            # Проверяем, есть ли уже слоты на этот месяц
            month_slots = [
                slot for slot in all_slots 
                if str(slot.get('id_специалиста')) == str(specialist_id) and 
                start_date <= datetime.strptime(slot.get('Дата', '1970-01-01'), '%Y-%m-%d').date() <= end_date
            ]

            # Проверяем, есть ли записи клиентов на этот месяц
            client_bookings = [
                slot for slot in month_slots 
                if slot.get('Статус') == 'Занято' and slot.get('id_клиента')
            ]

            if month_slots:
                # Уже есть расписание на этот месяц
                with bot.retrieve_data(user_id, chat_id) as data:
                    data['has_existing_schedule'] = True
                    data['has_client_bookings'] = len(client_bookings) > 0

                warning_text = f"На {data['target_month_str']} уже настроено расписание."

                if client_bookings:
                    warning_text += (
                        f"\n⚠️ Внимание! На этот месяц уже есть записи клиентов ({len(client_bookings)}).\n"
                        "Если вы измените расписание, все существующие записи будут отменены."
                    )

                warning_text += "\n\nВы уверены, что хотите перенастроить расписание?"

                # Создаем клавиатуру для подтверждения
                keyboard = types.InlineKeyboardMarkup()
                keyboard.row(
                    types.InlineKeyboardButton("✅ Да, изменить", callback_data="confirm_schedule_change"),
                    types.InlineKeyboardButton("❌ Отмена", callback_data="cancel_schedule_change")
                )

                # Если есть записи, предлагаем использовать особые дни
                if client_bookings:
                    keyboard.add(types.InlineKeyboardButton(
                        "📌 Лучше настроить особые дни", 
                        callback_data="use_special_days"
                    ))

                bot.edit_message_text(
                    warning_text,
                    chat_id,
                    call.message.message_id,
                    reply_markup=keyboard
                )
            else:
                # Нет расписания на этот месяц, продолжаем настройку
                with bot.retrieve_data(user_id, chat_id) as data:
                    data['has_existing_schedule'] = False
                    data['has_client_bookings'] = False

                # Удаляем сообщение с выбором месяца
                try:
                    bot.delete_message(chat_id, call.message.message_id)
                except Exception as e_del:
                    logger.warning(f"Не удалось удалить сообщение: {e_del}")

                # Переходим к выбору рабочих дней
                bot.set_state(user_id, SpecialistStates.waiting_for_standard_days, chat_id)

                # Показываем клавиатуру выбора рабочих дней
                keyboard = get_working_days_keyboard([])
                bot.send_message(
                    chat_id,
                    f"Настройка расписания на {data['target_month_str']}.\n"
                    "Выберите рабочие дни недели:",
                    reply_markup=keyboard
                )

            bot.answer_callback_query(call.id)
        except Exception as e:
            logger.error(f"Ошибка process_month_selection: {e}", exc_info=True)
            bot.answer_callback_query(call.id, "Ошибка при выборе месяца")
            bot.delete_state(call.from_user.id, call.message.chat.id)

    @bot.callback_query_handler(func=lambda call: call.data == "confirm_schedule_change", 
                               state=SpecialistStates.waiting_for_month_selection)
    def confirm_schedule_change(call):
        """
        Подтверждение изменения расписания на выбранный месяц
        """
        try:
            user_id = call.from_user.id
            chat_id = call.message.chat.id

            # Удаляем сообщение с подтверждением
            try:
                bot.delete_message(chat_id, call.message.message_id)
            except Exception as e_del:
                logger.warning(f"Не удалось удалить сообщение: {e_del}")

            # Переходим к выбору рабочих дней
            bot.set_state(user_id, SpecialistStates.waiting_for_standard_days, chat_id)

            # Показываем клавиатуру выбора рабочих дней
            keyboard = get_working_days_keyboard([])

            with bot.retrieve_data(user_id, chat_id) as data:
                target_month_str = data.get('target_month_str', 'выбранный месяц')
                has_client_bookings = data.get('has_client_bookings', False)

            message_text = f"Настройка расписания на {target_month_str}.\n"

            if has_client_bookings:
                message_text += "⚠️ Внимание! Существующие записи клиентов будут отменены.\n\n"

            message_text += "Выберите рабочие дни недели:"

            bot.send_message(
                chat_id,
                message_text,
                reply_markup=keyboard
            )

            bot.answer_callback_query(call.id)
        except Exception as e:
            logger.error(f"Ошибка confirm_schedule_change: {e}", exc_info=True)
            bot.answer_callback_query(call.id, "Ошибка при подтверждении изменения")
            bot.delete_state(call.from_user.id, call.message.chat.id)

    @bot.callback_query_handler(func=lambda call: call.data == "cancel_schedule_change", 
                               state=SpecialistStates.waiting_for_month_selection)
    def cancel_schedule_change(call):
        """
        Отмена изменения расписания
        """
        try:
            user_id = call.from_user.id
            chat_id = call.message.chat.id

            # Сбрасываем состояние
            bot.delete_state(user_id, chat_id)

            # Возвращаемся в меню
            bot.send_message(
                chat_id,
                "Изменение расписания отменено.",
                reply_markup=get_specialist_menu_keyboard()
            )

            # Удаляем сообщение с подтверждением
            try:
                bot.delete_message(chat_id, call.message.message_id)
            except Exception as e_del:
                logger.warning(f"Не удалось удалить сообщение: {e_del}")

            bot.answer_callback_query(call.id)
        except Exception as e:
            logger.error(f"Ошибка cancel_schedule_change: {e}", exc_info=True)
            bot.answer_callback_query(call.id, "Ошибка при отмене")

    @bot.callback_query_handler(func=lambda call: call.data == "use_special_days", 
                               state=SpecialistStates.waiting_for_month_selection)
    def switch_to_special_days(call):
        """
        Переход к настройке особых дней вместо изменения расписания
        """
        try:
            user_id = call.from_user.id
            chat_id = call.message.chat.id

            # Сбрасываем состояние
            bot.delete_state(user_id, chat_id)

            # Удаляем сообщение с подтверждением
            try:
                bot.delete_message(chat_id, call.message.message_id)
            except Exception as e_del:
                logger.warning(f"Не удалось удалить сообщение: {e_del}")

            # Имитируем вызов функции настройки особых дней
            configure_special_days(types.Message(
                message_id=0,
                from_user=call.from_user,
                date=0,
                chat=types.Chat(
                    id=chat_id,
                    type='private'
                ),
                content_type='text',
                options={},
                json_string=''
            ))

            bot.answer_callback_query(call.id)
        except Exception as e:
            logger.error(f"Ошибка switch_to_special_days: {e}", exc_info=True)
            bot.answer_callback_query(call.id, "Ошибка при переходе к особым дням")
            bot.send_message(chat_id, "Произошла ошибка. Попробуйте выбрать 'Настроить особые дни' из меню.")

    @bot.callback_query_handler(func=lambda call: call.data.startswith("toggle_work_"),
                                state=SpecialistStates.waiting_for_standard_days)
    def toggle_working_day(call):
        """
        Помечаем/снимаем галочку с выбранного дня недели
        """
        try:
            day = call.data.replace("toggle_work_", "")
            user_id = call.from_user.id

            with bot.retrieve_data(user_id, call.message.chat.id) as data:
                working_days = data.get('working_days', [])
                if day in working_days:
                    working_days.remove(day)
                else:
                    working_days.append(day)
                data['working_days'] = working_days

            # Обновляем клавиатуру
            keyboard = get_working_days_keyboard(selected_days=working_days)
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=keyboard)
            bot.answer_callback_query(call.id)
        except Exception as e:
            logger.error(f"Ошибка toggle_working_day: {e}", exc_info=True)
            bot.answer_callback_query(call.id, "Ошибка. Повторите позже.")

    @bot.callback_query_handler(func=lambda call: call.data == "working_days_done",
                                state=SpecialistStates.waiting_for_standard_days)
    def finish_working_days_selection(call):
        """
        Завершили выбор рабочих дней
        """
        try:
            user_id = call.from_user.id
            chat_id = call.message.chat.id

            with bot.retrieve_data(user_id, chat_id) as data:
                wd = data.get('working_days', [])

            if not wd:
                bot.answer_callback_query(call.id, "Вы не выбрали ни одного дня.")
                return

            bot.edit_message_text(
                text=f"Вы выбрали рабочие дни: {', '.join(wd)}",
                chat_id=chat_id,
                message_id=call.message.message_id
            )
            bot.answer_callback_query(call.id)

            bot.send_message(
                chat_id,
                "Введите время начала рабочего дня (например, 09:00):"
            )

            bot.set_state(user_id, SpecialistStates.waiting_for_standard_start, chat_id)
        except Exception as e:
            logger.error(f"Ошибка finish_working_days_selection: {e}", exc_info=True)
            bot.answer_callback_query(call.id, "Ошибка. Повторите позже.")

    @bot.message_handler(state=SpecialistStates.waiting_for_standard_start)
    def process_standard_start(message):
        try:
            if message.text == "🔙 Вернуться в начало":
                bot.delete_state(message.from_user.id, message.chat.id)
                from utils.keyboards import get_start_keyboard
                bot.send_message(
                    message.chat.id,
                    "Вы вернулись в начало. Выберите свою роль:",
                    reply_markup=get_start_keyboard()
                )
                return

            start_time = message.text.strip()
            # Проверка формата
            try:
                datetime.strptime(start_time, "%H:%M")
            except Exception:
                bot.send_message(message.chat.id, "Неверный формат. Введите время начала в формате HH:MM (например, 09:00):")
                return

            with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
                data['standard_start'] = start_time

            bot.set_state(message.from_user.id, SpecialistStates.waiting_for_standard_end, message.chat.id)
            bot.send_message(message.chat.id, "Введите время окончания рабочего дня (например, 18:00):")
        except Exception as e:
            logger.error(f"Ошибка process_standard_start: {e}", exc_info=True)
            bot.send_message(message.chat.id, "Ошибка. Повторите позже.")

    @bot.message_handler(state=SpecialistStates.waiting_for_standard_end)
    def process_standard_end(message):
        try:
            if message.text == "🔙 Вернуться в начало":
                bot.delete_state(message.from_user.id, message.chat.id)
                from utils.keyboards import get_start_keyboard
                bot.send_message(
                    message.chat.id,
                    "Вы вернулись в начало. Выберите свою роль:",
                    reply_markup=get_start_keyboard()
                )
                return

            end_time = message.text.strip()
            try:
                end_dt = datetime.strptime(end_time, "%H:%M")

                # Получаем время начала для проверки
                with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
                    start_time = data.get('standard_start', '')

                start_dt = datetime.strptime(start_time, "%H:%M")

                # Проверяем, что конец позже начала
                if end_dt <= start_dt:
                    bot.send_message(message.chat.id, "Время окончания должно быть позже времени начала. Введите время окончания заново:")
                    return
            except ValueError:
                bot.send_message(message.chat.id, "Неверный формат. Введите время окончания в формате HH:MM (например, 18:00):")
                return

            with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
                data['standard_end'] = end_time

            bot.set_state(message.from_user.id, SpecialistStates.waiting_for_standard_break, message.chat.id)
            bot.send_message(message.chat.id, "Введите длительность перерыва между клиентами в минутах (0 если не нужен):")
        except Exception as e:
            logger.error(f"Ошибка process_standard_end: {e}", exc_info=True)
            bot.send_message(message.chat.id, "Ошибка. Повторите позже.")

    @bot.message_handler(state=SpecialistStates.waiting_for_standard_break)
    def process_standard_break(message):
        try:
            if message.text == "🔙 Вернуться в начало":
                bot.delete_state(message.from_user.id, message.chat.id)
                from utils.keyboards import get_start_keyboard
                bot.send_message(
                    message.chat.id,
                    "Вы вернулись в начало. Выберите свою роль:",
                    reply_markup=get_start_keyboard()
                )
                return

            break_str = message.text.strip()
            if not break_str.isdigit():
                bot.send_message(message.chat.id, "Введите число (0 или больше).")
                return

            break_minutes = int(break_str)
            user_id = message.from_user.id

            with bot.retrieve_data(user_id, message.chat.id) as data:
                wd = data.get('working_days', [])
                start_time = data.get('standard_start', "")
                end_time = data.get('standard_end', "")
                target_year = data.get('target_year')
                target_month = data.get('target_month')
                target_month_str = data.get('target_month_str', '')
                has_existing_schedule = data.get('has_existing_schedule', False)
                has_client_bookings = data.get('has_client_bookings', False)

            # Проверяем, что у нас есть специалист
            specialist = sheets_service.get_specialist_by_telegram_id(user_id)
            if not specialist:
                bot.send_message(message.chat.id, "Ошибка: специалист не найден.")
                bot.delete_state(user_id, message.chat.id)
                return

            spec_id = specialist['id']

            # Если есть существующее расписание, нужно его очистить
            if has_existing_schedule:
                # Получаем первый и последний день месяца
                if target_month == 12:
                    next_year = target_year + 1
                    next_month = 1
                else:
                    next_year = target_year
                    next_month = target_month + 1

                start_date = datetime(target_year, target_month, 1).date()
                end_date = datetime(next_year, next_month, 1).date() - timedelta(days=1)

                # Получаем все слоты
                all_slots = sheets_service.schedule_sheet.get_all_records()

                # Находим индексы строк для удаления
                rows_to_update = []
                for idx, slot in enumerate(all_slots, start=2):  # +2 т.к. первая строка - заголовки
                    if (str(slot.get('id_специалиста')) == str(spec_id) and 
                        start_date <= datetime.strptime(slot.get('Дата', '1970-01-01'), '%Y-%m-%d').date() <= end_date):
                        # Если это занятая запись - отменяем её
                        if slot.get('Статус') == 'Занято' and slot.get('id_клиента'):
                            sheets_service.cancel_appointment(slot['id'])

                # Очищаем все существующие слоты для этого месяца и специалиста
                sheets_service.clear_month_schedule(spec_id, target_year, target_month)

            # Проверяем часовой пояс специалиста
            tz = specialist.get('Часовой пояс', 'Europe/Moscow')

            # Генерируем расписание на указанный месяц
            text_result = (f"Стандартное расписание на {target_month_str} настроено:\n"
                           f"Рабочие дни: {', '.join(wd)}\n"
                           f"Часы: {start_time} - {end_time}\n"
                           f"Перерыв: {break_minutes} мин\n\n"
                           f"Генерирую слоты. Пожалуйста подождите ...")

            bot.send_message(message.chat.id, text_result)

            # Генерируем расписание на выбранный месяц
            sheets_service.generate_specific_month_schedule(
                spec_id, wd, start_time, end_time, break_minutes, 
                target_year, target_month
            )

            # Возвращаемся в меню
            bot.send_message(
                message.chat.id,
                f"Расписание на {target_month_str} успешно сгенерировано!",
                reply_markup=get_specialist_menu_keyboard()
            )

            # Если были отменены записи клиентов, отправляем уведомление
            if has_client_bookings:
                bot.send_message(
                    message.chat.id,
                    "⚠️ Внимание! Все существующие записи клиентов на выбранный период были отменены."
                )

            bot.delete_state(user_id, message.chat.id)
        except Exception as e:
            logger.error(f"Ошибка process_standard_break: {e}", exc_info=True)
            bot.send_message(message.chat.id, "Ошибка. Повторите позже.")
            bot.delete_state(message.from_user.id, message.chat.id)

    # --- Настройка особых дней ---
    @bot.message_handler(func=lambda m: m.text == "📌 Настроить особые дни")
    def configure_special_days(message):
        """
        Переход к настройке особых дней через календарь.
        """
        try:
            user_id = message.from_user.id
            specialist = sheets_service.get_specialist_by_telegram_id(user_id)

            if not specialist:
                bot.send_message(
                    message.chat.id,
                    "Вы не зарегистрированы как специалист.",
                    reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add(
                        types.KeyboardButton("🔙 Вернуться в начало")
                    )
                )
                return

            today = date.today()
            keyboard = get_calendar_keyboard(today.year, today.month, selected_dates=[])

            bot.send_message(
                message.chat.id,
                "Выберите даты, для которых хотите установить особое расписание (отмечая галочкой), затем нажмите 'Готово'.",
                reply_markup=keyboard
            )

            bot.set_state(user_id, SpecialistStates.waiting_for_special_date, message.chat.id)

            with bot.retrieve_data(user_id, message.chat.id) as data:
                data['special_dates'] = []
        except Exception as e:
            logger.error(f"Ошибка configure_special_days: {e}", exc_info=True)
            bot.send_message(message.chat.id, "Ошибка. Повторите позже.")

    @bot.callback_query_handler(func=lambda call: call.data.startswith("calendar_nav_"),
                                state=SpecialistStates.waiting_for_special_date)
    def calendar_nav_callback(call):
        """
        Листание месяцев в календаре при настройке особых дней
        """
        try:
            _, year_str, month_str = call.data.split('_', 2)
            year = int(year_str)
            month = int(month_str)

            with bot.retrieve_data(call.from_user.id, call.message.chat.id) as data:
                selected_dates = data.get('special_dates', [])

            keyboard = get_calendar_keyboard(year, month, selected_dates=selected_dates)

            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=keyboard)
            bot.answer_callback_query(call.id)
        except Exception as e:
            logger.error(f"Ошибка листания календаря (особые дни): {e}", exc_info=True)
            bot.answer_callback_query(call.id, "Ошибка.")

    @bot.callback_query_handler(func=lambda call: call.data.startswith("calendar_select_"),
                                state=SpecialistStates.waiting_for_special_date)
    def select_special_date(call):
        """
        Выбор или отмена выбора конкретной даты
        """
        try:
            date_str = call.data.replace("calendar_select_", "")
            user_id = call.from_user.id
            chat_id = call.message.chat.id

            with bot.retrieve_data(user_id, chat_id) as data:
                selected_dates = data.get('special_dates', [])
                if date_str in selected_dates:
                    selected_dates.remove(date_str)
                else:
                    selected_dates.append(date_str)
                data['special_dates'] = selected_dates

            # Перерисовываем календарь
            parts = date_str.split('-')
            year = int(parts[0])
            month = int(parts[1])

            keyboard = get_calendar_keyboard(year, month, selected_dates=selected_dates)

            bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=keyboard)
            bot.answer_callback_query(call.id)
        except Exception as e:
            logger.error(f"Ошибка выбора даты (особые дни): {e}", exc_info=True)
            bot.answer_callback_query(call.id, "Ошибка.")

    @bot.callback_query_handler(func=lambda call: call.data == "calendar_done",
                                state=SpecialistStates.waiting_for_special_date)
    def finish_special_days_selection(call):
        """
        Завершение выбора дат. Предлагаем закрыть эти даты или указать особые часы.
        """
        try:
            user_id = call.from_user.id
            chat_id = call.message.chat.id

            with bot.retrieve_data(user_id, chat_id) as data:
                selected_dates = data.get('special_dates', [])

            if not selected_dates:
                bot.answer_callback_query(call.id, "Вы не выбрали ни одной даты.")
                return

            # Сортируем даты
            selected_dates.sort()

            # Форматируем даты для отображения
            formatted_dates = []
            for d in selected_dates:
                try:
                    date_obj = datetime.strptime(d, '%Y-%m-%d')
                    formatted_date = date_obj.strftime('%d.%m.%Y')
                    formatted_dates.append(formatted_date)
                except:
                    formatted_dates.append(d)

            bot.edit_message_text(
                text=f"Выбранные даты: {', '.join(formatted_dates)}",
                chat_id=chat_id,
                message_id=call.message.message_id
            )
            bot.answer_callback_query(call.id)

            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            markup.add("🔒 Закрыть выбранные дни", "🕒 Указать особые часы для выбранных дней")
            markup.add("🔙 Назад в меню специалиста")

            bot.send_message(
                chat_id,
                "Что сделать с этими особыми днями?",
                reply_markup=markup
            )

            bot.set_state(user_id, SpecialistStates.waiting_for_special_option, chat_id)
        except Exception as e:
            logger.error(f"Ошибка finish_special_days_selection: {e}", exc_info=True)
            bot.answer_callback_query(call.id, "Ошибка.")

    @bot.message_handler(state=SpecialistStates.waiting_for_special_option)
    def special_days_option(message):
        """
        Обработка выбранного действия над особыми днями:
         - Закрыть
         - Указать особые часы
        """
        try:
            text = message.text.strip()
            user_id = message.from_user.id
            chat_id = message.chat.id

            if text == "🔙 Назад в меню специалиста":
                bot.delete_state(user_id, chat_id)
                bot.send_message(
                    chat_id,
                    "Возвращаемся в меню специалиста",
                    reply_markup=get_specialist_menu_keyboard()
                )
                return

            with bot.retrieve_data(user_id, chat_id) as data:
                selected_dates = data.get('special_dates', [])

            if text == "🔒 Закрыть выбранные дни":
                # Получаем данные специалиста
                specialist = sheets_service.get_specialist_by_telegram_id(user_id)
                if not specialist:
                    bot.send_message(chat_id, "Не найден специалист. Ошибка.")
                    bot.delete_state(user_id, chat_id)
                    return

                sid = specialist['id']

                # Закрываем каждую выбранную дату
                success_count = 0
                for d in selected_dates:
                    if sheets_service.close_day_slots(sid, d):
                        success_count += 1

                if success_count > 0:
                    bot.send_message(
                        chat_id,
                        f"Выбранные дни успешно закрыты ({success_count} из {len(selected_dates)}).",
                        reply_markup=get_specialist_menu_keyboard()
                    )
                else:
                    bot.send_message(
                        chat_id,
                        "Не удалось закрыть выбранные дни. Возможно, для них нет активных слотов.",
                        reply_markup=get_specialist_menu_keyboard()
                    )

                bot.delete_state(user_id, chat_id)

            elif text == "🕒 Указать особые часы для выбранных дней":
                bot.send_message(chat_id, "Введите время начала работы (например 10:00):")
                bot.set_state(user_id, SpecialistStates.waiting_for_special_start, chat_id)
            else:
                bot.send_message(chat_id, "Неверная команда. Выберите из меню.")
        except Exception as e:
            logger.error(f"Ошибка special_days_option: {e}", exc_info=True)
            bot.send_message(message.chat.id, "Произошла ошибка. Попробуйте позже.")
            bot.delete_state(message.from_user.id, message.chat.id)

    @bot.message_handler(state=SpecialistStates.waiting_for_special_start)
    def process_special_start_time(message):
        try:
            if message.text == "🔙 Назад в меню специалиста":
                bot.delete_state(message.from_user.id, message.chat.id)
                bot.send_message(
                    message.chat.id,
                    "Возвращаемся в меню специалиста",
                    reply_markup=get_specialist_menu_keyboard()
                )
                return

            start_time = message.text.strip()
            # Валидация
            try:
                datetime.strptime(start_time, "%H:%M")
            except:
                bot.send_message(
                    message.chat.id, 
                    "Неверный формат времени. Введите в формате ЧЧ:ММ (например, 10:00):"
                )
                return

            user_id = message.from_user.id
            with bot.retrieve_data(user_id, message.chat.id) as data:
                data['special_start'] = start_time

            bot.set_state(user_id, SpecialistStates.waiting_for_special_end, message.chat.id)
            bot.send_message(message.chat.id, "Введите время окончания (например 16:00):")
        except Exception as e:
            logger.error(f"Ошибка process_special_start_time: {e}", exc_info=True)
            bot.send_message(message.chat.id, "Ошибка. Повторите позже.")

    @bot.message_handler(state=SpecialistStates.waiting_for_special_end)
    def process_special_end_time(message):
        try:
            if message.text == "🔙 Назад в меню специалиста":
                bot.delete_state(message.from_user.id, message.chat.id)
                bot.send_message(
                    message.chat.id,
                    "Возвращаемся в меню специалиста",
                    reply_markup=get_specialist_menu_keyboard()
                )
                return

            end_time = message.text.strip()

            # Валидация
            try:
                end_dt = datetime.strptime(end_time, "%H:%M")

                # Получаем время начала для проверки
                with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
                    start_time = data.get('special_start', '')
                    selected_dates = data.get('special_dates', [])

                start_dt = datetime.strptime(start_time, "%H:%M")

                # Проверяем, что конец позже начала
                if end_dt <= start_dt:
                    bot.send_message(
                        message.chat.id, 
                        "Время окончания должно быть позже времени начала. Введите заново:"
                    )
                    return
            except ValueError:
                bot.send_message(
                    message.chat.id, 
                    "Неверный формат времени. Введите в формате ЧЧ:ММ (например, 16:00):"
                )
                return

            user_id = message.from_user.id
            # Получаем данные специалиста
            specialist = sheets_service.get_specialist_by_telegram_id(user_id)
            if not specialist:
                bot.send_message(message.chat.id, "Не найден специалист. Ошибка.")
                bot.delete_state(user_id, message.chat.id)
                return

            # Получаем ID специалиста и данные о выбранных датах
            sid = specialist['id']
            with bot.retrieve_data(user_id, message.chat.id) as data:
                selected_dates = data.get('special_dates', [])
                start_time = data.get('special_start', '')

            if not selected_dates:
                bot.send_message(message.chat.id, "Ошибка: не выбраны даты.")
                bot.delete_state(user_id, message.chat.id)
                return

            # Сначала закрываем все слоты для выбранных дат
            for d in selected_dates:
                sheets_service.close_day_slots(sid, d)

            # Создаем новые слоты для каждой даты
            for date_str in selected_dates:
                # Конвертируем время начала и конца в минуты
                start_h, start_m = map(int, start_time.split(':'))
                end_h, end_m = map(int, end_time.split(':'))

                start_total = start_h * 60 + start_m
                end_total = end_h * 60 + end_m

                # Создаем слоты с шагом 30 минут
                while start_total < end_total:
                    hh = start_total // 60
                    mm = start_total % 60
                    time_str = f"{hh:02d}:{mm:02d}"
                    sheets_service.add_schedule_slot(date_str, time_str, sid)
                    start_total += 30

            # Форматируем даты для отображения
            formatted_dates = []
            for d in selected_dates:
                try:
                    date_obj = datetime.strptime(d, '%Y-%m-%d')
                    formatted_date = date_obj.strftime('%d.%m.%Y')
                    formatted_dates.append(formatted_date)
                except:
                    formatted_dates.append(d)

            # Сортируем даты
            formatted_dates.sort()

            bot.send_message(
                message.chat.id,
                f"Особые часы для {len(selected_dates)} дней указаны: {start_time} - {end_time}\n"
                f"Выбранные даты: {', '.join(formatted_dates)}",
                reply_markup=get_specialist_menu_keyboard()
            )

            bot.delete_state(user_id, message.chat.id)
        except Exception as e:
            logger.error(f"Ошибка process_special_end_time: {e}", exc_info=True)
            bot.send_message(message.chat.id, "Ошибка. Повторите позже.")
            bot.delete_state(message.from_user.id, message.chat.id)

    # =====================
    # 6. Настройка услуг
    # =====================
    @bot.message_handler(func=lambda m: m.text == "📋 Настройка услуг")
    def services_menu(message):
        """
        Меню управления услугами специалиста
        """
        try:
            user_id = message.from_user.id
            specialist = sheets_service.get_specialist_by_telegram_id(user_id)

            if not specialist:
                bot.send_message(
                    message.chat.id,
                    "Вы не зарегистрированы как специалист.",
                    reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add(
                        types.KeyboardButton("🔙 Вернуться в начало")
                    )
                )
                return

            markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
            markup.add("➕ Добавить услугу")
            markup.add("📝 Редактировать услуги")
            markup.add("🔙 Назад в меню специалиста")

            bot.send_message(message.chat.id, "Управление услугами. Выберите действие:", reply_markup=markup)
        except Exception as e:
            logger.error(f"Ошибка services_menu: {e}", exc_info=True)
            bot.send_message(message.chat.id, "Произошла ошибка. Попробуйте позже.")

    @bot.message_handler(func=lambda m: m.text == "➕ Добавить услугу")
    def add_service_start(message):
        try:
            user_id = message.from_user.id
            specialist = sheets_service.get_specialist_by_telegram_id(user_id)

            if not specialist:
                bot.send_message(
                    message.chat.id,
                    "Вы не зарегистрированы как специалист.",
                    reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add(
                        types.KeyboardButton("🔙 Вернуться в начало")
                    )
                )
                return

            bot.set_state(user_id, SpecialistStates.waiting_for_service_name, message.chat.id)

            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            markup.add("🔙 Назад в меню специалиста")

            bot.send_message(message.chat.id, "Введите название услуги (например, 'Массаж спины'):", reply_markup=markup)
        except Exception as e:
            logger.error(f"Ошибка add_service_start: {e}", exc_info=True)
            bot.send_message(message.chat.id, "Произошла ошибка. Попробуйте позже.")

    @bot.message_handler(state=SpecialistStates.waiting_for_service_name)
    def process_service_name(message):
        try:
            if message.text == "🔙 Назад в меню специалиста":
                bot.delete_state(message.from_user.id, message.chat.id)
                bot.send_message(
                    message.chat.id,
                    "Возвращаемся в меню специалиста",
                    reply_markup=get_specialist_menu_keyboard()
                )
                return

            name = message.text.strip()
            if len(name) < 2:
                bot.send_message(message.chat.id, "Слишком короткое название. Попробуйте снова:")
                return

            with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
                data['service_name'] = name

            bot.set_state(message.from_user.id, SpecialistStates.waiting_for_service_duration, message.chat.id)

            # Предлагаем варианты продолжительности
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            for duration in [30, 60, 90, 120]:
                markup.add(types.KeyboardButton(str(duration)))
            markup.add("🔙 Назад в меню специалиста")

            bot.send_message(
                message.chat.id, 
                "Укажите продолжительность услуги в минутах (число):",
                reply_markup=markup
            )
        except Exception as e:
            logger.error(f"Ошибка process_service_name: {e}", exc_info=True)
            bot.send_message(message.chat.id, "Произошла ошибка. Попробуйте позже.")
            bot.delete_state(message.from_user.id, message.chat.id)

    @bot.message_handler(state=SpecialistStates.waiting_for_service_duration)
    def process_service_duration(message):
        try:
            if message.text == "🔙 Назад в меню специалиста":
                bot.delete_state(message.from_user.id, message.chat.id)
                bot.send_message(
                    message.chat.id,
                    "Возвращаемся в меню специалиста",
                    reply_markup=get_specialist_menu_keyboard()
                )
                return

            text = message.text.strip()
            if not text.isdigit():
                bot.send_message(message.chat.id, "Введите число минут (например, 60).")
                return

            duration = int(text)
            if duration < 30:
                bot.send_message(message.chat.id, "Минимальная продолжительность — 30 минут. Попробуйте снова:")
                return

            with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
                data['service_duration'] = duration

            bot.set_state(message.from_user.id, SpecialistStates.waiting_for_service_price, message.chat.id)

            # Предлагаем варианты стоимости
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            for price in [0, 1000, 1500, 2000, 2500, 3000]:
                markup.add(types.KeyboardButton(str(price)))
            markup.add("🔙 Назад в меню специалиста")

            bot.send_message(
                message.chat.id, 
                "Укажите стоимость услуги в рублях (число), либо 0 если не фиксирована:",
                reply_markup=markup
            )
        except Exception as e:
            logger.error(f"Ошибка process_service_duration: {e}", exc_info=True)
            bot.send_message(message.chat.id, "Произошла ошибка. Попробуйте позже.")
            bot.delete_state(message.from_user.id, message.chat.id)

    @bot.message_handler(state=SpecialistStates.waiting_for_service_price)
    def process_service_price(message):
        try:
            if message.text == "🔙 Назад в меню специалиста":
                bot.delete_state(message.from_user.id, message.chat.id)
                bot.send_message(
                    message.chat.id,
                    "Возвращаемся в меню специалиста",
                    reply_markup=get_specialist_menu_keyboard()
                )
                return

            text = message.text.strip()
            if not text.isdigit():
                bot.send_message(message.chat.id, "Введите число (например, 1500).")
                return

            price = int(text)
            user_id = message.from_user.id

            # Получаем данные специалиста
            specialist = sheets_service.get_specialist_by_telegram_id(user_id)
            if not specialist:
                bot.send_message(message.chat.id, "Специалист не найден, попробуйте позже.")
                bot.delete_state(user_id, message.chat.id)
                return

            with bot.retrieve_data(user_id, message.chat.id) as data:
                service_name = data['service_name']
                duration = data['service_duration']

            # Получаем ID специалиста
            spec_id = specialist['id']

            # Сохраняем услугу в Google Sheets (лист "Услуги")
            services_sheet = None
            try:
                services_sheet = sheets_service.spreadsheet.worksheet("Услуги")
            except:
                # Создаем, если нет
                services_sheet = sheets_service.spreadsheet.add_worksheet(title='Услуги', rows=1000, cols=6)
                services_sheet.append_row(["id_специалиста", "Название", "Продолжительность", "Стоимость"])

            # Проверим, существует ли уже такая услуга
            all_svc = services_sheet.get_all_records()
            duplicate = False
            for svc in all_svc:
                if (str(svc.get('id_специалиста', '')) == str(spec_id) and 
                    svc.get('Название', '') == service_name):
                    duplicate = True
                    break

            if duplicate:
                bot.send_message(
                    message.chat.id,
                    f"Услуга с названием '{service_name}' уже существует. Пожалуйста, выберите другое название.",
                    reply_markup=get_specialist_menu_keyboard()
                )
                bot.delete_state(user_id, message.chat.id)
                return

            # Добавляем новую услугу
            new_row = [spec_id, service_name, duration, price]
            services_sheet.append_row(new_row)

            bot.send_message(
                message.chat.id,
                f"Услуга '{service_name}' продолжительностью {duration} мин и стоимостью {price} ₽ добавлена!",
                reply_markup=get_specialist_menu_keyboard()
            )

            bot.delete_state(user_id, message.chat.id)
        except Exception as e:
            logger.error(f"Ошибка process_service_price: {e}", exc_info=True)
            bot.send_message(message.chat.id, "Произошла ошибка. Попробуйте позже.")
            bot.delete_state(message.from_user.id, message.chat.id)

    @bot.message_handler(func=lambda m: m.text == "📝 Редактировать услуги")
    def edit_services(message):
        """
        Показываем список услуг и возможность удалить/изменить
        """
        try:
            user_id = message.from_user.id
            specialist = sheets_service.get_specialist_by_telegram_id(user_id)

            if not specialist:
                bot.send_message(
                    message.chat.id,
                    "Вы не зарегистрированы как специалист.",
                    reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add(
                        types.KeyboardButton("🔙 Вернуться в начало")
                    )
                )
                return

            # Получаем ID специалиста
            sid = specialist['id']

            # Получаем список услуг специалиста
            services = sheets_service.get_specialist_services(sid)

            if not services:
                bot.send_message(
                    message.chat.id, 
                    "У вас нет услуг. Сначала добавьте услуги через меню 'Добавить услугу'.", 
                    reply_markup=get_specialist_menu_keyboard()
                )
                return

            # Формируем текст и клавиатуру
            text = "Ваши услуги:\n"
            kb = types.InlineKeyboardMarkup()

            for i, svc in enumerate(services, start=1):
                name = svc.get('Название', 'Без названия')
                dur = svc.get('Продолжительность', 30)
                cost = svc.get('Стоимость', 0)

                text += f"{i}. {name} ({dur} мин, {cost} ₽)\n"

                # Создаем уникальный идентификатор для каждой услуги
                # Поскольку id_специалиста + название могут быть уникальным идентификатором
                service_id = f"{sid}_{name}"
                kb.add(
                    types.InlineKeyboardButton(f"❌ Удалить {i}", callback_data=f"delservice_{service_id}")
                )

            kb.add(types.InlineKeyboardButton("🔙 Закрыть", callback_data="close_edit_services"))

            bot.send_message(message.chat.id, text, reply_markup=kb)
        except Exception as e:
            logger.error(f"Ошибка edit_services: {e}", exc_info=True)
            bot.send_message(message.chat.id, "Произошла ошибка. Попробуйте позже.")

    @bot.callback_query_handler(func=lambda call: call.data.startswith("delservice_"))
    def delete_service(call):
        """
        Удаление услуги
        """
        try:
            service_id = call.data.split("_", 1)[1]

            # Разбираем ID услуги
            try:
                sid, name = service_id.split("_", 1)
            except:
                bot.answer_callback_query(call.id, "Ошибка формата ID услуги")
                return

            # Проверяем, что пользователь - специалист с указанным ID
            user_id = call.from_user.id
            specialist = sheets_service.get_specialist_by_telegram_id(user_id)

            if not specialist or str(specialist['id']) != str(sid):
                bot.answer_callback_query(call.id, "У вас нет прав на удаление этой услуги.")
                return

            # Получаем список услуг специалиста
            services = sheets_service.get_specialist_services(sid)

            # Ищем услугу с таким названием
            target = None
            for svc in services:
                if svc.get('Название') == name:
                    target = svc
                    break

            if not target:
                bot.answer_callback_query(call.id, "Услуга не найдена.")
                return

            # Удаляем услугу из листа "Услуги"
            services_sheet = sheets_service.spreadsheet.worksheet("Услуги")
            all_rows = services_sheet.get_all_values()  # Включая заголовок

            # Ищем строку, совпадающую с услугой
            target_row = None
            for row_idx, row in enumerate(all_rows, start=1):
                if row_idx == 1:  # Пропускаем заголовок
                    continue

                if (len(row) >= 3 and 
                    str(row[0]) == str(sid) and 
                    row[1] == name):
                    target_row = row_idx
                    break

            if target_row:
                # Удаляем строку
                services_sheet.delete_row(target_row)
                bot.answer_callback_query(call.id, f"Услуга '{name}' удалена.")

                # Обновляем список услуг
                new_services = sheets_service.get_specialist_services(sid)

                if not new_services:
                    # Если услуг больше нет
                    try:
                        bot.edit_message_text(
                            "У вас больше нет услуг. Добавьте услуги через меню 'Добавить услугу'.",
                            call.message.chat.id,
                            call.message.message_id
                        )
                    except Exception as e_edit:
                        logger.warning(f"Ошибка при обновлении сообщения: {e_edit}")
                    return

                # Формируем новый текст и клавиатуру
                text = "Ваши услуги:\n"
                kb = types.InlineKeyboardMarkup()

                for i, svc in enumerate(new_services, start=1):
                    svc_name = svc.get('Название', 'Без названия')
                    dur = svc.get('Продолжительность', 30)
                    cost = svc.get('Стоимость', 0)

                    text += f"{i}. {svc_name} ({dur} мин, {cost} ₽)\n"

                    service_id = f"{sid}_{svc_name}"
                    kb.add(
                        types.InlineKeyboardButton(f"❌ Удалить {i}", callback_data=f"delservice_{service_id}")
                    )

                kb.add(types.InlineKeyboardButton("🔙 Закрыть", callback_data="close_edit_services"))

                # Обновляем сообщение
                try:
                    bot.edit_message_text(
                        text,
                        call.message.chat.id,
                        call.message.message_id,
                        reply_markup=kb
                    )
                except Exception as e_edit:
                    logger.warning(f"Ошибка при обновлении сообщения: {e_edit}")
            else:
                bot.answer_callback_query(call.id, "Не удалось найти услугу в таблице.")
        except Exception as e:
            logger.error(f"Ошибка delete_service: {e}", exc_info=True)
            bot.answer_callback_query(call.id, "Ошибка при удалении услуги.")

    @bot.callback_query_handler(func=lambda call: call.data == "close_edit_services")
    def close_edit_services(call):
        """
        Закрыть меню редактирования
        """
        try:
            bot.edit_message_text("Редактирование услуг завершено.", call.message.chat.id, call.message.message_id)
            bot.answer_callback_query(call.id)
        except Exception as e:
            logger.error(f"Ошибка close_edit_services: {e}", exc_info=True)
            bot.answer_callback_query(call.id, "Ошибка.")

    # =====================
    # 7. Мои клиенты
    # =====================
    @bot.message_handler(func=lambda m: m.text == "👥 Мои клиенты")
    def show_my_clients(message):
        """
        Показываем список клиентов, прикрепленных к специалисту
        """
        try:
            user_id = message.from_user.id
            specialist = sheets_service.get_specialist_by_telegram_id(user_id)

            if not specialist:
                bot.send_message(
                    message.chat.id,
                    "Вы не зарегистрированы как специалист.",
                    reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add(
                        types.KeyboardButton("🔙 Вернуться в начало")
                    )
                )
                return

            # Получаем ID специалиста
            sid = specialist['id']

            # Получаем список всех клиентов
            all_clients = sheets_service.get_all_clients()

            # Фильтруем только клиентов этого специалиста
            my_clients = [c for c in all_clients if str(c.get('id_специалиста')) == str(sid)]

            if not my_clients:
                bot.send_message(
                    message.chat.id, 
                    "У вас пока нет клиентов. Поделитесь реферальной ссылкой с клиентами.", 
                    reply_markup=get_specialist_menu_keyboard()
                )
                return

            # Формируем текст со списком клиентов
            text = "Список ваших клиентов:\n"

            for i, cl in enumerate(my_clients, start=1):
                name = cl.get('Имя', 'Без имени')
                phone = cl.get('Телефон', '-')

                text += f"{i}. {name} | Тел: {phone}\n"

            # Добавляем информацию о реферальной ссылке
            ref_link = specialist.get('Реферальная', '')
            if ref_link:
                bot_username = bot.get_me().username
                if not ref_link.startswith("https://"):
                    ref_link = f"https://t.me/{bot_username}?start=ref{sid}"
                text += f"\nПригласить клиентов: {ref_link}"

            bot.send_message(message.chat.id, text, reply_markup=get_specialist_menu_keyboard())
        except Exception as e:
            logger.error(f"Ошибка show_my_clients: {e}", exc_info=True)
            bot.send_message(message.chat.id, "Произошла ошибка. Попробуйте позже.")
            # =====================
            # 8. Рассылка сообщений
            # =====================
            @bot.message_handler(func=lambda m: m.text == "📢 Рассылка сообщений")
            def broadcast_menu(message):
                """
                Выбор получателей
                """
                try:
                    user_id = message.from_user.id
                    specialist = sheets_service.get_specialist_by_telegram_id(user_id)

                    if not specialist:
                        bot.send_message(
                            message.chat.id,
                            "Вы не зарегистрированы как специалист.",
                            reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add(
                                types.KeyboardButton("🔙 Вернуться в начало")
                            )
                        )
                        return

                    # Получаем ID специалиста
                    sid = specialist['id']

                    # Получаем список всех клиентов
                    all_clients = sheets_service.get_all_clients()

                    # Фильтруем только клиентов этого специалиста
                    my_clients = [c for c in all_clients if str(c.get('id_специалиста')) == str(sid)]

                    if not my_clients:
                        bot.send_message(
                            message.chat.id, 
                            "У вас пока нет клиентов. Поделитесь реферальной ссылкой с клиентами.", 
                            reply_markup=get_specialist_menu_keyboard()
                        )
                        return

                    # Создаем клавиатуру для выбора получателей
                    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                    markup.add("👥 Все клиенты")
                    markup.add("📅 Клиенты с записями на эту неделю")
                    markup.add("📆 Клиенты с записями на выбранную дату")
                    markup.add("🔙 Назад в меню специалиста")

                    bot.set_state(user_id, SpecialistStates.waiting_for_recipients_choice, message.chat.id)
                    bot.send_message(message.chat.id, "Выберите получателей:", reply_markup=markup)
                except Exception as e:
                    logger.error(f"Ошибка broadcast_menu: {e}", exc_info=True)
                    bot.send_message(message.chat.id, "Произошла ошибка. Попробуйте позже.")

            @bot.message_handler(state=SpecialistStates.waiting_for_recipients_choice)
            def process_recipients_choice(message):
                try:
                    text = message.text.strip()
                    user_id = message.from_user.id
                    chat_id = message.chat.id

                    if text == "🔙 Назад в меню специалиста":
                        bot.delete_state(user_id, chat_id)
                        bot.send_message(chat_id, "Отменено.", reply_markup=get_specialist_menu_keyboard())
                        return

                    valid_choices = ["👥 Все клиенты", "📅 Клиенты с записями на эту неделю", "📆 Клиенты с записями на выбранную дату"]
                    if text not in valid_choices:
                        bot.send_message(chat_id, "Неверный выбор. Выберите из меню или вернитесь назад.")
                        return

                    with bot.retrieve_data(user_id, chat_id) as data:
                        data['broadcast_choice'] = text

                    # Если нужно уточнить дату, то спрашиваем
                    if text == "📆 Клиенты с записями на выбранную дату":
                        bot.set_state(user_id, SpecialistStates.waiting_for_broadcast_date, chat_id)

                        # Показываем календарь
                        today = date.today()
                        keyboard = get_calendar_keyboard(today.year, today.month)

                        bot.send_message(
                            chat_id, 
                            "Выберите дату для рассылки:", 
                            reply_markup=keyboard
                        )
                    else:
                        # Сразу переходим к запросу текста
                        bot.set_state(user_id, SpecialistStates.waiting_for_message_text, chat_id)

                        # Добавляем подсказки для текста сообщения
                        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                        markup.add("🔙 Назад в меню специалиста")

                        bot.send_message(
                            chat_id, 
                            "Введите текст сообщения для рассылки:", 
                            reply_markup=markup
                        )
                except Exception as e:
                    logger.error(f"Ошибка process_recipients_choice: {e}", exc_info=True)
                    bot.send_message(message.chat.id, "Произошла ошибка. Попробуйте позже.")
                    bot.delete_state(message.from_user.id, message.chat.id)

            @bot.message_handler(state=SpecialistStates.waiting_for_message_text)
            def process_broadcast_text(message):
                try:
                    text = message.text.strip()
                    user_id = message.from_user.id
                    chat_id = message.chat.id

                    if text == "🔙 Назад в меню специалиста":
                        bot.delete_state(user_id, chat_id)
                        bot.send_message(chat_id, "Рассылка отменена.", reply_markup=get_specialist_menu_keyboard())
                        return

                    if len(text) < 2:
                        bot.send_message(chat_id, "Сообщение слишком короткое. Введите подробнее:")
                        return

                    with bot.retrieve_data(user_id, chat_id) as data:
                        data['broadcast_text'] = text

                    bot.set_state(user_id, SpecialistStates.waiting_for_message_text_confirm, chat_id)

                    # Создаем клавиатуру для подтверждения
                    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
                    keyboard.add("✅ Отправить", "❌ Отмена")

                    bot.send_message(
                        chat_id, 
                        f"Подтвердите отправку сообщения:\n\n{text}", 
                        reply_markup=keyboard
                    )
                except Exception as e:
                    logger.error(f"Ошибка process_broadcast_text: {e}", exc_info=True)
                    bot.send_message(message.chat.id, "Произошла ошибка. Попробуйте позже.")
                    bot.delete_state(message.from_user.id, message.chat.id)

            @bot.message_handler(state=SpecialistStates.waiting_for_message_text_confirm)
            def confirm_broadcast(message):
                try:
                    choice = message.text.strip()
                    user_id = message.from_user.id
                    chat_id = message.chat.id

                    if choice == "❌ Отмена":
                        bot.delete_state(user_id, chat_id)
                        bot.send_message(chat_id, "Рассылка отменена.", reply_markup=get_specialist_menu_keyboard())
                        return

                    if choice != "✅ Отправить":
                        bot.send_message(chat_id, "Неверная команда. Нажмите ✅ Отправить или ❌ Отмена.")
                        return

                    # Выполняем рассылку
                    with bot.retrieve_data(user_id, chat_id) as data:
                        broadcast_choice = data.get('broadcast_choice', '')
                        broadcast_text = data.get('broadcast_text', '')
                        broadcast_date = data.get('broadcast_date', '')

                    # Получаем данные специалиста
                    specialist = sheets_service.get_specialist_by_telegram_id(user_id)
                    if not specialist:
                        bot.send_message(chat_id, "Специалист не найден.")
                        bot.delete_state(user_id, chat_id)
                        return

                    # Получаем ID специалиста
                    sid = specialist['id']

                    # Определяем список получателей
                    all_clients = sheets_service.get_all_clients()
                    final_recipients = []

                    if broadcast_choice == "👥 Все клиенты":
                        # Все клиенты этого специалиста
                        final_recipients = [c for c in all_clients if str(c.get('id_специалиста')) == str(sid)]

                    elif broadcast_choice == "📅 Клиенты с записями на эту неделю":
                        # Собираем клиентов, у которых запись в ближайшие 7 дней
                        today = date.today()
                        seven_days_later = today + timedelta(days=7)

                        # Получаем все слоты расписания
                        all_slots = sheets_service.schedule_sheet.get_all_records()

                        # Собираем ID клиентов с записями на ближайшие 7 дней
                        client_ids = set()
                        for slot in all_slots:
                            # Проверяем, что слот относится к этому специалисту
                            if str(slot.get('id_специалиста')) != str(sid):
                                continue

                            # Проверяем дату слота
                            slot_date_str = slot.get('Дата')
                            if not slot_date_str:
                                continue

                            try:
                                slot_date = datetime.strptime(slot_date_str, "%Y-%m-%d").date()
                                if today <= slot_date <= seven_days_later:
                                    if slot.get('id_клиента'):
                                        client_ids.add(str(slot['id_клиента']))
                            except:
                                pass

                        # Фильтруем клиентов по ID и специалисту
                        final_recipients = [
                            c for c in all_clients 
                            if str(c.get('id')) in client_ids and str(c.get('id_специалиста')) == str(sid)
                        ]

                    elif broadcast_choice == "📆 Клиенты с записями на выбранную дату":
                        # Конкретная дата
                        if not broadcast_date:
                            bot.send_message(chat_id, "Ошибка: дата не выбрана.")
                            bot.delete_state(user_id, chat_id)
                            return

                        # Получаем все слоты расписания
                        all_slots = sheets_service.schedule_sheet.get_all_records()

                        # Собираем ID клиентов с записями на выбранную дату
                        client_ids = set()
                        for slot in all_slots:
                            # Проверяем, что слот относится к этому специалисту
                            if str(slot.get('id_специалиста')) != str(sid):
                                continue

                            # Проверяем дату слота
                            if slot.get('Дата') == broadcast_date and slot.get('id_клиента'):
                                client_ids.add(str(slot['id_клиента']))

                        # Фильтруем клиентов по ID и специалисту
                        final_recipients = [
                            c for c in all_clients 
                            if str(c.get('id')) in client_ids and str(c.get('id_специалиста')) == str(sid)
                        ]

                    # Выполняем рассылку
                    count = 0
                    for cl in final_recipients:
                        # Проверяем наличие Telegram ID
                        tg_id = cl.get('Telegram_ID')
                        if tg_id:
                            try:
                                # Формируем персональное сообщение с именем клиента
                                personal_text = f"Сообщение от {specialist.get('Имя', 'Вашего специалиста')}:\n\n{broadcast_text}"
                                bot.send_message(int(tg_id), personal_text)
                                count += 1
                            except Exception as e:
                                logger.warning(f"Не удалось отправить сообщение клиенту {tg_id}: {e}")

                    # Завершаем рассылку
                    bot.delete_state(user_id, chat_id)

                    bot.send_message(
                        chat_id,
                        f"Сообщение отправлено {count} клиентам.",
                        reply_markup=get_specialist_menu_keyboard()
                    )
                except Exception as e:
                    logger.error(f"Ошибка confirm_broadcast: {e}", exc_info=True)
                    bot.send_message(message.chat.id, "Произошла ошибка. Попробуйте позже.")
                    bot.delete_state(message.from_user.id, message.chat.id)

            @bot.callback_query_handler(func=lambda call: call.data.startswith("calendar_select_"),
                                     state=SpecialistStates.waiting_for_broadcast_date)
            def select_broadcast_date(call):
                """
                Выбор даты для рассылки сообщений
                """
                try:
                    date_str = call.data.replace("calendar_select_", "")
                    user_id = call.from_user.id
                    chat_id = call.message.chat.id

                    # Сохраняем выбранную дату
                    with bot.retrieve_data(user_id, chat_id) as data:
                        data['broadcast_date'] = date_str

                    # Удаляем сообщение с календарем
                    try:
                        bot.delete_message(chat_id, call.message.message_id)
                    except Exception as e_del:
                        logger.warning(f"Не удалось удалить сообщение с календарем: {e_del}")

                    # Форматируем дату для красивого отображения
                    try:
                        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                        formatted_date = date_obj.strftime('%d.%m.%Y')
                    except:
                        formatted_date = date_str

                    # Переходим к запросу текста сообщения
                    bot.set_state(user_id, SpecialistStates.waiting_for_message_text, chat_id)

                    # Создаем клавиатуру
                    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                    markup.add("🔙 Назад в меню специалиста")

                    bot.send_message(
                        chat_id, 
                        f"Вы выбрали дату: {formatted_date}\nВведите текст сообщения для рассылки:", 
                        reply_markup=markup
                    )

                    bot.answer_callback_query(call.id)
                except Exception as e:
                    logger.error(f"Ошибка select_broadcast_date: {e}", exc_info=True)
                    bot.answer_callback_query(call.id, "Ошибка при выборе даты")
                    bot.delete_state(call.from_user.id, call.message.chat.id)

            # =====================
            # 9. Реферальная ссылка
            # =====================
            @bot.message_handler(func=lambda m: m.text == "🔗 Реферальная ссылка")
            def referral_link(message):
                """
                Показываем/генерируем реферальную ссылку, а также статистику
                """
                try:
                    user_id = message.from_user.id
                    specialist = sheets_service.get_specialist_by_telegram_id(user_id)

                    if not specialist:
                        bot.send_message(
                            message.chat.id,
                            "Вы не зарегистрированы как специалист.",
                            reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add(
                                types.KeyboardButton("🔙 Вернуться в начало")
                            )
                        )
                        return

                    # Получаем ID специалиста
                    sid = specialist['id']

                    # Получаем или генерируем реферальную ссылку
                    ref_link = specialist.get('Реферальная', '')
                    if not ref_link:
                        # Получаем имя бота
                        bot_username = bot.get_me().username

                        # Генерируем новую ссылку
                        ref_link = f"https://t.me/{bot_username}?start=ref{sid}"

                        # Обновляем ссылку в БД
                        sheets_service.update_specialist_referral_link(sid, ref_link)

                    # Предлагаем меню (скопировать / статистика)
                    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                    markup.add("📊 Статистика переходов")
                    markup.add("🔙 Назад в меню специалиста")

                    bot.send_message(
                        message.chat.id,
                        f"Ваша реферальная ссылка:\n{ref_link}\n\nПри переходе по ней клиент регистрируется напрямую к вам.",
                        reply_markup=markup
                    )
                except Exception as e:
                    logger.error(f"Ошибка referral_link: {e}", exc_info=True)
                    bot.send_message(message.chat.id, "Произошла ошибка. Попробуйте позже.")

            @bot.message_handler(func=lambda m: m.text == "📊 Статистика переходов")
            def referral_stats(message):
                """
                Статистика по переходам по реферальной ссылке
                """
                try:
                    user_id = message.from_user.id
                    specialist = sheets_service.get_specialist_by_telegram_id(user_id)

                    if not specialist:
                        bot.send_message(
                            message.chat.id,
                            "Вы не зарегистрированы как специалист.",
                            reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add(
                                types.KeyboardButton("🔙 Вернуться в начало")
                            )
                        )
                        return

                    # Получаем ID специалиста
                    sid = specialist['id']

                    # Получаем данные по клиентам
                    all_clients = sheets_service.get_all_clients()
                    my_clients = [c for c in all_clients if str(c.get('id_специалиста')) == str(sid)]

                    total_count = len(my_clients)

                    # Получаем данные по записям
                    all_slots = sheets_service.schedule_sheet.get_all_records()

                    # Находим слоты, привязанные к этому специалисту и имеющие статус "Занято"
                    booked_slots = [
                        s for s in all_slots 
                        if str(s.get('id_специалиста')) == str(sid) and s.get('Статус') == 'Занято'
                    ]

                    # Уникальные клиенты с записями
                    clients_with_bookings = set()
                    for slot in booked_slots:
                        if slot.get('id_клиента'):
                            clients_with_bookings.add(str(slot['id_клиента']))

                    bookings_count = len(clients_with_bookings)

                    # Формируем текст статистики
                    stats_text = (
                        "📊 Статистика по реферальной ссылке:\n\n"
                        f"• Всего зарегистрировано клиентов: {total_count}\n"
                        f"• Клиентов с записями: {bookings_count}\n"
                    )

                    # Получаем данные по отзывам клиентов
                    reviews = sheets_service.get_specialist_reviews(sid)
                    if reviews:
                        avg_rating = sum(r.get('Оценка', 0) for r in reviews) / len(reviews)
                        stats_text += f"• Отзывов получено: {len(reviews)}\n"
                        stats_text += f"• Средняя оценка: {avg_rating:.1f}/5\n"

                    bot.send_message(
                        message.chat.id,
                        stats_text,
                        reply_markup=get_specialist_menu_keyboard()
                    )
                except Exception as e:
                    logger.error(f"Ошибка referral_stats: {e}", exc_info=True)
                    bot.send_message(message.chat.id, "Произошла ошибка. Попробуйте позже.")

            logger.info("Завершена регистрация обработчиков specialist.py")

# Функции для рассылки сообщений
    @bot.message_handler(func=lambda m: m.text == "📢 Рассылка сообщений")
    def broadcast_menu(message):
        """
        Выбор получателей для рассылки
        """
        try:
            user_id = message.from_user.id
            specialist = sheets_service.get_specialist_by_telegram_id(user_id)
    
            if not specialist:
                bot.send_message(
                    message.chat.id,
                    "Вы не зарегистрированы как специалист.",
                    reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add(
                        types.KeyboardButton("🔙 Вернуться в начало")
                    )
                )
                return
    
            # Получаем ID специалиста
            sid = specialist['id']
    
            # Получаем список всех клиентов
            all_clients = sheets_service.get_all_clients()
    
            # Фильтруем только клиентов этого специалиста
            my_clients = [c for c in all_clients if str(c.get('id_специалиста')) == str(sid)]
    
            if not my_clients:
                bot.send_message(
                    message.chat.id, 
                    "У вас пока нет клиентов. Поделитесь реферальной ссылкой с клиентами.", 
                    reply_markup=get_specialist_menu_keyboard()
                )
                return
    
            # Создаем клавиатуру для выбора получателей
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            markup.add("👥 Все клиенты")
            markup.add("📅 Клиенты с записями на эту неделю")
            markup.add("📆 Клиенты с записями на выбранную дату")
            markup.add("🔙 Назад в меню специалиста")
    
            bot.set_state(user_id, SpecialistStates.waiting_for_recipients_choice, message.chat.id)
            bot.send_message(message.chat.id, "Выберите получателей:", reply_markup=markup)
        except Exception as e:
            logger.error(f"Ошибка broadcast_menu: {e}", exc_info=True)
            bot.send_message(message.chat.id, "Произошла ошибка. Попробуйте позже.")
    
    @bot.message_handler(state=SpecialistStates.waiting_for_recipients_choice)
    def process_recipients_choice(message):
        try:
            text = message.text.strip()
            user_id = message.from_user.id
            chat_id = message.chat.id
    
            if text == "🔙 Назад в меню специалиста":
                bot.delete_state(user_id, chat_id)
                bot.send_message(chat_id, "Отменено.", reply_markup=get_specialist_menu_keyboard())
                return
    
            valid_choices = ["👥 Все клиенты", "📅 Клиенты с записями на эту неделю", "📆 Клиенты с записями на выбранную дату"]
            if text not in valid_choices:
                bot.send_message(chat_id, "Неверный выбор. Выберите из меню или вернитесь назад.")
                return
    
            with bot.retrieve_data(user_id, chat_id) as data:
                data['broadcast_choice'] = text
    
            # Если нужно уточнить дату, то спрашиваем
            if text == "📆 Клиенты с записями на выбранную дату":
                bot.set_state(user_id, SpecialistStates.waiting_for_broadcast_date, chat_id)
    
                # Показываем календарь
                today = date.today()
                keyboard = get_calendar_keyboard(today.year, today.month)
    
                bot.send_message(
                    chat_id, 
                    "Выберите дату для рассылки:", 
                    reply_markup=keyboard
                )
            else:
                # Сразу переходим к запросу текста
                bot.set_state(user_id, SpecialistStates.waiting_for_message_text, chat_id)
    
                # Добавляем подсказки для текста сообщения
                markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                markup.add("🔙 Назад в меню специалиста")
    
                bot.send_message(
                    chat_id, 
                    "Введите текст сообщения для рассылки:", 
                    reply_markup=markup
                )
        except Exception as e:
            logger.error(f"Ошибка process_recipients_choice: {e}", exc_info=True)
            bot.send_message(message.chat.id, "Произошла ошибка. Попробуйте позже.")
            bot.delete_state(message.from_user.id, message.chat.id)
    
    @bot.message_handler(state=SpecialistStates.waiting_for_message_text)
    def process_broadcast_text(message):
        try:
            text = message.text.strip()
            user_id = message.from_user.id
            chat_id = message.chat.id
    
            if text == "🔙 Назад в меню специалиста":
                bot.delete_state(user_id, chat_id)
                bot.send_message(chat_id, "Рассылка отменена.", reply_markup=get_specialist_menu_keyboard())
                return
    
            if len(text) < 2:
                bot.send_message(chat_id, "Сообщение слишком короткое. Введите подробнее:")
                return
    
            with bot.retrieve_data(user_id, chat_id) as data:
                data['broadcast_text'] = text
    
            bot.set_state(user_id, SpecialistStates.waiting_for_message_text_confirm, chat_id)
    
            # Создаем клавиатуру для подтверждения
            keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
            keyboard.add("✅ Отправить", "❌ Отмена")
    
            bot.send_message(
                chat_id, 
                f"Подтвердите отправку сообщения:\n\n{text}", 
                reply_markup=keyboard
            )
        except Exception as e:
            logger.error(f"Ошибка process_broadcast_text: {e}", exc_info=True)
            bot.send_message(message.chat.id, "Произошла ошибка. Попробуйте позже.")
            bot.delete_state(message.from_user.id, message.chat.id)
    
    @bot.message_handler(state=SpecialistStates.waiting_for_message_text_confirm)
    def confirm_broadcast(message):
        try:
            choice = message.text.strip()
            user_id = message.from_user.id
            chat_id = message.chat.id
    
            if choice == "❌ Отмена":
                bot.delete_state(user_id, chat_id)
                bot.send_message(chat_id, "Рассылка отменена.", reply_markup=get_specialist_menu_keyboard())
                return
    
            if choice != "✅ Отправить":
                bot.send_message(chat_id, "Неверная команда. Нажмите ✅ Отправить или ❌ Отмена.")
                return
    
            # Выполняем рассылку
            with bot.retrieve_data(user_id, chat_id) as data:
                broadcast_choice = data.get('broadcast_choice', '')
                broadcast_text = data.get('broadcast_text', '')
                broadcast_date = data.get('broadcast_date', '')
    
            # Получаем данные специалиста
            specialist = sheets_service.get_specialist_by_telegram_id(user_id)
            if not specialist:
                bot.send_message(chat_id, "Специалист не найден.")
                bot.delete_state(user_id, chat_id)
                return
    
            # Получаем ID специалиста
            sid = specialist['id']
    
            # Определяем список получателей
            all_clients = sheets_service.get_all_clients()
            final_recipients = []
    
            if broadcast_choice == "👥 Все клиенты":
                # Все клиенты этого специалиста
                final_recipients = [c for c in all_clients if str(c.get('id_специалиста')) == str(sid)]
    
            elif broadcast_choice == "📅 Клиенты с записями на эту неделю":
                # Собираем клиентов, у которых запись в ближайшие 7 дней
                today = date.today()
                seven_days_later = today + timedelta(days=7)
    
                # Получаем все слоты расписания
                all_slots = sheets_service.schedule_sheet.get_all_records()
    
                # Собираем ID клиентов с записями на ближайшие 7 дней
                client_ids = set()
                for slot in all_slots:
                    # Проверяем, что слот относится к этому специалисту
                    if str(slot.get('id_специалиста')) != str(sid):
                        continue
    
                    # Проверяем дату слота
                    slot_date_str = slot.get('Дата')
                    if not slot_date_str:
                        continue
    
                    try:
                        slot_date = datetime.strptime(slot_date_str, "%Y-%m-%d").date()
                        if today <= slot_date <= seven_days_later:
                            if slot.get('id_клиента'):
                                client_ids.add(str(slot['id_клиента']))
                    except:
                        pass
    
                # Фильтруем клиентов по ID и специалисту
                final_recipients = [
                    c for c in all_clients 
                    if str(c.get('id')) in client_ids and str(c.get('id_специалиста')) == str(sid)
                ]
    
            elif broadcast_choice == "📆 Клиенты с записями на выбранную дату":
                # Конкретная дата
                if not broadcast_date:
                    bot.send_message(chat_id, "Ошибка: дата не выбрана.")
                    bot.delete_state(user_id, chat_id)
                    return
    
                # Получаем все слоты расписания
                all_slots = sheets_service.schedule_sheet.get_all_records()
    
                # Собираем ID клиентов с записями на выбранную дату
                client_ids = set()
                for slot in all_slots:
                    # Проверяем, что слот относится к этому специалисту
                    if str(slot.get('id_специалиста')) != str(sid):
                        continue
    
                    # Проверяем дату слота
                    if slot.get('Дата') == broadcast_date and slot.get('id_клиента'):
                        client_ids.add(str(slot['id_клиента']))
    
                # Фильтруем клиентов по ID и специалисту
                final_recipients = [
                    c for c in all_clients 
                    if str(c.get('id')) in client_ids and str(c.get('id_специалиста')) == str(sid)
                ]
    
            # Выполняем рассылку
            count = 0
            for cl in final_recipients:
                # Проверяем наличие Telegram ID
                tg_id = cl.get('Telegram_ID')
                if tg_id:
                    try:
                        # Формируем персональное сообщение с именем клиента
                        personal_text = f"Сообщение от {specialist.get('Имя', 'Вашего специалиста')}:\n\n{broadcast_text}"
                        bot.send_message(int(tg_id), personal_text)
                        count += 1
                    except Exception as e:
                        logger.warning(f"Не удалось отправить сообщение клиенту {tg_id}: {e}")
    
            # Завершаем рассылку
            bot.delete_state(user_id, chat_id)
    
            bot.send_message(
                chat_id,
                f"Сообщение отправлено {count} клиентам.",
                reply_markup=get_specialist_menu_keyboard()
            )
        except Exception as e:
            logger.error(f"Ошибка confirm_broadcast: {e}", exc_info=True)
            bot.send_message(message.chat.id, "Произошла ошибка. Попробуйте позже.")
            bot.delete_state(message.from_user.id, message.chat.id)
    
    @bot.callback_query_handler(func=lambda call: call.data.startswith("calendar_select_"),
                             state=SpecialistStates.waiting_for_broadcast_date)
    def select_broadcast_date(call):
        """
        Выбор даты для рассылки сообщений
        """
        try:
            date_str = call.data.replace("calendar_select_", "")
            user_id = call.from_user.id
            chat_id = call.message.chat.id
    
            # Сохраняем выбранную дату
            with bot.retrieve_data(user_id, chat_id) as data:
                data['broadcast_date'] = date_str
    
            # Удаляем сообщение с календарем
            try:
                bot.delete_message(chat_id, call.message.message_id)
            except Exception as e_del:
                logger.warning(f"Не удалось удалить сообщение с календарем: {e_del}")
    
            # Форматируем дату для красивого отображения
            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                formatted_date = date_obj.strftime('%d.%m.%Y')
            except:
                formatted_date = date_str
    
            # Переходим к запросу текста сообщения
            bot.set_state(user_id, SpecialistStates.waiting_for_message_text, chat_id)
    
            # Создаем клавиатуру
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            markup.add("🔙 Назад в меню специалиста")
    
            bot.send_message(
                chat_id, 
                f"Вы выбрали дату: {formatted_date}\nВведите текст сообщения для рассылки:", 
                reply_markup=markup
            )
    
            bot.answer_callback_query(call.id)
        except Exception as e:
            logger.error(f"Ошибка select_broadcast_date: {e}", exc_info=True)
            bot.answer_callback_query(call.id, "Ошибка при выборе даты")
            bot.delete_state(call.from_user.id, call.message.chat.id)
    
    # Функции для реферальной ссылки
    @bot.message_handler(func=lambda m: m.text == "🔗 Реферальная ссылка")
    def referral_link(message):
        """
        Показываем/генерируем реферальную ссылку, а также статистику
        """
        try:
            user_id = message.from_user.id
            specialist = sheets_service.get_specialist_by_telegram_id(user_id)
    
            if not specialist:
                bot.send_message(
                    message.chat.id,
                    "Вы не зарегистрированы как специалист.",
                    reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add(
                        types.KeyboardButton("🔙 Вернуться в начало")
                    )
                )
                return
    
            # Получаем ID специалиста
            sid = specialist['id']
    
            # Получаем или генерируем реферальную ссылку
            ref_link = specialist.get('Реферальная', '')
            if not ref_link:
                # Получаем имя бота
                bot_username = bot.get_me().username
    
                # Генерируем новую ссылку
                ref_link = f"https://t.me/{bot_username}?start=ref{sid}"
    
                # Обновляем ссылку в БД
                sheets_service.update_specialist_referral_link(sid, ref_link)
    
            # Предлагаем меню (скопировать / статистика)
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            markup.add("📊 Статистика переходов")
            markup.add("🔙 Назад в меню специалиста")
    
            bot.send_message(
                message.chat.id,
                f"Ваша реферальная ссылка:\n{ref_link}\n\nПри переходе по ней клиент регистрируется напрямую к вам.",
                reply_markup=markup
            )
        except Exception as e:
            logger.error(f"Ошибка referral_link: {e}", exc_info=True)
            bot.send_message(message.chat.id, "Произошла ошибка. Попробуйте позже.")
    
    @bot.message_handler(func=lambda m: m.text == "📊 Статистика переходов")
    def referral_stats(message):
        """
        Статистика по переходам по реферальной ссылке
        """
        try:
            user_id = message.from_user.id
            specialist = sheets_service.get_specialist_by_telegram_id(user_id)
    
            if not specialist:
                bot.send_message(
                    message.chat.id,
                    "Вы не зарегистрированы как специалист.",
                    reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add(
                        types.KeyboardButton("🔙 Вернуться в начало")
                    )
                )
                return
    
            # Получаем ID специалиста
            sid = specialist['id']
    
            # Получаем данные по клиентам
            all_clients = sheets_service.get_all_clients()
            my_clients = [c for c in all_clients if str(c.get('id_специалиста')) == str(sid)]
    
            total_count = len(my_clients)
    
            # Получаем данные по записям
            all_slots = sheets_service.schedule_sheet.get_all_records()
    
            # Находим слоты, привязанные к этому специалисту и имеющие статус "Занято"
            booked_slots = [
                s for s in all_slots 
                if str(s.get('id_специалиста')) == str(sid) and s.get('Статус') == 'Занято'
            ]
    
            # Уникальные клиенты с записями
            clients_with_bookings = set()
            for slot in booked_slots:
                if slot.get('id_клиента'):
                    clients_with_bookings.add(str(slot['id_клиента']))
    
            bookings_count = len(clients_with_bookings)
    
            # Формируем текст статистики
            stats_text = (
                "📊 Статистика по реферальной ссылке:\n\n"
                f"• Всего зарегистрировано клиентов: {total_count}\n"
                f"• Клиентов с записями: {bookings_count}\n"
            )
    
            # Получаем данные по отзывам клиентов
            reviews = sheets_service.get_specialist_reviews(sid)
            if reviews:
                avg_rating = sum(r.get('Оценка', 0) for r in reviews) / len(reviews)
                stats_text += f"• Отзывов получено: {len(reviews)}\n"
                stats_text += f"• Средняя оценка: {avg_rating:.1f}/5\n"
    
            bot.send_message(
                message.chat.id,
                stats_text,
                reply_markup=get_specialist_menu_keyboard()
            )
        except Exception as e:
            logger.error(f"Ошибка referral_stats: {e}", exc_info=True)
            bot.send_message(message.chat.id, "Произошла ошибка. Попробуйте позже.")
