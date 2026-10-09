from maxapi.types import CallbackButton
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder

# Клавиатуры бота
def option_user_choice():
    keyboard_builder = InlineKeyboardBuilder()
    keyboard_builder.row(CallbackButton(text = 'Проверить сообщение 💬', payload = 'message_check'))
    keyboard_builder.row(CallbackButton(text = 'Проверить телеграмм канал 🗂', payload = 'channel_check'))
    return keyboard_builder.as_markup()


def option_user_go_back():
    keyboard_builder = InlineKeyboardBuilder()
    keyboard_builder.row(CallbackButton(text='Вернуться назад ↩️', payload='back'))
    return keyboard_builder.as_markup()


def option_user_choose_time_interval():
    keyboard_builder = InlineKeyboardBuilder()
    keyboard_builder.row(CallbackButton(text='Все посты в канале 📂', payload = 'all_posts'))
    keyboard_builder.row(CallbackButton(text='Указать период вручную 📅', payload = 'interval'))
    keyboard_builder.row(CallbackButton(text='За последние 7 дней 🗓', payload = 'week'))
    keyboard_builder.row(CallbackButton(text='За последний месяц 🗓', payload = 'month'))
    keyboard_builder.row(CallbackButton(text='За последний год 🗓', payload = 'year'))
    keyboard_builder.row(CallbackButton(text='Вернуться назад ↩️', payload = 'back'))
    return keyboard_builder.as_markup()