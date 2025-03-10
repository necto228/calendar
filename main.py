# main.py
import logging
import os
import telebot
from telebot import types, custom_filters
from telebot.handler_backends import State, StatesGroup
from telebot.storage import StateMemoryStorage
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import signal
import sys

from settings import TOKEN, WEBHOOK_URL
from handlers import client, specialist, common
from services.google_sheets import GoogleSheetsService
from services.logger import LoggingService
from services.scheduler import SchedulerService

# Создаём папку logs если нужно
log_dir = os.path.join(os.getcwd(), 'logs')
if os.path.exists(log_dir) and not os.path.isdir(log_dir):
    try:
        os.remove(log_dir)
        print(f"Удалён файл logs (он не был директорией).")
    except Exception as e:
        print(f"Ошибка удаления файла logs: {e}")

if not os.path.exists(log_dir):
    try:
        os.makedirs(log_dir, exist_ok=True)
        print(f"Создана директория логов: {log_dir}")
    except Exception as e:
        print(f"Ошибка создания директории логов: {e}")

log_file = os.path.join(log_dir, 'main.log')
handlers = [logging.StreamHandler()]
if os.path.exists(log_dir) and os.path.isdir(log_dir):
    handlers.append(logging.FileHandler(log_file, encoding='utf-8'))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=handlers)
logger = logging.getLogger(__name__)

# FSM-хранилище
state_storage = StateMemoryStorage()
bot = telebot.TeleBot(TOKEN, state_storage=state_storage)

# Добавляем StateFilter
bot.add_custom_filter(custom_filters.StateFilter(bot))

# Сервисы
sheets_service = GoogleSheetsService()
logging_service = LoggingService(sheets_service)
scheduler_service = SchedulerService(sheets_service, bot)

# Обработчики для уведомлений (колбэки)
@bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_visit_"))
def confirm_visit_callback(call):
    """Обработчик подтверждения записи"""
    try:
        reminder_id = call.data.split("_")[2]
        user_id = call.from_user.id
        
        # Обновляем статус напоминания и записи
        reminder = sheets_service.get_reminder_by_id(reminder_id)
        if reminder:
            appointment_id = reminder.get('id_записи')
            if appointment_id:
                sheets_service.update_appointment_confirmation(appointment_id, True)
                
            sheets_service.update_reminder_status(reminder_id, 'confirmed')
            
            # Отправляем сообщение пользователю
            bot.edit_message_text(
                "Спасибо за подтверждение! Ждем вас на приеме.",
                call.message.chat.id,
                call.message.message_id
            )
            
            # Отправляем уведомление специалисту
            specialist_id = reminder.get('id_специалиста')
            if specialist_id:
                specialist = sheets_service.get_specialist_by_id(specialist_id)
                if specialist and specialist.get('Telegram_ID'):
                    client = sheets_service.get_client_by_id(reminder.get('id_клиента'))
                    client_name = client.get('Имя', 'Клиент') if client else 'Клиент'
                    
                    try:
                        date_str = scheduler_service.format_date(reminder.get('Дата', ''))
                        time_str = reminder.get('Время', '')
                        
                        notification = (
                            f"✅ Клиент {client_name} подтвердил запись на {date_str} "
                            f"в {time_str}"
                        )
                        
                        bot.send_message(specialist.get('Telegram_ID'), notification)
                    except Exception as e_notify:
                        logger.error(f"Ошибка отправки уведомления специалисту: {e_notify}")
        
        bot.answer_callback_query(call.id, "Запись подтверждена")
    except Exception as e:
        logger.error(f"Ошибка в обработчике подтверждения записи: {e}", exc_info=True)
        bot.answer_callback_query(call.id, "Произошла ошибка. Попробуйте позже.")

@bot.callback_query_handler(func=lambda call: call.data.startswith("cancel_visit_"))
def cancel_visit_callback(call):
    """Обработчик отмены записи из напоминания"""
    try:
        reminder_id = call.data.split("_")[2]
        user_id = call.from_user.id
        
        # Получаем данные напоминания
        reminder = sheets_service.get_reminder_by_id(reminder_id)
        if reminder:
            appointment_id = reminder.get('id_записи')
            if appointment_id:
                # Отменяем запись
                success = sheets_service.cancel_appointment(appointment_id)
                
                if success:
                    # Обновляем статус напоминания
                    sheets_service.update_reminder_status(reminder_id, 'cancelled')
                    
                    # Отправляем сообщение пользователю
                    bot.edit_message_text(
                        "Запись отменена. Вы можете записаться на другое время.",
                        call.message.chat.id,
                        call.message.message_id
                    )
                    
                    # Отправляем уведомление специалисту
                    specialist_id = reminder.get('id_специалиста')
                    if specialist_id:
                        specialist = sheets_service.get_specialist_by_id(specialist_id)
                        if specialist and specialist.get('Telegram_ID'):
                            client = sheets_service.get_client_by_id(reminder.get('id_клиента'))
                            client_name = client.get('Имя', 'Клиент') if client else 'Клиент'
                            
                            try:
                                date_str = scheduler_service.format_date(reminder.get('Дата', ''))
                                time_str = reminder.get('Время', '')
                                
                                notification = (
                                    f"❌ Клиент {client_name} отменил запись на {date_str} "
                                    f"в {time_str}"
                                )
                                
                                bot.send_message(specialist.get('Telegram_ID'), notification)
                            except Exception as e_notify:
                                logger.error(f"Ошибка отправки уведомления специалисту: {e_notify}")
                else:
                    bot.answer_callback_query(call.id, "Не удалось отменить запись. Обратитесь к специалисту.")
                    return
            else:
                bot.answer_callback_query(call.id, "Запись не найдена")
                return
        else:
            bot.answer_callback_query(call.id, "Напоминание не найдено")
            return
        
        bot.answer_callback_query(call.id, "Запись отменена")
    except Exception as e:
        logger.error(f"Ошибка в обработчике отмены записи: {e}", exc_info=True)
        bot.answer_callback_query(call.id, "Произошла ошибка. Попробуйте позже.")

@bot.callback_query_handler(func=lambda call: call.data.startswith("rate_"))
def rate_appointment_callback(call):
    """Обработчик оценки визита"""
    try:
        parts = call.data.split("_")
        rating = int(parts[1])
        appointment_id = parts[2]
        user_id = call.from_user.id
        
        # Получаем данные клиента
        client = sheets_service.get_client_by_telegram_id(user_id)
        if not client:
            bot.answer_callback_query(call.id, "Клиент не найден")
            return
        
        client_id = client.get('id')
        
        # Получаем информацию о записи
        appointment = sheets_service.get_appointment_by_id(appointment_id)
        if not appointment:
            bot.answer_callback_query(call.id, "Запись не найдена")
            return
        
        specialist_id = appointment.get('id_специалиста')
        
        # Сохраняем оценку
        review_id = sheets_service.add_review(client_id, specialist_id, rating, "")
        
        if review_id:
            # Спрашиваем, не хочет ли клиент оставить комментарий
            markup = telebot.types.InlineKeyboardMarkup()
            markup.add(
                telebot.types.InlineKeyboardButton("📝 Написать отзыв", callback_data=f"comment_{review_id}"),
                telebot.types.InlineKeyboardButton("➡️ Пропустить", callback_data="skip_comment")
            )
            
            # Определяем текст звезд
            stars = "⭐" * rating
            
            bot.edit_message_text(
                f"Спасибо за вашу оценку: {stars} ({rating}/5)! Хотите оставить комментарий или пожелания?",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup
            )
            
            # Отправляем уведомление специалисту
            specialist = sheets_service.get_specialist_by_id(specialist_id)
            if specialist and specialist.get('Telegram_ID'):
                try:
                    notification = (
                        f"⭐ Новый отзыв от клиента {client.get('Имя', 'Клиент')}!\n\n"
                        f"Оценка: {stars} ({rating}/5)\n"
                    )
                    
                    bot.send_message(specialist.get('Telegram_ID'), notification)
                except Exception as e_notify:
                    logger.error(f"Ошибка отправки уведомления специалисту: {e_notify}")
        else:
            bot.answer_callback_query(call.id, "Не удалось сохранить оценку. Попробуйте позже.")
    except Exception as e:
        logger.error(f"Ошибка в обработчике оценки визита: {e}", exc_info=True)
        bot.answer_callback_query(call.id, "Произошла ошибка. Попробуйте позже.")

@bot.callback_query_handler(func=lambda call: call.data.startswith("comment_"))
def comment_review_callback(call):
    """Обработчик запроса комментария к отзыву"""
    try:
        review_id = call.data.split("_")[1]
        
        # Переводим пользователя в состояние ожидания комментария
        bot.set_state(call.from_user.id, client.ClientStates.writing_review, call.message.chat.id)
        
        # Сохраняем ID отзыва
        with bot.retrieve_data(call.from_user.id, call.message.chat.id) as data:
            data['review_id'] = review_id
        
        # Запрашиваем комментарий
        bot.edit_message_text(
            "Пожалуйста, напишите ваш отзыв:",
            call.message.chat.id,
            call.message.message_id
        )
        
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(telebot.types.KeyboardButton("Пропустить"))
        
        bot.send_message(
            call.message.chat.id,
            "Напишите ваш комментарий или нажмите 'Пропустить':",
            reply_markup=markup
        )
        
        bot.answer_callback_query(call.id)
    except Exception as e:
        logger.error(f"Ошибка в обработчике запроса комментария: {e}", exc_info=True)
        bot.answer_callback_query(call.id, "Произошла ошибка. Попробуйте позже.")

@bot.callback_query_handler(func=lambda call: call.data == "skip_comment")
def skip_comment_callback(call):
    """Обработчик пропуска комментария"""
    try:
        # Возвращаем клавиатуру меню
        from utils.keyboards import get_client_menu_keyboard
        
        bot.edit_message_text(
            "Спасибо за вашу оценку! Она поможет нам стать лучше.",
            call.message.chat.id,
            call.message.message_id
        )
        
        bot.send_message(
            call.message.chat.id,
            "Вы можете управлять своими записями через меню.",
            reply_markup=get_client_menu_keyboard()
        )
        
        bot.answer_callback_query(call.id)
    except Exception as e:
        logger.error(f"Ошибка в обработчике пропуска комментария: {e}", exc_info=True)
        bot.answer_callback_query(call.id, "Произошла ошибка. Попробуйте позже.")

# Регистрируем все хендлеры
logger.info("Регистрация обработчиков...")
logger.info(
    f"Количество обработчиков до регистрации: {len(bot.message_handlers)}")

# Важно! Сначала регистрируем более специфичные обработчики, 
# затем общие
client.register_handlers(bot, sheets_service, logging_service, scheduler_service)
logger.info(
    f"После регистрации client: {len(bot.message_handlers)} обработчиков")

specialist.register_handlers(bot, sheets_service, logging_service, scheduler_service)
logger.info(
    f"После регистрации specialist: {len(bot.message_handlers)} обработчиков")

common.register_handlers(bot, sheets_service, logging_service, scheduler_service)
logger.info(
    f"После регистрации common: {len(bot.message_handlers)} обработчиков")

# Проверка на конфликты состояний
state_handlers = {}
for h in bot.message_handlers:
    if hasattr(h, 'filters') and hasattr(h.filters, 'state'):
        st = str(h.filters.state)
        if st in state_handlers:
            logger.warning(f"КОНФЛИКТ: Несколько хендлеров для состояния {st}")
        else:
            state_handlers[st] = h

logger.info(f"Обработчики по состояниям: {list(state_handlers.keys())}")

app = FastAPI()

# Обработчик остановки приложения
def shutdown_handler():
    """Обработчик завершения работы приложения"""
    logger.info("Останавливаем планировщик уведомлений...")
    scheduler_service.stop_scheduler()
    logger.info("Планировщик остановлен")

# Обработчики сигналов
def signal_handler(sig, frame):
    """Обработчик сигналов завершения"""
    logger.info(f"Получен сигнал {sig}, завершаем работу...")
    shutdown_handler()
    sys.exit(0)

# Регистрируем обработчики сигналов
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

@app.on_event("shutdown")
async def shutdown_event():
    """Событие завершения работы FastAPI"""
    shutdown_handler()

@app.get("/")
async def index():
    logging.info(
        "Тест логирования - если вы видите это сообщение, логирование работает корректно"
    )
    return JSONResponse({"message": "Бот успешно запущен!"})


@app.get("/webhook")
async def webhook_get():
    return JSONResponse({
        "message":
        "Вебхук доступен. Используйте POST для отправки апдейтов."
    })


@app.post("/webhook")
async def webhook(request: Request):
    if request.headers.get("content-type") != "application/json":
        raise HTTPException(status_code=400, detail="Неверный формат данных")

    json_bytes = await request.body()
    json_string = json_bytes.decode("utf-8")

    try:
        logger.info(f"WEBHOOK: Получено обновление: {json_string[:100]}...")
        update = types.Update.de_json(json_string)

        # Лог входящего
        if update.message and update.message.text:
            user_id = update.message.from_user.id
            chat_id = update.message.chat.id
            username = update.message.from_user.username or f"{update.message.from_user.first_name} {update.message.from_user.last_name or ''}"
            logger.info(
                f"WEBHOOK: Сообщение от {user_id} ({username}): {update.message.text}"
            )
            logging_service.log_message(user_id, username, update.message.text,
                                        'user')

        # Перехват отправки send_message
        if not hasattr(bot, 'original_send_message'):
            bot.original_send_message = bot.send_message
            logger.info("WEBHOOK: Перехватываем send_message для логирования")

            def logged_send_message(chat_id, text, *args, **kwargs):
                try:
                    logger.info(
                        f"WEBHOOK: Отправка сообщения {chat_id}: {text[:50]}..."
                    )
                    logging_service.log_message(chat_id, 'bot', text, 'bot')
                except Exception as e:
                    logger.error(
                        f"Ошибка логирования исходящего сообщения: {e}")
                return bot.original_send_message(chat_id, text, *args,
                                                 **kwargs)

            bot.send_message = logged_send_message

        logger.info("WEBHOOK: Начинаем обработку")
        if update.message and update.message.from_user:
            try:
                uid = update.message.from_user.id
                ch = update.message.chat.id
                cur_state = bot.get_state(uid, ch)
                logger.info(
                    f"WEBHOOK: Текущее состояние пользователя {uid}: {cur_state}"
                )

                # Выведем все зарегистрированные message_handlers
                hlist = bot.message_handlers.copy()
                logger.info(f"WEBHOOK: Всего {len(hlist)} обработчиков")
                for hh in hlist:
                    if hasattr(hh, 'filters') and hasattr(hh.filters, 'state'):
                        logger.info(f" - хендлер со state={hh.filters.state}")

            except Exception as st_err:
                logger.error(f"WEBHOOK: Ошибка получения состояния: {st_err}")

        # Передаём в TeleBot
        logger.info(f"WEBHOOK: process_new_updates({update.update_id})")
        bot.process_new_updates([update])
        logger.info("WEBHOOK: Обновление обработано успешно")

    except Exception as e:
        logger.error(f"Ошибка обработки: {e}", exc_info=True)
        raise HTTPException(status_code=500,
                            detail="Ошибка обработки обновления")

    return JSONResponse({"status": "ok"})


def setup_webhook():
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    logger.info(f"Вебхук установлен на: {WEBHOOK_URL}")


if __name__ == "__main__":
    # Запускаем планировщик уведомлений
    logger.info("Запуск планировщика уведомлений...")
    scheduler_service.start_scheduler(bot)
    
    setup_webhook()

    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)