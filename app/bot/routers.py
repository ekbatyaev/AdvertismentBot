import asyncio
from dateutil.relativedelta import relativedelta
from datetime import datetime, timedelta
from maxapi.exceptions import MaxApiError
from app.settings import settings, logger, MOSCOW_TZ
from app.functions import load_data
from app.bot.states import NavigateStates, AnalyzeStates
from app.bot.functions import safe_send_document, validate_date_pair, edit_last_message, run_channel_analysis
from app.bot.keyboards import option_user_choice, option_user_go_back, option_user_choose_time_interval
from app.ai.functions.ad_analysis import analyze_text
from maxapi import Router, F
from maxapi.context.base import BaseContext
from maxapi.enums.parse_mode import TextFormat
from maxapi.enums.upload_type import UploadType
from maxapi.types import InputMedia, MessageCreated, MessageCallback
from maxapi.filters.command import CommandStart, Command

# Инициализация путей использования бота
user_router = Router(router_id = "user")

@user_router.message_created(Command("secret_admin_statistics_request"))
async def handle_admin_request(event:  MessageCreated, context: BaseContext):
    await asyncio.sleep(0.5)
    now = datetime.now(MOSCOW_TZ).replace(tzinfo=None)
    month = now.strftime("%B").lower()
    file_name = settings.ai_logs_dir / f"{month}_logs_{now.year}.json"
    data = await load_data(file_name)
    if not data:
        await event.message.answer("За текущий месяц запросов ещё не было.")
        return
    summ_input_tokens, summ_output_tokens, summ_mc_time = 0, 0, 0
    for cell in data:
        summ_input_tokens += cell["input_tokens"]
        summ_output_tokens += cell["output_tokens"]
        summ_mc_time += cell["Время ответа в мс"]
    await event.message.answer(
        f"📊 *Cтатистика за последний календарный месяц*" + "\n\n" +
        f"Количество запросов к модели: **{len(data)}**\n" + f"Среднее количество входящих токенов: **{summ_input_tokens // len(data)}**\n" +
        f"Среднее количество исходящих токенов: **{summ_output_tokens // len(data)}**\n" + f"Среднее время ответа (мс): **{summ_mc_time // len(data)}**\n",
        format = TextFormat.MARKDOWN
    )
    try:
        # Отправляем файл
        await safe_send_document(
                                 chat_id = event.message.recipient.chat_id,
                                document = InputMedia(str(file_name), type = UploadType.FILE),
                                 text = f"📊 Статистика постов ({datetime.now().strftime('%d.%m.%Y %H:%M')})"
                                 )
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await asyncio.sleep(0.5)
        await event.message.answer("Отправить документ не удалось, попробуйте позже")

# Начальный блок сообщений с выбором варианта использования бота
@user_router.message_created(CommandStart())
async def handle_start_message(event: MessageCreated, context: BaseContext):
    await asyncio.sleep(0.5)
    sender = event.message.sender
    username = sender.username or sender.first_name
    welcome_message = await event.message.answer(
        f"Привет, **{username}**!\n\nЯ являются ботом компании **Systeme Electric**, созданным для проверки сообщений на **наличие рекламы.**\n\nБуду рад помочь 🤝",
        attachments=[option_user_choice()], format = TextFormat.MARKDOWN,
    )
    logger.info(f"Пользователь {sender.user_id} начал беседу")
    await context.update_data(last_message_id = welcome_message.message.body.mid)
    await context.set_state(NavigateStates.option_user_choice)


@user_router.message_created(F.message.body.text, NavigateStates.option_user_choice)
async def attention_message_to_user(event: MessageCreated, context: BaseContext):
    await asyncio.sleep(0.5)
    await event.message.answer("Пожалуйста, выбери одну из опций выше.")


@user_router.message_callback(F.callback.payload == 'message_check',
                              NavigateStates.option_user_choice)
async def option_message_check(event: MessageCallback, context: BaseContext):
    await asyncio.sleep(0.5)
    logger.info(f"Пользователь {event.callback.user.user_id} запустил анализ сообщения")
    await event.edit(text="Пришли мне **текст сообщения** 📝",
                                    attachments=[option_user_go_back()], format=TextFormat.MARKDOWN)
    await context.set_state(AnalyzeStates.message_analyze)


@user_router.message_callback(F.callback.payload == 'back', AnalyzeStates.message_analyze)
async def back_to_previous(event: MessageCallback, context: BaseContext):
    await asyncio.sleep(0.5)
    user = event.callback.user
    username = user.username or user.first_name
    await event.edit(
        text=f"Привет, **{username}**!\n\nЯ являются ботом компании **Systeme Electric**, созданным для проверки сообщений на **наличие рекламы.**\n\nБуду рад помочь 🤝",
        attachments=[option_user_choice()], format = TextFormat.MARKDOWN)
    await context.set_state(NavigateStates.option_user_choice)


@user_router.message_created(F.message.body.text, AnalyzeStates.message_analyze)
async def message_analyze(event: MessageCreated,
                          context: BaseContext):
    text = event.message.body.text
    await edit_last_message(context, text="Пришли мне **текст сообщения** 📝",
                                 format = TextFormat.MARKDOWN)
    await asyncio.sleep(0.5)

    ai_answer = (await event.message.answer(
        "*Искусственный интеллект обрабатывает ваш запрос..*",
        format = TextFormat.MARKDOWN)).message

    answer_list = await analyze_text(text = text, temperature = 0.4)
    logger.info(text)
    if not answer_list:
        await ai_answer.edit(text="Пожалуйста, попробуйте позже.")
        logger.error(f"Ошибка обработки сообщения: {text}")
        return

    violations_flag = any(answer["fine"] > 0 for answer in answer_list)

    if violations_flag:
        answer_list = sorted(answer_list, key=lambda answer: answer["fine"], reverse=True)

    descriptions = ""
    for i, answer in enumerate(answer_list):
        descriptions += f"**{str(i + 1)}) Описание:**\n" + answer["description"] + "\n\n**Возможный штраф:** " + str(
            answer["fine"]) + "\n\n**Рекомендация:**\n" + answer["recommendation"] + "\n\n"

    violation_status = "Присутствуют 🚨" if violations_flag else "Отсутствуют ✅"

    try:
        final_answer_to_user = f"**Результаты анализа 🔍**\n\n**Нарушения:** {violation_status}\n\n{descriptions}"
        await ai_answer.edit(text=final_answer_to_user, format = TextFormat.MARKDOWN)

    except (MaxApiError, ValueError) as e:
        logger.error(f"Ошибка: {e}")
        descriptions = ""
        for i, answer in enumerate(answer_list):
            descriptions += f"{str(i + 1)}) Описание:\n" + answer["description"] + "\n\nВозможный штраф: " + str(
                answer["fine"]) + "\n\nРекомендация:\n" + answer["recommendation"] + "\n\n"

        violation_status = "Присутствуют 🚨" if violations_flag else "Отсутствуют ✅"

        final_answer_to_user = f"Результаты анализа 🔍\n\nНарушения: {violation_status}\n\n{descriptions}"
        await ai_answer.edit(text=final_answer_to_user)
    logger.info(final_answer_to_user)
    await asyncio.sleep(0.5)
    last_message = await event.message.answer("Выбери дальнейшую опцию",
                                              attachments = [option_user_choice()])
    await context.update_data(last_message_id = last_message.message.body.mid)
    await context.set_state(NavigateStates.option_user_choice)


@user_router.message_callback(F.callback.payload == 'channel_check',
                              NavigateStates.option_user_choice)
async def option_channel_check(event: MessageCallback, context: BaseContext):
    await asyncio.sleep(0.5)
    logger.info(f"Пользователь {event.callback.user.user_id} запустил анализ канала")
    await event.edit(text="Пришли мне **тег канала** в формате **@systemeelectric_official** 🔗",
                                 attachments = [option_user_go_back()], format = TextFormat.MARKDOWN)
    await context.set_state(NavigateStates.get_channel_name)


@user_router.message_callback(F.callback.payload == 'back',
                              NavigateStates.get_channel_name, NavigateStates.get_time_choice)
async def back_to_previous(event: MessageCallback, context: BaseContext):
    await asyncio.sleep(0.5)
    await event.edit(text = "Выбери дальнейшую опцию", attachments = [option_user_choice()])
    await context.set_state(NavigateStates.option_user_choice)


@user_router.message_created(F.message.body.text, NavigateStates.get_channel_name)
async def check_bot_rights(event: MessageCreated, context: BaseContext):
    await asyncio.sleep(0.5)
    text = event.message.body.text.strip()
    logger.info(text)
    if "https://t.me/" in text:
        text = text.replace("https://t.me/", "@")
    if not text.startswith("@"):
        await asyncio.sleep(0.5)
        await event.message.answer("Пожалуйста, пришли тег канала в формате **@systemeelectric_official** 🔗",
                                format = TextFormat.MARKDOWN)
        logger.warning(f"Неправильное название канала: {text}")
        return
    await edit_last_message(context,
                            text=f"Канал для проверки: {text}")
    await asyncio.sleep(0.5)
    last_message = await event.message.answer("Какой период постов нужно проверить?",
                                        attachments = [option_user_choose_time_interval()])
    await context.update_data(channel_name = text,
                              last_message_id = last_message.message.body.mid)
    await context.set_state(NavigateStates.get_time_choice)

@user_router.message_callback(F.callback.payload == 'all_posts',
                              NavigateStates.get_time_choice)
async def get_all_timestamp(event: MessageCallback, context: BaseContext):
    await asyncio.sleep(0.5)
    await event.edit(
        text=f"Ты выбрал анализ **всех постов** в канале. Он может занять **продолжительное время** ⏱️.",
        attachments=[], format = TextFormat.MARKDOWN)

    await run_channel_analysis(event.message, context, None, None, event.callback.user.user_id,
                         "*Искусственный интеллект обрабатывает ваш запрос...*")


@user_router.message_callback(F.callback.payload.in_({"week", "month", "year"}), NavigateStates.get_time_choice)
async def get_exact_timestamp(event: MessageCallback,
                              context: BaseContext):
    await asyncio.sleep(0.5)
    period = event.callback.payload
    end_time = datetime.now()
    dict_dates = {
        "week": {
            "date": (end_time - timedelta(weeks=1)).strftime("%d.%m.%Y"),
            "message": "Ты выбрал анализ постов за **последнюю неделю**."},
        "month": {
            "date": (end_time - relativedelta(months=1)).strftime("%d.%m.%Y"),
            "message": "Ты выбрал анализ постов за **последний месяц**.\n\nОн может занять **продолжительное время** ⏱️."},
        "year": {
            "date": (end_time - relativedelta(years=1)).strftime("%d.%m.%Y"),
            "message": "Ты выбрал анализ постов за **последний год**.\n\nОн может занять **продолжительное время** ⏱️."}
    }
    await event.edit(text=dict_dates[period]["message"], attachments=[], format=TextFormat.MARKDOWN)
    await run_channel_analysis(event.message, context, dict_dates[period]["date"], end_time.strftime("%d.%m.%Y"),
                               event.callback.user.user_id, "*Искусственный интеллект обрабатывает ваш запрос...*")


@user_router.message_callback(F.callback.payload == 'interval', NavigateStates.get_time_choice)
async def get_timestamps_interval(event: MessageCallback, context: BaseContext):
    await asyncio.sleep(0.5)
    await event.edit(
        text="Ты выбрал анализ постов **определенного временного промежутка**.\n\nПожалуйста, пришли мне **дату начала** и **дату конца интервала** в формате день.месяц.год .\n\n**Например:** 08.12.2025 26.12.2025",
        attachments=[option_user_go_back()], format=TextFormat.MARKDOWN)
    await context.set_state(NavigateStates.get_interval)


@user_router.message_callback(F.callback.payload == 'back', NavigateStates.get_interval)
async def back_to_time_choice(event: MessageCallback, context: BaseContext):
    await asyncio.sleep(0.5)
    await event.edit(text="Какой период постов нужно проверить?",
                     attachments=[option_user_choose_time_interval()])
    await context.set_state(NavigateStates.get_time_choice)


@user_router.message_created(F.message.body.text, NavigateStates.get_interval)
async def get_interval(event: MessageCreated, context: BaseContext):
    await asyncio.sleep(0.5)
    text = event.message.body.text
    valid_dict = await validate_date_pair(text)
    if not valid_dict.get("valid"):
        await event.message.answer(valid_dict.get("message"))
        return
    await asyncio.sleep(0.5)
    await edit_last_message(context, text=f"Твой выбранный промежуток: **{text}**",
                            format=TextFormat.MARKDOWN)
    dates = text.split()
    await run_channel_analysis(event.message, context, dates[0], dates[1], event.message.sender.user_id,
                               "*Искусственный интеллект обрабатывает ваш запрос, он может занять продолжительное время...*")