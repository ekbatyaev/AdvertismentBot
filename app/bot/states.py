from aiogram.filters.state import State, StatesGroup

# FSM состояние бота
class NavigateStates(StatesGroup):
    option_user_choice = State()
    get_time_choice = State()
    get_interval = State()
    get_channel_name = State()


class AnalyzeStates(StatesGroup):
    message_analyze = State()
    channel_analyze = State()
    get_analysis_results = State()