from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# Клавиатуры бота
def option_user_choice():
    keyboard_list = [
        [InlineKeyboardButton(text='Проверить сообщение 💬', callback_data='message_check')],
        [InlineKeyboardButton(text='Проверить канал 🗂', callback_data='channel_check')]
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_list)
    return keyboard


def option_user_go_back():
    keyboard_list = [
        [InlineKeyboardButton(text='Вернуться назад ↩️', callback_data='back')]
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_list)
    return keyboard


def option_user_choose_time_interval():
    keyboard_list = [
        [InlineKeyboardButton(text='Все посты в канале 📂', callback_data='all_posts')],
        [InlineKeyboardButton(text='Указать период вручную 📅', callback_data='interval')],
        [InlineKeyboardButton(text='За последние 7 дней 🗓', callback_data='week')],
        [InlineKeyboardButton(text='За последний месяц 🗓', callback_data='month')],
        [InlineKeyboardButton(text='За последний год 🗓', callback_data='year')],
        [InlineKeyboardButton(text='Вернуться назад ↩️', callback_data='back')]
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_list)
    return keyboard