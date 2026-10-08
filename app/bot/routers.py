import asyncio
from dateutil.relativedelta import relativedelta
from datetime import datetime, timedelta
from aiogram import F, types
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile, CallbackQuery
from app.settings import logger, MOSCOW_TZ
from app.functions import load_data
from app.bot.states import NavigateStates, AnalyzeStates
from app.bot.functions import safe_send_document, get_channel_analysis, validate_date_pair
from app.bot.keyboards import option_user_choice, option_user_go_back, option_user_choose_time_interval
from app.ai.functions.ad_analysis import analyze_text
from aiogram import Router

# Инициализация путей использования бота
user_router = Router()

@user_router.message(Command("secret_admin_statistics_request"))
async def handle_admin_request(message: types.Message, state: FSMContext):
    await asyncio.sleep(0.5)
    now = datetime.now(MOSCOW_TZ).replace(tzinfo=None)
    month = now.strftime("%B").lower()
    file_name = f"logs/{month}_logs_{now.year}.json"
    data = await load_data(file_name)
    summ_input_tokens, summ_output_tokens, summ_mc_time = 0, 0, 0
    for cell in data:
        summ_input_tokens += cell["input_tokens"]
        summ_output_tokens += cell["output_tokens"]
        summ_mc_time += cell["Время ответа в мс"]
    await message.answer(
        f"📊 _Cтатистика за последний календарный месяц_" + "\n\n" +
        f"Количество запросов к модели: *{len(data)}*\n" + f"Среднее количество входящих токенов: *{summ_input_tokens // len(data)}*\n" +
        f"Среднее количество исходящих токенов: *{summ_output_tokens // len(data)}*\n" + f"Среднее время ответа (мс): *{summ_mc_time // len(data)}*\n",
        parse_mode="Markdown"
    )
    try:
        # Отправляем файл
        await safe_send_document(
                                 chat_id=message.from_user.id,
                                 document=FSInputFile(file_name),
                                 caption=f"📊 Статистика постов ({datetime.now().strftime('%d.%m.%Y %H:%M')})"
                                 )
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await asyncio.sleep(0.5)
        await message.answer("Отправить документ не удалось, попробуйте позже")
    finally:
        return

# Начальный блок сообщений с выбором варианта использования бота
@user_router.message(CommandStart())
async def handle_start_message(message: types.Message, state: FSMContext):
    await asyncio.sleep(0.5)
    username = message.from_user.username
    welcome_message = await message.answer(
        f"Привет, *{username}*!\n\nЯ являются телеграмм-ботом компании *Systeme Electric*, созданным для проверки сообщений на *наличие рекламы.*\n\nБуду рад помочь 🤝",
        reply_markup=option_user_choice(), parse_mode="Markdown"
    )
    logger.info(f"User {message.from_user.id} started conversation")
    await state.update_data(last_message=welcome_message)
    await state.set_state(NavigateStates.option_user_choice)


@user_router.message(F.text, NavigateStates.option_user_choice)
async def attention_message_to_user(message: types.Message, state: FSMContext):
    await asyncio.sleep(0.5)
    await message.answer(f"Пожалуйста, выбери одну из опций выше.", parse_mode="Markdown")
    await state.set_state(NavigateStates.option_user_choice)


@user_router.callback_query(F.data == 'message_check', NavigateStates.option_user_choice)
async def option_message_check(call: CallbackQuery, state: FSMContext):
    await asyncio.sleep(0.5)
    data = await state.get_data()
    last_message = data.get("last_message")
    logger.info(f"User {call.from_user.id} started message analysis", call.from_user.id)
    await last_message.edit_text(text="Пришли мне *текст сообщения* 📝",
                                 reply_markup=option_user_go_back(), parse_mode="Markdown")
    await state.set_state(AnalyzeStates.message_analyze)


@user_router.callback_query(F.data == 'back', AnalyzeStates.message_analyze)
async def back_to_previous(message: types.Message, state: FSMContext):
    await asyncio.sleep(0.5)
    data = await state.get_data()
    last_message = data.get("last_message")
    username = message.from_user.username
    await last_message.edit_text(
        text=f"Привет, *{username}*!\n\nЯ являются телеграмм-ботом компании *Systeme Electric*, созданным для проверки сообщений на *наличие рекламы.*\n\nБуду рад помочь 🤝",
        reply_markup=option_user_choice(), parse_mode="Markdown")
    await state.set_state(NavigateStates.option_user_choice)


@user_router.message((F.text | F.caption), AnalyzeStates.message_analyze)
async def message_analyze(message: types.Message, state: FSMContext):
    data = await state.get_data()
    last_message = data.get("last_message")
    text = message.text or message.caption
    await last_message.edit_text(text="Пришли мне *текст сообщения* 📝",
                                 reply_markup=None, parse_mode="Markdown")
    await asyncio.sleep(0.5)
    ai_answer = await message.answer("_Искусственный интеллект обрабатывает ваш запрос.._", parse_mode="Markdown")
    answer_list = await analyze_text(text = text, temperature = 0.4)
    logger.info(text)
    if not answer_list:
        await ai_answer.edit_text(text="Пожалуйста, попробуйте позже.")
        logger.error(f"Ошибка обработки сообщения: {text}")
        return

    violations_flag = any(answer["fine"] > 0 for answer in answer_list)

    if violations_flag:
        answer_list = sorted(answer_list, key=lambda answer: answer["fine"], reverse=True)

    descriptions = ""
    for i, answer in enumerate(answer_list):
        descriptions += f"*{str(i + 1)}) Описание:*\n" + answer["description"] + "\n\n*Возможный штраф:* " + str(
            answer["fine"]) + "\n\n*Рекомендация:*\n" + answer["recommendation"] + "\n\n"

    violation_status = "Присутствуют 🚨" if violations_flag else "Отсутствуют ✅"

    try:
        final_answer_to_user = f"*Результаты анализа 🔍*\n\n*Нарушения: *{violation_status}\n\n{descriptions}"
        await ai_answer.edit_text(text=final_answer_to_user, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Ошибка: {e}")
        descriptions = ""
        for i, answer in enumerate(answer_list):
            descriptions += f"{str(i + 1)}) Описание:\n" + answer["description"] + "\n\nВозможный штраф: " + str(
                answer["fine"]) + "\n\nРекомендация:\n" + answer["recommendation"] + "\n\n"

        violation_status = "Присутствуют 🚨" if violations_flag else "Отсутствуют ✅"

        final_answer_to_user = f"Результаты анализа 🔍\n\nНарушения: {violation_status}\n\n{descriptions}"
        await ai_answer.edit_text(text=final_answer_to_user, parse_mode=None)
    logger.info(final_answer_to_user)
    await asyncio.sleep(0.5)
    last_message = await message.answer("Выбери дальнейшую опцию", reply_markup=option_user_choice())
    await state.update_data(last_message=last_message)
    await state.set_state(NavigateStates.option_user_choice)


@user_router.callback_query(F.data == 'channel_check', NavigateStates.option_user_choice)
async def option_channel_check(call: CallbackQuery, state: FSMContext):
    await asyncio.sleep(0.5)
    data = await state.get_data()
    last_message = data.get("last_message")
    logger.info(f"User {call.from_user.id} started channel analysis")
    await last_message.edit_text(text="Пришли мне *тег канала* в формате *@systemeelectric_official* 🔗",
                                 reply_markup=option_user_go_back(), parse_mode="Markdown")
    await state.set_state(NavigateStates.get_channel_name)


@user_router.callback_query(F.data == 'back', NavigateStates.get_channel_name)
async def back_to_previous(call: CallbackQuery, state: FSMContext):
    await asyncio.sleep(0.5)
    data = await state.get_data()
    last_message = data.get("last_message")
    await last_message.edit_text("Выбери дальнейшую опцию", reply_markup=option_user_choice())
    await state.set_state(NavigateStates.option_user_choice)


@user_router.message(F.text, NavigateStates.get_channel_name)
async def check_bot_rights(message: types.Message, state: FSMContext):
    await asyncio.sleep(0.5)
    data = await state.get_data()
    last_message = data.get("last_message")
    text = message.text
    logger.info(text)
    if "https://t.me/" in text:
        text = text.replace("https://t.me/", "@")
    if text[0] != "@":
        await asyncio.sleep(0.5)
        await message.answer("Пожалуйста, пришли тег канала в формате *@systemeelectric_official* 🔗",
                             parse_mode="Markdown")
        logger.warning(f"Invalid channel name: {text}")
        await state.set_state(NavigateStates.get_channel_name)
        return
    await last_message.edit_text(text=f"Канал для проверки: {text}", reply_markup=None)
    await asyncio.sleep(0.5)
    last_message = await message.answer("Какой период постов нужно проверить?",
                                        reply_markup=option_user_choose_time_interval())
    await state.update_data(channel_name=text, last_message=last_message)
    await state.set_state(NavigateStates.get_time_choice)


@user_router.callback_query(F.data == 'back', NavigateStates.get_time_choice)
async def back_to_previous(call: CallbackQuery, state: FSMContext):
    await asyncio.sleep(0.5)
    data = await state.get_data()
    last_message = data.get("last_message")
    await last_message.edit_text("Выбери дальнейшую опцию", reply_markup=option_user_choice())
    await state.set_state(NavigateStates.option_user_choice)


@user_router.callback_query(F.data == 'all_posts', NavigateStates.get_time_choice)
async def get_all_timestamp(call: CallbackQuery, state: FSMContext):
    await asyncio.sleep(0.5)
    data = await state.get_data()
    last_message = data.get("last_message")
    channel_name = data.get("channel_name")
    await last_message.edit_text(
        text=f"Ты выбрал анализ *всех постов* в канале. Он может занять *продолжительное время* ⏱️.",
        parse_mode="Markdown")
    await asyncio.sleep(0.5)
    ai_answer = await call.message.answer(
        "_Искусственный интеллект обрабатывает ваш запрос..._",
        parse_mode="Markdown")
    task_result_description = await get_channel_analysis(channel_name[1:], None, None, call.from_user.id)
    await ai_answer.delete()
    await asyncio.sleep(0.5)
    if not task_result_description.get("completion") and task_result_description.get("error") == "parsing":
        await call.message.answer("Пожалуйста, проверь не ошибся ли ты в теге или измени временной промежуток постов.")
    elif task_result_description.get("error") == "document_send":
        await call.message.answer("Пожалуйста, попробуйте позже, ошибка при отправке документа")
    last_message = await call.message.answer("Выбери дальнейшую опцию", reply_markup=option_user_choice())
    await state.update_data(last_message=last_message)
    await state.set_state(NavigateStates.option_user_choice)


@user_router.callback_query(F.data.in_({"week", "month", "year"}), NavigateStates.get_time_choice)
async def get_exact_timestamp(call: CallbackQuery, state: FSMContext):
    await asyncio.sleep(0.5)
    data = await state.get_data()
    last_message = data.get("last_message")
    channel_name = data.get("channel_name")
    end_time = datetime.now()
    dict_dates = {
        "week": {
            "date": (end_time - timedelta(weeks=1)).strftime("%d.%m.%Y"),
            "message": f"Ты выбрал анализ постов за *последнюю неделю*."},
        "month": {
            "date": (end_time - relativedelta(months=1)).strftime("%d.%m.%Y"),
            "message": f"Ты выбрал анализ постов за *последний месяц*.\n\nОн может занять *продолжительное время* ⏱️."},
        "year": {
            "date": (end_time - relativedelta(years=1)).strftime("%d.%m.%Y"),
            "message": f"Ты выбрал анализ постов за *последний год*.\n\nОн может занять *продолжительное время* ⏱️."}
    }
    await last_message.edit_text(text=dict_dates[call.data]["message"], parse_mode="Markdown")
    await asyncio.sleep(0.5)
    ai_answer = await call.message.answer(
        "_Искусственный интеллект обрабатывает ваш запрос..._",
        parse_mode="Markdown")
    task_result_description = await get_channel_analysis(channel_name[1:], dict_dates[call.data]["date"],
                                                         end_time.strftime("%d.%m.%Y"), call.from_user.id)
    await ai_answer.delete()
    await asyncio.sleep(0.5)
    if not task_result_description.get("completion") and task_result_description.get("error") == "parsing":
        await call.message.answer("Пожалуйста, проверь не ошибся ли ты в теге или измени временной промежуток постов.")
    elif task_result_description.get("error") == "document_send":
        await call.message.answer("Пожалуйста, попробуйте позже, ошибка при отправке документа")
    last_message = await call.message.answer("Выбери дальнейшую опцию", reply_markup=option_user_choice())
    await state.update_data(last_message=last_message)
    await state.set_state(NavigateStates.option_user_choice)


@user_router.callback_query(F.data == 'interval', NavigateStates.get_time_choice)
async def get_timestamps_interval(call: CallbackQuery, state: FSMContext):
    await asyncio.sleep(0.5)
    data = await state.get_data()
    last_message = data.get("last_message")
    await last_message.edit_text(
        text=f"Ты выбрал анализ постов *определенного временного промежутка*.\n\nПожалуйста, пришли мне *дату начала* и *дату конца интервала* в формате день.месяц.год .\n\n*Например:* 08.12.2025 26.12.2025",
        reply_markup=option_user_go_back(), parse_mode="Markdown")
    await state.set_state(NavigateStates.get_interval)


@user_router.callback_query(F.data == 'back', NavigateStates.get_interval)
async def back_to_previous(call: CallbackQuery, state: FSMContext):
    await asyncio.sleep(0.5)
    data = await state.get_data()
    last_message = data.get("last_message")
    await last_message.edit_text("Какой период постов нужно проверить?",
                                 reply_markup=option_user_choose_time_interval())
    await state.set_state(NavigateStates.get_time_choice)


@user_router.message(F.text, NavigateStates.get_interval)
async def get_interval(message: types.Message, state: FSMContext):
    await asyncio.sleep(0.5)
    data = await state.get_data()
    channel_name = data.get("channel_name")
    last_message = data.get("last_message")
    valid_dict = await validate_date_pair(message.text)
    if not valid_dict.get("valid"):
        await message.answer(valid_dict.get("message"))
        await state.set_state(NavigateStates.get_interval)
        return
    await asyncio.sleep(0.5)
    await last_message.edit_text(text=f"Твой выбранный промежуток: *{message.text}*", reply_markup=None,
                                 parse_mode="Markdown")
    dates = message.text.split()
    ai_answer = await message.answer(
        "_Искусственный интеллект обрабатывает ваш запрос, он может занять продолжительное время..._",
        parse_mode="Markdown")
    task_result_description = await get_channel_analysis(channel_name[1:], dates[0], dates[1], message.from_user.id)
    await ai_answer.delete()
    await asyncio.sleep(0.5)
    if not task_result_description.get("completion") and task_result_description.get("error") == "parsing":
        await message.answer("Пожалуйста, проверь не ошибся ли ты в теге или измени временной промежуток постов.")
    elif task_result_description.get("error") == "document_send":
        await message.answer("Пожалуйста, попробуйте позже, ошибка при отправке документа")
    last_message = await message.answer("Выбери дальнейшую опцию", reply_markup=option_user_choice())
    await state.update_data(last_message=last_message)
    await state.set_state(NavigateStates.option_user_choice)