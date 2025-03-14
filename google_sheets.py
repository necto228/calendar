# services/google_sheets.py
import logging
import gspread
from google.oauth2.service_account import Credentials
from settings import GOOGLE_SHEET_ID, GOOGLE_CREDENTIALS_JSON
from datetime import datetime, timedelta, date

logger = logging.getLogger(__name__)

class GoogleSheetsService:
    """Сервис для работы с Google Sheets API"""

    def __init__(self):
        try:
            scopes = [
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]
            credentials = Credentials.from_service_account_info(
                GOOGLE_CREDENTIALS_JSON, 
                scopes=scopes
            )
            self.client = gspread.authorize(credentials)
            self.spreadsheet = self.client.open_by_key(GOOGLE_SHEET_ID)
            
            # Проверяем и создаем листы, если они не существуют
            worksheets = {ws.title: ws for ws in self.spreadsheet.worksheets()}
            
            # Лист "Специалисты"
            if 'Специалисты' not in worksheets:
                logger.info("Создаем лист 'Специалисты'")
                self.specialists_sheet = self.spreadsheet.add_worksheet(title='Специалисты', rows=1000, cols=6)
                self.specialists_sheet.append_row(['id', 'Имя', 'Специализация', 'Часовой пояс', 'Реферальная', 'Telegram_ID'])
            else:
                self.specialists_sheet = worksheets['Специалисты']
                # Проверяем заголовки
                headers = self.specialists_sheet.row_values(1)
                required_headers = ['id', 'Имя', 'Специализация', 'Часовой пояс', 'Реферальная', 'Telegram_ID']
                for header in required_headers:
                    if header not in headers:
                        logger.info(f"Добавляем отсутствующий заголовок '{header}' в лист Специалисты")
                        col_idx = len(headers) + 1
                        self.specialists_sheet.update_cell(1, col_idx, header)
                        headers.append(header)
            
            # Лист "Клиенты"
            if 'Клиенты' not in worksheets:
                logger.info("Создаем лист 'Клиенты'")
                self.clients_sheet = self.spreadsheet.add_worksheet(title='Клиенты', rows=1000, cols=5)
                self.clients_sheet.append_row(['id', 'Имя', 'Телефон', 'id_специалиста', 'Telegram_ID'])
            else:
                self.clients_sheet = worksheets['Клиенты']
                # Проверяем заголовки
                headers = self.clients_sheet.row_values(1)
                required_headers = ['id', 'Имя', 'Телефон', 'id_специалиста', 'Telegram_ID']
                for header in required_headers:
                    if header not in headers:
                        logger.info(f"Добавляем отсутствующий заголовок '{header}' в лист Клиенты")
                        col_idx = len(headers) + 1
                        self.clients_sheet.update_cell(1, col_idx, header)
                        headers.append(header)
            
            # Лист "Расписание"
            if 'Расписание' not in worksheets:
                logger.info("Создаем лист 'Расписание'")
                self.schedule_sheet = self.spreadsheet.add_worksheet(title='Расписание', rows=1000, cols=6)
                self.schedule_sheet.append_row(['id', 'Дата', 'Время', 'id_специалиста', 'Статус', 'id_клиента'])
            else:
                self.schedule_sheet = worksheets['Расписание']
                # Проверяем заголовки
                headers = self.schedule_sheet.row_values(1)
                required_headers = ['id', 'Дата', 'Время', 'id_специалиста', 'Статус', 'id_клиента']
                for header in required_headers:
                    if header not in headers:
                        logger.info(f"Добавляем отсутствующий заголовок '{header}' в лист Расписание")
                        col_idx = len(headers) + 1
                        self.schedule_sheet.update_cell(1, col_idx, header)
                        headers.append(header)
                
                # Проверяем наличие дополнительных столбцов для функциональности уведомлений
                additional_headers = ['Подтверждено', 'Запрос_оценки', 'Продолжительность']
                for header in additional_headers:
                    if header not in headers:
                        logger.info(f"Добавляем отсутствующий заголовок '{header}' в лист Расписание")
                        col_idx = len(headers) + 1
                        self.schedule_sheet.update_cell(1, col_idx, header)
                        headers.append(header)
            
            # Лист "Услуги"
            if 'Услуги' not in worksheets:
                logger.info("Создаем лист 'Услуги'")
                self.services_sheet = self.spreadsheet.add_worksheet(title='Услуги', rows=1000, cols=4)
                self.services_sheet.append_row(['id_специалиста', 'Название', 'Продолжительность', 'Стоимость'])
            else:
                self.services_sheet = worksheets['Услуги']
            
            # Лист "Отзывы"
            if 'Отзывы' not in worksheets:
                logger.info("Создаем лист 'Отзывы'")
                self.reviews_sheet = self.spreadsheet.add_worksheet(title='Отзывы', rows=1000, cols=5)
                self.reviews_sheet.append_row(['id_клиента', 'id_специалиста', 'Дата', 'Оценка', 'Комментарий'])
            else:
                self.reviews_sheet = worksheets['Отзывы']
            
            # Попытка получить или создать лист для логов
            try:
                self.logs_worksheet = self.spreadsheet.worksheet('Логи')
                logger.info("Лист логов найден")
            except gspread.exceptions.WorksheetNotFound:
                self.logs_worksheet = self.spreadsheet.add_worksheet(title='Логи', rows=1000, cols=5)
                self.logs_worksheet.append_row(['Время', 'ID пользователя', 'Имя пользователя', 'Сообщение', 'Тип'])
                logger.info("Создан новый лист логов")
            
            # Лист "Напоминания" для отслеживания отправленных напоминаний
            if 'Напоминания' not in worksheets:
                logger.info("Создаем лист 'Напоминания'")
                self.reminders_sheet = self.spreadsheet.add_worksheet(title='Напоминания', rows=1000, cols=8)
                self.reminders_sheet.append_row(['id', 'id_записи', 'id_клиента', 'id_специалиста', 'Дата', 'Время', 'Статус', 'Услуга'])
            else:
                self.reminders_sheet = worksheets['Напоминания']
                # Проверяем заголовки
                headers = self.reminders_sheet.row_values(1)
                required_headers = ['id', 'id_записи', 'id_клиента', 'id_специалиста', 'Дата', 'Время', 'Статус', 'Услуга']
                for header in required_headers:
                    if header not in headers:
                        logger.info(f"Добавляем отсутствующий заголовок '{header}' в лист Напоминания")
                        col_idx = len(headers) + 1
                        self.reminders_sheet.update_cell(1, col_idx, header)
                        headers.append(header)
            
            logger.info("Соединение с Google Sheets успешно установлено")
        except Exception as e:
            logger.error(f"Ошибка инициализации Google Sheets: {e}", exc_info=True)
            self.logs_worksheet = None
            raise

                def _normalize_date(self, date_str):
        """
        Нормализует строку даты, удаляя лишние пробелы, символы переноса строки и апострофы.
        Возвращает строку в формате YYYY-MM-DD.
        """
        if not date_str:
            return ""

        # Удаляем пробелы, символы переноса строки и апострофы
        date_str = date_str.strip().strip("'").strip('"')

        # Пытаемся преобразовать в объект datetime для стандартизации
        try:
            # Проверяем разные форматы даты
            for fmt in ['%Y-%m-%d', '%d.%m.%Y', '%Y/%m/%d', '%d-%m-%Y']:
                try:
                    date_obj = datetime.strptime(date_str, fmt)
                    return date_obj.strftime('%Y-%m-%d')
                except ValueError:
                    continue

            # Если не удалось распознать формат, пробуем разбить строку
            if '/' in date_str:
                parts = date_str.split('/')
            elif '-' in date_str:
                parts = date_str.split('-')
            elif '.' in date_str:
                parts = date_str.split('.')
            else:
                logger.warning(f"Не удалось нормализовать дату: {date_str}")
                return date_str

            if len(parts) == 3:
                # Пытаемся угадать формат по длине года
                if len(parts[0]) == 4:  # Год-месяц-день
                    return f"{parts[0]}-{int(parts[1]):02d}-{int(parts[2]):02d}"
                elif len(parts[2]) == 4:  # День-месяц-год
                    return f"{parts[2]}-{int(parts[1]):02d}-{int(parts[0]):02d}"

            logger.warning(f"Не удалось нормализовать дату: {date_str}")
            return date_str
        except Exception as e:
            logger.warning(f"Ошибка при нормализации даты '{date_str}': {e}")
            return date_str

        # Удаляем пробелы, символы переноса строки и апострофы
        date_str = date_str.strip().strip("'").strip('"')

        # Пытаемся преобразовать в объект datetime для стандартизации
        try:
            # Проверяем разные форматы даты
            for fmt in ['%Y-%m-%d', '%d.%m.%Y', '%Y/%m/%d', '%d-%m-%Y']:
                try:
                    date_obj = datetime.strptime(date_str, fmt)
                    return date_obj.strftime('%Y-%m-%d')
                except ValueError:
                    continue

            # Если не удалось распознать формат, пробуем разбить строку
            if '/' in date_str:
                parts = date_str.split('/')
            elif '-' in date_str:
                parts = date_str.split('-')
            elif '.' in date_str:
                parts = date_str.split('.')
            else:
                logger.warning(f"Не удалось нормализовать дату: {date_str}")
                return date_str

            if len(parts) == 3:
                # Пытаемся угадать формат по длине года
                if len(parts[0]) == 4:  # Год-месяц-день
                    return f"{parts[0]}-{int(parts[1]):02d}-{int(parts[2]):02d}"
                elif len(parts[2]) == 4:  # День-месяц-год
                    return f"{parts[2]}-{int(parts[1]):02d}-{int(parts[0]):02d}"

            logger.warning(f"Не удалось нормализовать дату: {date_str}")
            return date_str
        except Exception as e:
            logger.warning(f"Ошибка при нормализации даты '{date_str}': {e}")
            return date_str

        
        # Удаляем пробелы, символы переноса строки и апострофы
        date_str = date_str.strip().strip("'").strip('"')
        
        # Пытаемся преобразовать в объект datetime для стандартизации
        try:
            # Проверяем разные форматы даты
            for fmt in ['%Y-%m-%d', '%d.%m.%Y', '%Y/%m/%d', '%d-%m-%Y']:
                try:
                    date_obj = datetime.strptime(date_str, fmt)
                    return date_obj.strftime('%Y-%m-%d')
                except ValueError:
                    continue
            
            # Если не удалось распознать формат, пробуем разбить строку
            if '/' in date_str:
                parts = date_str.split('/')
            elif '-' in date_str:
                parts = date_str.split('-')
            elif '.' in date_str:
                parts = date_str.split('.')
            else:
                logger.warning(f"Не удалось нормализовать дату: {date_str}")
                return date_str
            
            if len(parts) == 3:
                # Пытаемся угадать формат по длине года
                if len(parts[0]) == 4:  # Год-месяц-день
                    return f"{parts[0]}-{int(parts[1]):02d}-{int(parts[2]):02d}"
                elif len(parts[2]) == 4:  # День-месяц-год
                    return f"{parts[2]}-{int(parts[1]):02d}-{int(parts[0]):02d}"
                
            logger.warning(f"Не удалось нормализовать дату: {date_str}")
            return date_str
        except Exception as e:
            logger.warning(f"Ошибка при нормализации даты '{date_str}': {e}")
            return date_str

    def get_available_slots(self, specialist_id, date=None):
        """
        Получает доступные (свободные) слоты расписания для специалиста.
        
        Args:
            specialist_id: ID специалиста
            date: Дата в формате YYYY-MM-DD (если None, то все даты)
            
        Returns:
            Список доступных слотов расписания
        """
        try:
            # Получаем все записи из листа расписания
            all_slots = self.schedule_sheet.get_all_records()
            
            # Для логирования
            total_slots = len(all_slots)
            total_specialist_slots = 0
            total_free_slots = 0
            total_date_match = 0
            
            # Список для хранения доступных слотов
            available_slots = []
            
            # Нормализуем искомую дату, если она задана
            norm_date = self._normalize_date(date) if date else None
            
            # Перебираем все слоты
            for slot in all_slots:
                # Проверяем, что слот принадлежит запрашиваемому специалисту
                if str(slot.get('id_специалиста', '')) != str(specialist_id):
                    continue
                    
                total_specialist_slots += 1
                
                # Проверяем, что слот свободен
                if slot.get('Статус') != 'Свободно':
                    continue
                    
                total_free_slots += 1
                
                # Проверяем дату, если она задана
                if norm_date is not None:
                    # Нормализуем дату слота для корректного сравнения
                    slot_date = self._normalize_date(slot.get('Дата', ''))
                    if slot_date != norm_date:
                        continue
                        
                total_date_match += 1
                available_slots.append(slot)
            
            # Добавляем отладочное логирование
            if date is not None:
                logger.debug(
                    f"get_available_slots: специалист {specialist_id}, дата {date}, "
                    f"найдено {len(available_slots)} слотов из {total_slots} "
                    f"(специалиста: {total_specialist_slots}, свободных: {total_free_slots}, "
                    f"дата совпала: {total_date_match})"
                )
            
            return available_slots
        except Exception as e:
            logger.error(f"Ошибка получения доступных слотов: {e}", exc_info=True)
            return []

    def generate_month_schedule(self, specialist_id, working_days, start_time, end_time, break_minutes):
        """
        Генерирует расписание для специалиста на ближайшие 30 дней и добавляет слоты в расписание (лист "Расписание").
        """
        try:
            start_dt = datetime.strptime(start_time, "%H:%M").time()
            end_dt = datetime.strptime(end_time, "%H:%M").time()
        except Exception as e:
            logger.error(f"Ошибка преобразования времени: {e}")
            return

        today = date.today()
        mapping = {
            "Monday": "Понедельник",
            "Tuesday": "Вторник",
            "Wednesday": "Среда",
            "Thursday": "Четверг",
            "Friday": "Пятница",
            "Saturday": "Суббота",
            "Sunday": "Воскресенье"
        }

        for day_offset in range(30):
            current_day = today + timedelta(days=day_offset)
            day_russian = mapping.get(current_day.strftime("%A"), current_day.strftime("%A"))
            if day_russian in working_days:
                current_dt = datetime.combine(current_day, start_dt)
                end_dt_full = datetime.combine(current_day, end_dt)
                while current_dt + timedelta(minutes=30) <= end_dt_full:
                    slot_time = current_dt.strftime("%H:%M")
                    self.add_schedule_slot(current_day.strftime("%Y-%m-%d"), slot_time, specialist_id)
                    current_dt += timedelta(minutes=30 + break_minutes)
        logger.info(f"Генерация расписания на месяц для специалиста {specialist_id} завершена.")
        
    def generate_specific_month_schedule(self, specialist_id, working_days, start_time, end_time, break_minutes, year, month):
        """
        Генерирует расписание для специалиста на выбранный месяц и год
        и добавляет слоты в расписание (лист "Расписание").
        """
        try:
            start_dt = datetime.strptime(start_time, "%H:%M").time()
            end_dt = datetime.strptime(end_time, "%H:%M").time()
        except Exception as e:
            logger.error(f"Ошибка преобразования времени: {e}")
            return

        import calendar
        
        # Получаем первый и последний день месяца
        first_day = date(year, month, 1)
        
        # Для получения последнего дня месяца
        _, last_day_num = calendar.monthrange(year, month)
        last_day = date(year, month, last_day_num)
        
        # Отображение английских названий дней недели на русские
        mapping = {
            "Monday": "Понедельник",
            "Tuesday": "Вторник",
            "Wednesday": "Среда",
            "Thursday": "Четверг",
            "Friday": "Пятница",
            "Saturday": "Суббота",
            "Sunday": "Воскресенье"
        }

        # Генерируем слоты для каждого дня месяца
        current_day = first_day
        while current_day <= last_day:
            day_russian = mapping.get(current_day.strftime("%A"), current_day.strftime("%A"))
            if day_russian in working_days:
                current_dt = datetime.combine(current_day, start_dt)
                end_dt_full = datetime.combine(current_day, end_dt)
                while current_dt + timedelta(minutes=30) <= end_dt_full:
                    slot_time = current_dt.strftime("%H:%M")
                    self.add_schedule_slot(current_day.strftime("%Y-%m-%d"), slot_time, specialist_id)
                    current_dt += timedelta(minutes=30 + break_minutes)
            current_day += timedelta(days=1)
            
        logger.info(f"Генерация расписания на {month}/{year} для специалиста {specialist_id} завершена.")

    def clear_month_schedule(self, specialist_id, year, month):
        """
        Очищает все слоты для указанного специалиста за определенный месяц.
        Возвращает количество удаленных слотов.
        """
        try:
            import calendar
            
            # Получаем первый и последний день месяца
            first_day = date(year, month, 1)
            
            # Для получения последнего дня месяца
            _, last_day_num = calendar.monthrange(year, month)
            last_day = date(year, month, last_day_num)
            
            # Форматируем даты в строки для сравнения
            start_date_str = first_day.strftime("%Y-%m-%d")
            end_date_str = last_day.strftime("%Y-%m-%d")
            
            # Получаем все строки из листа расписания
            all_rows = self.schedule_sheet.get_all_values()
            
            # Индексы для столбцов
            idx_id = 0
            idx_date = 1
            idx_specialist = 3
            idx_status = 4
            idx_client = 5
            
            # Строки для удаления (в обратном порядке, чтобы не нарушить индексацию)
            rows_to_delete = []
            
            # Проходимся по всем строкам (кроме заголовка)
            for i in range(1, len(all_rows)):
                row = all_rows[i]
                if len(row) <= max(idx_date, idx_specialist, idx_status, idx_client):
                    # Неполная строка, пропускаем
                    continue
                
                # Проверяем, что это запись нужного специалиста
                if str(row[idx_specialist]) != str(specialist_id):
                    continue
                
                # Проверяем, что дата находится в нужном месяце
                date_str = self._normalize_date(row[idx_date].strip() if row[idx_date] else "")
                if not date_str or date_str < start_date_str or date_str > end_date_str:
                    continue
                
                # Этот слот подходит для удаления
                rows_to_delete.append(i + 1)  # +1 т.к. в Google Sheets строки начинаются с 1
            
            # Удаляем строки в обратном порядке
            deleted_count = 0
            for row_idx in sorted(rows_to_delete, reverse=True):
                self.schedule_sheet.delete_row(row_idx)
                deleted_count += 1
            
            logger.info(f"Удалено {deleted_count} слотов за {month}/{year} для специалиста {specialist_id}")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Ошибка при очистке расписания на месяц: {e}", exc_info=True)
            return 0

    def close_day_slots(self, specialist_id, date_str):
        """
        Обновляет все слоты для указанного специалиста в указанную дату, устанавливая статус "Закрыто".
        При этом сбрасывает поле id_клиента.

        Args:
            specialist_id: ID специалиста.
            date_str: дата в формате "YYYY-MM-DD".

        Returns:
            True, если обновление прошло успешно (хотя бы один слот изменён), иначе False.
        """
        try:
            normalized_date = self._normalize_date(date_str)
            all_slots = self.schedule_sheet.get_all_records()
            updated = False
            # Получаем заголовки, чтобы найти нужные колонки
            headers = self.schedule_sheet.row_values(1)
            status_col = headers.index('Статус') + 1
            client_col = headers.index('id_клиента') + 1
            
            # Итерируем по слотам (начиная со второй строки, т.к. первая – заголовки)
            for idx, slot in enumerate(all_slots, start=2):
                slot_date = self._normalize_date(slot.get('Дата', ''))
                
                # Логирование для отладки
                if str(slot.get('id_специалиста')) == str(specialist_id):
                    logger.debug(f"Проверка слота: дата в слоте={slot.get('Дата', '')}, нормализованная={slot_date}, искомая={normalized_date}")
                
                if (str(slot.get('id_специалиста')) == str(specialist_id) and 
                    slot_date == normalized_date and slot.get('Статус') != 'Закрыто'):
                    self.schedule_sheet.update_cell(idx, status_col, 'Закрыто')
                    self.schedule_sheet.update_cell(idx, client_col, '')
                    updated = True
            
            if updated:
                logger.info(f"Слоты для специалиста {specialist_id} на дату {date_str} закрыты.")
            else:
                logger.info(f"Для специалиста {specialist_id} на дату {date_str} не найдено активных слотов для закрытия.")
            return updated
        except Exception as e:
            logger.error(f"Ошибка в close_day_slots: {e}")
            return False

    def add_log_entry(self, log_data):
        try:
            if self.logs_worksheet:
                self.logs_worksheet.append_row(log_data)
                logger.debug(f"Лог добавлен в Google Sheets: {log_data}")
            else:
                logger.warning("Не удалось добавить лог: logs_worksheet не инициализирован")
        except Exception as e:
            logger.error(f"Ошибка при добавлении лога в Google Sheets: {e}")
            
    def batch_write_logs(self, logs):
        """
        Записывает список логов в Google Sheets.
        Если все записи выполнены успешно – возвращает True, иначе False.
        """
        try:
            self.logs_worksheet.append_rows(logs, value_input_option='RAW')
            logger.info(f"Успешно записаны {len(logs)} логов в Google Sheets.")
            return True
        except Exception as e:
            logger.error(f"Ошибка в batch_write_logs: {e}")
            return False
            
    # Методы для работы со специалистами
    def get_all_specialists(self):
        try:
            return self.specialists_sheet.get_all_records()
        except Exception as e:
            logger.error(f"Ошибка получения специалистов: {e}")
            return []

    def get_specialist_by_id(self, specialist_id):
        try:
            all_specialists = self.specialists_sheet.get_all_records()
            for specialist in all_specialists:
                if str(specialist['id']) == str(specialist_id):
                    return specialist
            return None
        except Exception as e:
            logger.error(f"Ошибка получения специалиста по ID: {e}")
            return None

    def get_specialist_by_ref_link(self, ref_link):
        try:
            all_specialists = self.specialists_sheet.get_all_records()
            for specialist in all_specialists:
                if specialist['Реферальная'] == ref_link:
                    return specialist
            return None
        except Exception as e:
            logger.error(f"Ошибка получения специалиста по реферальной ссылке: {e}")
            return None
            
    def add_specialist(self, name, specialization, timezone, telegram_id=None):
        try:
            # Проверяем, зарегистрирован ли уже пользователь с таким Telegram_ID
            if telegram_id:
                all_specialists = self.specialists_sheet.get_all_records()
                for specialist in all_specialists:
                    if str(specialist.get('Telegram_ID', '')) == str(telegram_id):
                        logger.info(f"Специалист с Telegram_ID {telegram_id} уже существует.")
                        return specialist.get('id')
                        
            # Получаем заголовки для определения порядка столбцов
            headers = self.specialists_sheet.row_values(1)
            
            # Убедимся, что все необходимые колонки существуют
            required_headers = ['id', 'Имя', 'Специализация', 'Часовой пояс', 'Реферальная', 'Telegram_ID']
            for header in required_headers:
                if header not in headers:
                    logger.info(f"Добавляем отсутствующий заголовок '{header}' в лист Специалисты.")
                    col_idx = len(headers) + 1
                    self.specialists_sheet.update_cell(1, col_idx, header)
                    headers.append(header)
            
            # Получаем всех специалистов для определения нового ID
            all_specialists = self.specialists_sheet.get_all_records()
            new_id = 1
            if all_specialists:
                try:
                    new_id = max(int(specialist.get('id', 0)) for specialist in all_specialists) + 1
                except ValueError:
                    logger.warning("Ошибка определения нового ID специалиста. Используем значение по умолчанию.")
            
            # Создаем новый словарь данных специалиста
            new_specialist_data = {
                'id': new_id,
                'Имя': name,
                'Специализация': specialization,
                'Часовой пояс': timezone,
                'Реферальная': '',
                'Telegram_ID': telegram_id or ''
            }
            
            # Добавляем специалиста в таблицу в правильном порядке колонок
            new_specialist_row = [new_specialist_data.get(header, '') for header in headers]
            self.specialists_sheet.append_row(new_specialist_row)
            
            logger.info(f"Добавлен новый специалист: {name}, ID: {new_id}")
            return new_id
        except Exception as e:
            logger.error(f"Ошибка добавления специалиста: {e}", exc_info=True)
            return None
            
    def update_specialist_referral_link(self, specialist_id, referral_link):
        try:
            all_specialists = self.specialists_sheet.get_all_records()
            row_idx = None
            for idx, specialist in enumerate(all_specialists, start=2):
                if str(specialist.get('id', '')) == str(specialist_id):
                    row_idx = idx
                    break
            
            if row_idx:
                headers = self.specialists_sheet.row_values(1)
                col_idx = headers.index('Реферальная') + 1
                self.specialists_sheet.update_cell(row_idx, col_idx, referral_link)
                
                # Также обновляем Telegram_ID, если он есть
                if 'Telegram_ID' in headers and not specialist.get('Telegram_ID'):
                    col_idx_tg = headers.index('Telegram_ID') + 1
                    telegram_id = specialist.get('Telegram_ID', '')
                    self.specialists_sheet.update_cell(row_idx, col_idx_tg, telegram_id)
                
                logger.info(f"Обновлена реферальная ссылка для специалиста ID: {specialist_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Ошибка обновления реферальной ссылки: {e}")
            return False

    def get_specialist_by_telegram_id(self, telegram_id):
        try:
            all_specialists = self.get_all_specialists()
            for specialist in all_specialists:
                if str(specialist.get('Telegram_ID', '')) == str(telegram_id):
                    return specialist
            return None
        except Exception as e:
            logger.error(f"Ошибка при получении специалиста по Telegram ID: {e}")
            return None
            
    def get_client_by_telegram_id(self, telegram_id):
        try:
            all_clients = self.get_all_clients()
            for client in all_clients:
                if str(client.get('Telegram_ID', '')) == str(telegram_id):
                    return client
            return None
        except Exception as e:
            logger.error(f"Ошибка при получении клиента по Telegram ID: {e}")
            return None

    # Методы для работы с клиентами
    def get_all_clients(self):
        try:
            return self.clients_sheet.get_all_records()
        except Exception as e:
            logger.error(f"Ошибка получения клиентов: {e}")
            return []

    def get_client_by_id(self, client_id):
        try:
            all_clients = self.clients_sheet.get_all_records()
            for client in all_clients:
                if str(client['id']) == str(client_id):
                    return client
            return None
        except Exception as e:
            logger.error(f"Ошибка получения клиента по ID: {e}")
            return None

    def get_client_by_phone(self, phone):
        try:
            all_clients = self.clients_sheet.get_all_records()
            for client in all_clients:
                if client['Телефон'] == phone:
                    return client
            return None
        except Exception as e:
            logger.error(f"Ошибка получения клиента по телефону: {e}")
            return None

    def add_client(self, name, phone, specialist_id, telegram_id=None):
        try:
            # Проверяем, зарегистрирован ли уже пользователь с таким Telegram_ID
            if telegram_id:
                all_clients = self.clients_sheet.get_all_records()
                for client in all_clients:
                    if str(client.get('Telegram_ID', '')) == str(telegram_id):
                        logger.info(f"Клиент с Telegram_ID {telegram_id} уже существует.")
                        return client.get('id')
                        
            # Получаем заголовки для определения порядка столбцов
            headers = self.clients_sheet.row_values(1)
            
            # Убедимся, что все необходимые колонки существуют
            required_headers = ['id', 'Имя', 'Телефон', 'id_специалиста', 'Telegram_ID']
            for header in required_headers:
                if header not in headers:
                    logger.info(f"Добавляем отсутствующий заголовок '{header}' в лист Клиенты.")
                    col_idx = len(headers) + 1
                    self.clients_sheet.update_cell(1, col_idx, header)
                    headers.append(header)
            
            # Получаем всех клиентов для определения нового ID
            all_clients = self.clients_sheet.get_all_records()
            new_id = 1
            if all_clients:
                try:
                    new_id = max(int(client.get('id', 0)) for client in all_clients) + 1
                except ValueError:
                    logger.warning("Ошибка определения нового ID клиента. Используем значение по умолчанию.")
            
            # Создаем новый словарь данных клиента
            new_client_data = {
                'id': new_id,
                'Имя': name,
                'Телефон': phone,
                'id_специалиста': specialist_id,
                'Telegram_ID': telegram_id or ''
            }
            
            # Добавляем клиента в таблицу в правильном порядке колонок
            new_client_row = [new_client_data.get(header, '') for header in headers]
            self.clients_sheet.append_row(new_client_row)
            
            logger.info(f"Добавлен новый клиент: {name}, ID: {new_id}")
            return new_id
        except Exception as e:
            logger.error(f"Ошибка добавления клиента: {e}", exc_info=True)
            return None

    # Методы для работы с расписанием
    def get_client_appointments(self, client_id):
        try:
            all_slots = self.schedule_sheet.get_all_records()
            client_slots = []
            for slot in all_slots:
                if str(slot.get('id_клиента', '')) == str(client_id):
                    client_slots.append(slot)
            return client_slots
        except Exception as e:
            logger.error(f"Ошибка получения записей клиента: {e}")
            return []

    def book_appointment(self, slot_id, client_id):
        try:
            all_slots = self.schedule_sheet.get_all_records()
            row_idx = None
            for idx, slot in enumerate(all_slots, start=2):
                if str(slot['id']) == str(slot_id) and slot['Статус'] == 'Свободно':
                    row_idx = idx
                    break
            if row_idx:
                self.schedule_sheet.update_cell(row_idx, 5, 'Занято')
                self.schedule_sheet.update_cell(row_idx, 6, client_id)
                return True
            return False
        except Exception as e:
            logger.error(f"Ошибка бронирования слота: {e}")
            return False

    def cancel_appointment(self, slot_id):
        try:
            all_slots = self.schedule_sheet.get_all_records()
            row_idx = None
            for idx, slot in enumerate(all_slots, start=2):
                if str(slot['id']) == str(slot_id) and slot['Статус'] == 'Занято':
                    row_idx = idx
                    break
            if row_idx:
                self.schedule_sheet.update_cell(row_idx, 5, 'Свободно')
                self.schedule_sheet.update_cell(row_idx, 6, '')
                logger.info(f"Отменена запись, слот ID={slot_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Ошибка отмены бронирования: {e}")
            return False

    def add_schedule_slot(self, date, time, specialist_id):
        try:
            all_slots = self.schedule_sheet.get_all_records()
            new_id = 1
            if all_slots:
                try:
                    new_id = max(int(slot.get('id', 0)) for slot in all_slots) + 1
                except ValueError:
                    logger.warning("Ошибка определения нового ID слота. Используем значение по умолчанию.")
                    
            # Нормализуем дату
            date = self._normalize_date(date)
                
            new_slot = [new_id, date, time, specialist_id, 'Свободно', '']
            self.schedule_sheet.append_row(new_slot)
            return new_id
        except Exception as e:
            logger.error(f"Ошибка добавления слота в расписание: {e}")
            return None

    # Методы для работы с услугами
    def get_specialist_services(self, specialist_id):
        """
        Получает список услуг специалиста из листа "Услуги".
        """
        try:
            services_sheet = self.spreadsheet.worksheet("Услуги")
            all_services = services_sheet.get_all_records()
            specialist_services = [service for service in all_services if str(service.get('id_специалиста', '')) == str(specialist_id)]
            return specialist_services
        except Exception as e:
            logger.error(f"Ошибка получения услуг для специалиста {specialist_id}: {e}")
            return []
    
    # Методы для работы с отзывами
    def add_review(self, client_id, specialist_id, rating, comment=""):
        """
        Добавляет отзыв клиента о специалисте в лист "Отзывы"
        """
        try:
            from datetime import datetime
            date_str = datetime.now().strftime("%Y-%m-%d")
            
            # Добавляем отзыв
            self.reviews_sheet.append_row([client_id, specialist_id, date_str, rating, comment])
            logger.info(f"Добавлен новый отзыв от клиента {client_id} для специалиста {specialist_id}")
            return True
        except Exception as e:
            logger.error(f"Ошибка добавления отзыва: {e}")
            return False
    
    def get_specialist_reviews(self, specialist_id):
        """
        Получает все отзывы о конкретном специалисте
        """
        try:
            all_reviews = self.reviews_sheet.get_all_records()
            specialist_reviews = [
                review for review in all_reviews 
                if str(review.get('id_специалиста', '')) == str(specialist_id)
            ]
            return specialist_reviews
        except Exception as e:
            logger.error(f"Ошибка получения отзывов специалиста {specialist_id}: {e}")
            return []
    
    # Методы для работы с напоминаниями
    def add_reminder(self, appointment_id, client_id, date_str, time_str, status="pending", specialist_id=None, service_name=None):
        """
        Добавляет напоминание о записи в базу данных
        """
        try:
            # Проверяем/создаем лист для напоминаний, если его еще нет
            try:
                reminders_sheet = self.reminders_sheet
            except:
                logger.error("Лист напоминаний не найден")
                return None
            
            # Получаем все напоминания для определения ID
            all_reminders = reminders_sheet.get_all_records()
            new_id = 1
            if all_reminders:
                try:
                    new_id = max(int(reminder.get('id', 0)) for reminder in all_reminders) + 1
                except:
                    logger.warning("Ошибка определения нового ID напоминания. Используем значение по умолчанию.")
            
            # Если specialist_id не указан, получаем его из записи
            if not specialist_id:
                appointments = self.schedule_sheet.get_all_records()
                for appt in appointments:
                    if str(appt.get('id')) == str(appointment_id):
                        specialist_id = appt.get('id_специалиста')
                        break
            
            # Нормализуем дату
            date_str = self._normalize_date(date_str)
            
            # Добавляем напоминание
            reminders_sheet.append_row([new_id, appointment_id, client_id, specialist_id, date_str, time_str, status, service_name or ''])
            
            logger.info(f"Добавлено напоминание ID={new_id} для записи ID={appointment_id}")
            return new_id
        except Exception as e:
            logger.error(f"Ошибка добавления напоминания: {e}", exc_info=True)
            return None

    def update_reminder_status(self, reminder_id, new_status):
        """
        Обновляет статус напоминания
        """
        try:
            try:
                reminders_sheet = self.reminders_sheet
            except:
                logger.error("Лист напоминаний не найден")
                return False
            
            all_reminders = reminders_sheet.get_all_records()
            row_idx = None
            for idx, reminder in enumerate(all_reminders, start=2):
                if str(reminder.get('id')) == str(reminder_id):
                    row_idx = idx
                    break
            
            if row_idx:
                # Получаем индекс колонки статуса
                headers = reminders_sheet.row_values(1)
                status_col = headers.index('Статус') + 1
                
                # Обновляем статус
                reminders_sheet.update_cell(row_idx, status_col, new_status)
                logger.info(f"Обновлен статус напоминания ID={reminder_id} на {new_status}")
                return True
            
            logger.warning(f"Напоминание ID={reminder_id} не найдено")
            return False
        except Exception as e:
            logger.error(f"Ошибка обновления статуса напоминания: {e}", exc_info=True)
            return False

    def get_reminders_by_status(self, status_list):
        """
        Получает список напоминаний с указанным статусом
        
        Args:
            status_list: строка статуса или список статусов
        """
        try:
            try:
                reminders_sheet = self.reminders_sheet
            except:
                logger.error("Лист напоминаний не найден")
                return []
            
            all_reminders = reminders_sheet.get_all_records()
            
            # Преобразуем строку в список если передана одна строка
            if isinstance(status_list, str):
                status_list = [status_list]
            
            # Фильтруем напоминания по статусу
            filtered_reminders = [
                reminder for reminder in all_reminders 
                if reminder.get('Статус', '') in status_list
            ]
            
            return filtered_reminders
        except Exception as e:
            logger.error(f"Ошибка получения напоминаний по статусу: {e}", exc_info=True)
            return []

    def get_reminder_by_id(self, reminder_id):
        """
        Получает напоминание по ID
        """
        try:
            try:
                reminders_sheet = self.reminders_sheet
            except:
                logger.error("Лист напоминаний не найден")
                return None
            
            all_reminders = reminders_sheet.get_all_records()
            for reminder in all_reminders:
                if str(reminder.get('id')) == str(reminder_id):
                    return reminder
            
            return None
        except Exception as e:
            logger.error(f"Ошибка получения напоминания по ID: {e}", exc_info=True)
            return None

    def update_appointment_confirmation(self, appointment_id, confirmed=True):
        """
        Обновляет статус подтверждения записи
        """
        try:
            # Проверяем, есть ли колонка для подтверждения
            headers = self.schedule_sheet.row_values(1)
            if 'Подтверждено' not in headers:
                # Добавляем колонку если её нет
                confirm_col = len(headers) + 1
                self.schedule_sheet.update_cell(1, confirm_col, 'Подтверждено')
                headers.append('Подтверждено')
            
            confirm_col = headers.index('Подтверждено') + 1
            
            # Ищем запись
            all_slots = self.schedule_sheet.get_all_records()
            row_idx = None
            for idx, slot in enumerate(all_slots, start=2):
                if str(slot.get('id')) == str(appointment_id):
                    row_idx = idx
                    break
            
            if row_idx:
                # Обновляем статус подтверждения
                self.schedule_sheet.update_cell(row_idx, confirm_col, 'Да' if confirmed else 'Нет')
                logger.info(f"Обновлен статус подтверждения записи ID={appointment_id} на {confirmed}")
                return True
            
            logger.warning(f"Запись ID={appointment_id} не найдена")
            return False
        except Exception as e:
            logger.error(f"Ошибка обновления статуса подтверждения: {e}", exc_info=True)
            return False

    def update_appointment_feedback_request(self, appointment_id, requested=True):
        """
        Обновляет статус запроса на оценку визита
        """
        try:
            # Проверяем, есть ли колонка для запроса оценки
            headers = self.schedule_sheet.row_values(1)
            if 'Запрос_оценки' not in headers:
                # Добавляем колонку если её нет
                feedback_col = len(headers) + 1
                self.schedule_sheet.update_cell(1, feedback_col, 'Запрос_оценки')
                headers.append('Запрос_оценки')
            
            feedback_col = headers.index('Запрос_оценки') + 1
            
            # Ищем запись
            all_slots = self.schedule_sheet.get_all_records()
            row_idx = None
            for idx, slot in enumerate(all_slots, start=2):
                if str(slot.get('id')) == str(appointment_id):
                    row_idx = idx
                    break
            
            if row_idx:
                # Обновляем статус запроса на оценку
                self.schedule_sheet.update_cell(row_idx, feedback_col, 'Да' if requested else 'Нет')
                logger.info(f"Обновлен статус запроса оценки записи ID={appointment_id} на {requested}")
                return True
            
            logger.warning(f"Запись ID={appointment_id} не найдена")
            return False
        except Exception as e:
            logger.error(f"Ошибка обновления статуса запроса оценки: {e}", exc_info=True)
            return False

    def get_completed_appointments_without_feedback(self):
        """
        Получает список завершенных записей, для которых не был отправлен запрос на оценку
        """
        try:
            all_slots = self.schedule_sheet.get_all_records()
            
            # Проверяем, есть ли колонка для запроса оценки
            if all_slots and 'Запрос_оценки' not in all_slots[0]:
                # Добавляем колонку если её нет
                headers = self.schedule_sheet.row_values(1)
                feedback_col = len(headers) + 1
                self.schedule_sheet.update_cell(1, feedback_col, 'Запрос_оценки')
                
                # Обновляем записи, добавляя пустое значение для новой колонки
                for i in range(2, len(all_slots) + 2):
                    self.schedule_sheet.update_cell(i, feedback_col, '')
                
                # Обновляем данные
                all_slots = self.schedule_sheet.get_all_records()
            
            # Фильтруем записи
            now = datetime.now()
            
            # Получаем завершенные записи без запроса на оценку
            completed_appointments = []
            for slot in all_slots:
                if (slot.get('Статус') == 'Занято' and 
                    slot.get('id_клиента') and 
                    (slot.get('Запрос_оценки', '') != 'Да')):
                    
                    # Проверяем, прошла ли запись (время приема + его длительность)
                    try:
                        slot_date = self._normalize_date(slot.get('Дата', ''))
                        appt_date = datetime.strptime(slot_date, '%Y-%m-%d').date()
                        appt_time = datetime.strptime(slot.get('Время', ''), '%H:%M').time()
                        appt_dt = datetime.combine(appt_date, appt_time)
                        
                        # Получаем продолжительность из записи или устанавливаем по умолчанию
                        duration = int(slot.get('Продолжительность', 30))
                        end_dt = appt_dt + timedelta(minutes=duration)
                        
                        # Если запись завершилась + прошел 1 час, добавляем в список
                        if (now - end_dt).total_seconds() >= 3600:  # 3600 секунд = 1 час
                            completed_appointments.append(slot)
                    except Exception as e_date:
                        logger.warning(f"Ошибка при проверке даты записи: {e_date}")
            
            return completed_appointments
        except Exception as e:
            logger.error(f"Ошибка получения завершенных записей: {e}", exc_info=True)
            return []

    def get_appointment_by_id(self, appointment_id):
        """
        Получает запись по ID
        """
        try:
            all_slots = self.schedule_sheet.get_all_records()
            for slot in all_slots:
                if str(slot.get('id')) == str(appointment_id):
                    return slot
            return None
        except Exception as e:
            logger.error(f"Ошибка получения записи по ID: {e}", exc_info=True)
            return None

    def get_specialist_appointments_by_date(self, specialist_id, date_str):
        """
        Получает все записи специалиста на указанную дату
        """
        try:
            all_slots = self.schedule_sheet.get_all_records()
            appointments = []
            
            # Нормализуем дату для сравнения
            normalized_date = self._normalize_date(date_str)
            
            # Проверяем и логируем первые несколько слотов для отладки
            debug_count = 0
            for slot in all_slots:
                if debug_count < 5 and str(slot.get('id_специалиста')) == str(specialist_id):
                    slot_date = slot.get('Дата', '')
                    normalized_slot_date = self._normalize_date(slot_date)
                    logger.debug(f"Слот специалиста {specialist_id}: дата в слоте='{slot_date}', нормализованная='{normalized_slot_date}', искомая='{normalized_date}'")
                    debug_count += 1
                
                slot_date = self._normalize_date(slot.get('Дата', ''))
                
                if (str(slot.get('id_специалиста')) == str(specialist_id) and 
                    slot_date == normalized_date and 
                    slot.get('Статус') == 'Занято' and 
                    slot.get('id_клиента')):
                    appointments.append(slot)
            
            logger.info(f"Найдено {len(appointments)} записей для специалиста {specialist_id} на дату {date_str}")
            return appointments
        except Exception as e:
            logger.error(f"Ошибка получения записей специалиста на дату: {e}", exc_info=True)
            return []