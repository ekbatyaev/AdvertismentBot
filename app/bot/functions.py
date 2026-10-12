import asyncio, pandas as pd
from io import BytesIO
from openpyxl.workbook import Workbook
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
from openpyxl.utils import get_column_letter
from app.settings import logger, MOSCOW_TZ
from app.bot.config import bot
from app.ai.functions.ad_analysis import analyze_text
from maxapi.types import InputMedia, InputMediaBuffer
from maxapi.exceptions.max import MaxApiError, MaxConnection, MaxUploadFileFailed
from maxapi.enums.upload_type import UploadType
from maxapi.enums.parse_mode import TextFormat
from maxapi.context.base import BaseContext
from maxapi.types.chats import Chat
from maxapi.enums.chat_type import ChatType
from maxapi.enums.chat_permission import ChatPermission
from app.bot.schemas import BotPermissions, SendAnalysis, DateValidation
from aiohttp import ClientError
from app.bot.states import NavigateStates
from app.bot.keyboards import option_user_choice
import re
from datetime import datetime
from maxapi.types.message import Message
from maxapi.utils.time import to_ms

PAGE_LIMIT_MAX = 100
_PARSER_SEMAPHORE = asyncio.Semaphore(4)
_DOC_CREATION_SEMAPHORE = asyncio.Semaphore(4)

# Безопасная отправка документа

async def check_bot_channel_permissions(chat_id: int) -> BotPermissions:
    try:
        bot_info = await bot.get_me_from_chat(chat_id)
    except MaxApiError:
        return BotPermissions(permission_to_read=False,
                         bot_channel_status="Бот не добавлен в канал.")
    if not bot_info.is_admin:
        return BotPermissions(permission_to_read = False,
                         bot_channel_status = "Бот добавлен в канал, но не является администратором.")
    if ChatPermission.READ_ALL_MESSAGES not in (bot_info.permissions or []):
        return BotPermissions(permission_to_read = False,
                         bot_channel_status = "Бот не имеет права «Читать все сообщения».")
    return BotPermissions(permission_to_read = True,
                     bot_channel_status = "Бот обладает всеми нужными правами.")

async def check_channel_by_url(link: str) -> Chat | None:
    """Ссылка/алиас -> Chat или None."""
    try:
        chat = await bot.get_chat_by_link(link)
    except (ValueError, MaxApiError):
        return None
    return chat if chat.type == ChatType.CHANNEL else None

async def send_welcome(event, chat_id: int, user, context: BaseContext):
    username = user.username or user.first_name
    welcome_message = await event.bot.send_message(
        chat_id=chat_id,
        text=(
            f"Привет, **{username}**!\n\n"
            "Я являются ботом компании **Systeme Electric**, созданным для проверки "
            "сообщений на **наличие рекламы.**\n\nБуду рад помочь 🤝"
        ),
        attachments=[option_user_choice()],
        format=TextFormat.MARKDOWN,
    )
    logger.info(f"Пользователь {user.user_id} начал беседу")
    await context.update_data(last_message_id=welcome_message.message.body.mid)
    await context.set_state(NavigateStates.option_user_choice)

async def get_channel_messages(
    chat_id: int,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[Message]:
    """Сообщения канала за [start, end] от старых к новым.

    start=None — с начала истории, end=None — до текущего момента.
    """
    start_ms = to_ms(start) if start else None
    end_ms = to_ms(end) if end else None

    # Текущее окно запроса; None = граница не передаётся в API
    low, high = start_ms, end_ms
    result: dict[str, Message] = {}

    while True:
        batch = (await bot.get_messages(
            chat_id=chat_id,
            from_time=low,
            to_time=high,
            count=PAGE_LIMIT_MAX,
        )).messages

        new = 0
        for m in batch:
            if m.body and m.body.mid not in result:
                result[m.body.mid] = m
                new += 1

        if len(batch) < PAGE_LIMIT_MAX or new == 0:
            break  # окно исчерпано или нет прогресса

        # Определяем, в какую сторону сервер отдаёт сообщения,
        # и сдвигаем ту границу, от которой он «обрезал» пачку.
        first, last = batch[0].timestamp, batch[-1].timestamp
        if first >= last:              # от новых к старым
            high = min(m.timestamp for m in batch)
        else:                          # от старых к новым
            low = max(m.timestamp for m in batch)
        # без ±1: сообщения с той же мс не теряются, дубли отсекает result

        if low is not None and high is not None and high < low:
            break

    # Финальная проверка периода на нашей стороне
    messages = [
        m for m in result.values()
        if (start_ms is None or m.timestamp >= start_ms)
        and (end_ms is None or m.timestamp <= end_ms)
    ]
    return sorted(messages, key=lambda m: m.timestamp)

async def run_channel_analysis(message: Message, context: BaseContext,
                               chat_id: int, start_date, end_date):
    """Общий хвост: запуск анализа, вывод ошибок, возврат в меню."""
    data = await context.get_data()
    channel_chat_id = data.get("channel_chat_id")
    channel_name = data.get("channel_name")
    await asyncio.sleep(0.5)
    ai_answer = (await message.answer("*Искусственный интеллект обрабатывает ваш запрос, он может занять продолжительное время...*",
                                      format=TextFormat.MARKDOWN)).message
    async with _PARSER_SEMAPHORE:
        messages_to_analysis = await asyncio.to_thread(get_channel_messages, channel_chat_id, start_date, end_date)

    async with _DOC_CREATION_SEMAPHORE:
        analysis_result: SendAnalysis = await asyncio.to_thread(send_analysis, messages_to_analysis, channel_name, chat_id)

    await ai_answer.delete()
    await asyncio.sleep(0.5)
    if not analysis_result.analysis_sent_status:
        await message.answer(f"К сожалению, при проведения анализа произошла следующая ошибка:\n{analysis_result.status_description}")
    last_message = await message.answer("Выбери дальнейшую опцию", attachments=[option_user_choice()])
    await context.update_data(last_message_id=last_message.message.body.mid)
    await context.set_state(NavigateStates.option_user_choice)

async def edit_last_message(context: BaseContext, **kwargs):
    """Редактирует сообщение, ID которого сохранён в FSM."""
    data = await context.get_data()
    mid = data.get("last_message_id")
    if mid:
        await bot.edit_message(message_id=mid, **kwargs)

async def safe_send_document(document: InputMedia | InputMediaBuffer,
                             **kwargs):
    for attempt in range(3):
        try:
            return await bot.send_message(
                attachments = [document],
                **kwargs
            )
        except (MaxConnection, MaxUploadFileFailed, MaxApiError,
                ClientError, asyncio.TimeoutError) as e:
            logger.error(f"Ошибка: {e}")
            if attempt == 2:
                raise
            await asyncio.sleep(2)


# Проверка валидности даты

async def validate_date_pair(date_string: str) -> DateValidation:
    base_pattern = r'^(\d{2})\.(\d{2})\.(\d{4}) (\d{2})\.(\d{2})\.(\d{4})$'
    match = re.match(base_pattern, date_string)

    if not match:
        return DateValidation(
            validation_status = False,
            status_description = "Неверный формат. Нужно: день.месяц.год день.месяц.год"
        )

    d1, m1, y1, d2, m2, y2 = map(int, match.groups())
    current_date = datetime.now(MOSCOW_TZ).replace(tzinfo=None)

    if not (1 <= m1 <= 12):
        return DateValidation(
            validation_status = False,
            status_description = f"Неверный месяц в первой дате: {m1:02d}. Месяц должен быть от 01 до 12."
        )

    try:
        date1 = datetime(y1, m1, d1)
    except ValueError:
        if d1 < 1 or d1 > 31:
            msg = f"Неверный день в первой дате: {d1:02d}. День должен быть от 01 до 31."
        elif m1 == 2 and d1 > 29:
            msg = f"В феврале не может быть {d1:02d} дня. Проверьте високосный год."
        elif m1 in [4, 6, 9, 11] and d1 > 30:
            msg = f"В {m1:02d}-м месяце только 30 дней."
        else:
            msg = f"Некорректная первая дата: {d1:02d}.{m1:02d}.{y1:04d}"

        return DateValidation(
            validation_status = False,
            status_description = msg
        )

    if date1 > current_date:
        return DateValidation(
            validation_status = False,
            status_description = f"Первая дата ({date1.strftime('%d.%m.%Y')}) ещё не наступила!"
        )

    if not (1 <= m2 <= 12):
        return DateValidation(
            validation_status =  False,
            status_description = f"Неверный месяц во второй дате: {m2:02d}. Месяц должен быть от 01 до 12."
        )

    try:
        date2 = datetime(y2, m2, d2)
    except ValueError:
        if d2 < 1 or d2 > 31:
            msg = f"Неверный день во второй дате: {d2:02d}. День должен быть от 01 до 31."
        elif m2 == 2 and d2 > 29:
            msg = f"В феврале не может быть {d2:02d} дня. Проверьте високосный год."
        elif m2 in [4, 6, 9, 11] and d2 > 30:
            msg = f"В {m2:02d}-м месяце только 30 дней."
        else:
            msg = f"Некорректная вторая дата: {d2:02d}.{m2:02d}.{y2:04d}"

        return DateValidation(
            validation_status = False,
            status_description =  msg
        )

    if date2 > current_date:
        return DateValidation(
            validation_status = False,
            status_description = f"Вторая дата ({date2.strftime('%d.%m.%Y')}) ещё не наступила!"
        )

    if date2 < date1:
        return DateValidation(
            validation_status = False,
            status_description = (
                f"Вторая дата ({date2.strftime('%d.%m.%Y')}) "
                f"раньше первой ({date1.strftime('%d.%m.%Y')})!"
            )
        )

    return DateValidation(
        validation_status = True,
        status_description = "Даты прошли валидацию."
    )


async def send_analysis(messages: list[Message], channel_name: str, chat_id: int) -> SendAnalysis:

    if not messages:
        logger.warning("Сообщений за указанный период анализа канала нет.")
        return SendAnalysis(analysis_sent_status = False, status_description = "Сообщений за указанный период не найдено")

    datum = []

    for message in messages:

        post_text = message.body.text if message.body else None
        if not post_text:
            continue

        answer_list = await analyze_text(text = post_text, temperature = 0.4)

        if answer_list:
            violations_flag = any(answer["fine"] > 0 for answer in answer_list)
        else:
            logger.error(f"Ошибка при обработке запроса:\n\n{post_text}")
            answer_list = []
            violations_flag = False

        descriptions = ""
        recommendations = ""

        if violations_flag:
            answer_list = sorted(answer_list, key=lambda answer: answer["fine"], reverse=True)

        for i, answer in enumerate(answer_list):
            descriptions += f"{str(i + 1)}) Описание:\n" + answer[
                "description"] + "\n\nВозможный штраф: " + str(answer["fine"]) + "\n\n"
            recommendations += f"{str(i + 1)}) Рекомендация:\n" + answer["recommendation"] + "\n\n"

        cell = {
            "Текст публикации": post_text,
            "Наличие нарушений": "Присутствуют 🚨" if violations_flag == True else "Отсутствуют ✅",
            "Описание": descriptions,
            "Рекомендации": recommendations
        }
        datum.append(cell)

    df = pd.DataFrame(datum)

    wb = Workbook()
    ws = wb.active

    # Ограничиваем имя листа до 31 символа
    sheet_title = f"Анализ {channel_name}"[:31]
    ws.title = sheet_title

    filename = f"Анализ канала {channel_name}.xlsx"

    # Настройки стилей
    header_font = Font(name='Arial', size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
    thin_border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )

    cell_alignment = Alignment(
        vertical='top',
        horizontal='left',
        wrap_text=True
    )

    # Записываем заголовки
    for col_idx, column_name in enumerate(df.columns, 1):
        cell = ws.cell(row=1, column=col_idx, value=str(column_name))
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(vertical='center', horizontal='center')
        cell.border = thin_border

    # Записываем данные
    for row_idx, row in enumerate(df.itertuples(index=False), 2):
        for col_idx, value in enumerate(row, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=str(value))
            cell.alignment = cell_alignment
            cell.border = thin_border

    # Автоподбор ширины колонок с учетом переноса текста
    for column in ws.columns:
        max_length = 0
        column_letter = get_column_letter(column[0].column)

        # Находим максимальную длину текста в колонке
        for cell in column:
            if cell.value:
                # Учитываем перенос строк
                lines = str(cell.value).split('\n')
                max_line_length = max(len(line) for line in lines)
                max_length = max(max_length, max_line_length)

        # Устанавливаем ширину (ограничиваем максимум 50 символов)
        adjusted_width = min(max_length + 2, 50)
        ws.column_dimensions[column_letter].width = adjusted_width

    # Устанавливаем высоту строк для лучшего отображения
    for row in ws.iter_rows(min_row=2):
        max_lines = 1
        for cell in row:
            if cell.value:
                lines = str(cell.value).count('\n') + 1
                max_lines = max(max_lines, lines)
        ws.row_dimensions[row[0].row].height = max_lines * 15

    # Замораживаем заголовки
    ws.freeze_panes = 'A2'

    excel_buffer = BytesIO()
    wb.save(excel_buffer)
    excel_buffer.seek(0)

    excel_file = InputMediaBuffer(
        buffer = excel_buffer.read(),
        filename=filename,
        type = UploadType.FILE
    )

    try:
        # Отправляем файл
        await safe_send_document(
            chat_id = chat_id,
            document=excel_file,
            text=f"📊 Анализ постов канала {channel_name} ({datetime.now().strftime('%d.%m.%Y %H:%M')})"
        )
        return SendAnalysis(analysis_sent_status = True, status_description = "Анализ успешно отправлен.")
    except Exception as e:
        logger.error(f"Ошибка отправки файла: {e}")
        return SendAnalysis(analysis_sent_status = False, status_description = "Ошибка отправки документа с анализом")
    finally:
        logger.info(f"Обработано {len(datum)} из {len(messages)} постов")