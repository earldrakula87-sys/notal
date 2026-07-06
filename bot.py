import asyncio
import logging
import aiohttp
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.enums import ChatAction
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from kerykeion import KrInstance, OutputTemplate
import cairosvg

import config
import database

logging.basicConfig(level=logging.INFO)

bot = Bot(token=config.TELEGRAM_TOKEN)
dp = Dispatcher()

class HoroscopeStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_year = State()
    waiting_for_month = State()
    waiting_for_day = State()
    waiting_for_hour = State()
    waiting_for_minute = State()
    waiting_for_city = State()

SYSTEM_PROMPT = {
    "role": "system",
    "content": (
        "Ты — Верховный Астролог, Эксперт по натальным картам и составитель точнейших звездных прогнозов. "
        "Пользователь прислал тебе точные математические расчеты планет своей натальной карты. Твоя задача — сделать "
        "глубокий, харизматичный, психологически поддерживающий и структурированный разбор. "
        "Опиши характер человека, его скрытый потенциал, сильные стороны, а также сферы карьеры и отношений на основе полученных градусов планет. "
        "Общайся мудро и авторитетно. Используй форматирование текста (жирный шрифт, списки), чтобы разбор выглядел профессионально."
    )
}

def get_main_menu():
    kb = [
        [types.KeyboardButton(text="🌌 Составить натальную карту")],
        [types.KeyboardButton(text="🔮 Задать вопрос Астрологу"), types.KeyboardButton(text="🧠 Сбросить память (/clear)")]
    ]
    return types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

async def ask_yandex_gpt(payload_messages: list) -> str:
    url = "https://yandex.net"
    headers = {
        "Authorization": f"Bearer {config.YANDEX_API_KEY}",
        "OpenAI-Project": config.YANDEX_FOLDER_ID,
        "Content-Type": "application/json"
    }
    payload = {
        "model": config.YANDEX_MODEL_URI,
        "messages": payload_messages,
        "temperature": 0.7,
        "max_tokens": 3000
    }
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, json=payload, headers=headers, timeout=40) as response:
                if response.status == 200:
                    result = await response.json()
                    return result["choices"]["message"]["content"]
                else:
                    error_text = await response.text()
                    logging.error(f"Ошибка Yandex API ({response.status}): {error_text}")
                    return f"Ошибка API Яндекс ({response.status}). Проверьте ключи в config.py."
        except Exception as e:
            logging.error(f"Исключение при запросе к Yandex API: {e}")
            return "Произошла ошибка соединения с сервером ИИ."

def generate_chart_data(name, year, month, day, hour, minute, city):
    user_chart = KrInstance(
        name=name, year=year, month=month, day=day, 
        hour=hour, minute=minute, city=city
    )
    output = OutputTemplate(user_chart)
    svg_data = output.xml_string
    png_path = f"chart_{name}.png"
    cairosvg.svg2png(bytestring=svg_data.encode('utf-8'), write_to=png_path)
    
    raw_data = "Расчеты натальной карты:\n"
    for planet in ["Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn"]:
        p_info = getattr(user_chart, planet.lower())
        raw_data += f"- {planet}: Знак {p_info.sign}, Дом {p_info.house}, Градус {p_info.position:.2f}\n"
    return png_path, raw_data

def clean_html_response(ai_response: str) -> str:
    html_response = ai_response
    is_bold_open = False
    while "**" in html_response:
        html_response = html_response.replace("**", "<b>", 1) if not is_bold_open else html_response.replace("**", "</b>", 1)
        is_bold_open = not is_bold_open
    if is_bold_open: html_response += "</b>"
    return html_response.replace("* ", "• ").replace("*", "")

@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    database.clear_context(message.from_user.id)
    await message.answer(
        "Приветствую тебя, путник! 🌌 Я твой персональный <b>Верховный Астролог</b> на базе ИИ.\n\n"
        "Используй меню ниже, чтобы составить точную карту звезд или задать мне прямой вопрос.",
        reply_markup=get_main_menu(),
        parse_mode="HTML"
    )

@dp.message(Command("clear"))
@dp.message(F.text == "🧠 Сбросить память (/clear)")
async def cmd_clear(message: types.Message, state: FSMContext):
    await state.clear()
    database.clear_context(message.from_user.id)
    await message.answer("Контекст общения успешно сброшен. Небосклон чист для новых расчетов! 🧠", reply_markup=get_main_menu())

@dp.message(F.text == "🌌 Составить натальную карту")
async def start_fsm(message: types.Message, state: FSMContext):
    await message.answer("Прекрасно. Давай заглянем в расположение звезд на момент твоих первых секунд жизни.\n\n✍️ <b>Как тебя зовут?</b>", parse_mode="HTML")
    await state.set_state(HoroscopeStates.waiting_for_name)

@dp.message(HoroscopeStates.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("📅 <b>В какой год ты родился?</b> (Например: 1995)", parse_mode="HTML")
    await state.set_state(HoroscopeStates.waiting_for_year)

@dp.message(HoroscopeStates.waiting_for_year)
async def process_year(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Пожалуйста, введи год числом (например: 1998)")
        return
    await state.update_data(year=int(message.text))
    await message.answer("🔢 <b>В какой месяц?</b> (Числом от 1 до 12)", parse_mode="HTML")
    await state.set_state(HoroscopeStates.waiting_for_month)

@dp.message(HoroscopeStates.waiting_for_month)
async def process_month(message: types.Message, state: FSMContext):
    if not message.text.isdigit() or not (1 <= int(message.text) <= 12):
        await message.answer("Введите корректный номер месяца (от 1 до 12)")
        return
    await state.update_data(month=int(message.text))
    await message.answer("📆 <b>Какого числа?</b> (День месяца числом)", parse_mode="HTML")
    await state.set_state(HoroscopeStates.waiting_for_day)

@dp.message(HoroscopeStates.waiting_for_day)
async def process_day(message: types.Message, state: FSMContext):
    if not message.text.isdigit() or not (1 <= int(message.text) <= 31):
        await message.answer("Введите корректный день месяца")
        return
    await state.update_data(day=int(message.text))
    await message.answer("⏰ <b>В какой час ты родился?</b> (По 24-часовой шкале, от 0 до 23)", parse_mode="HTML")
    await state.set_state(HoroscopeStates.waiting_for_hour)

@dp.message(HoroscopeStates.waiting_for_hour)
async def process_hour(message: types.Message, state: FSMContext):
    if not message.text.isdigit() or not (0 <= int(message.text) <= 23):
        await message.answer("Введите час от 0 до 23")
        return
    await state.update_data(hour=int(message.text))
    await message.answer("⏱ <b>В какие минуты?</b> (От 0 до 59)", parse_mode="HTML")
    await state.set_state(HoroscopeStates.waiting_for_minute)

@dp.message(HoroscopeStates.waiting_for_minute)
async def process_minute(message: types.Message, state: FSMContext):
    if not message.text.isdigit() or not (0 <= int(message.text) <= 59):
        await message.answer("Введите минуты от 0 до 59")
        return
    await state.update_data(minute=int(message.text))
    await message.answer("🌆 <b>В каком городе ты родился?</b> (Напиши название города на английском языке, например: <code>Moscow</code>, <code>London</code>)", parse_mode="HTML")
    await state.set_state(HoroscopeStates.waiting_for_city)

@dp.message(HoroscopeStates.waiting_for_city)
async def process_city(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    await state.update_data(city=message.text.strip())
    
    data = await state.get_data()
    await state.clear()
    
    try:
        await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
        await message.answer("✨ Данные приняты. Запускаю вычисление положения планет по швейцарским эфемеридам... Отрисовываю карту.")
        
        png_file, planet_data_text = generate_chart_data(
            data['name'], data['year'], data['month'], data['day'], 
            data['hour'], data['minute'], data['city']
        )
        
        photo = types.FSInputFile(png_file)
        await bot.send_photo(chat_id=message.chat.id, photo=photo, caption="🌌 Ваша астрологическая натальная карта готова. Начинаю расшифровку ИИ...")
        
        if os.path.exists(png_file):
            os.remove(png_file)

        user_history = database.get_context(user_id)
        user_history.append({
            "role": "user",
            "content": f"Сделай разбор моей карты по этим точным градусам:\n{planet_data_text}"
        })
        
        ai_response = await ask_yandex_gpt([SYSTEM_PROMPT] + user_history)
        
        if "Ошибка" not in ai_response:
            user_history.append({"role": "assistant", "content": ai_response})
            database.save_context(user_id, SYSTEM_PROMPT, user_history)
            
        await message.answer(clean_html_response(ai_response), parse_mode="HTML", reply_markup=get_main_menu())
        
    except Exception as err:
        logging.error(f"Ошибка вычисления карты: {err}")
        await message.answer("❌ Произошла ошибка. Проверьте правильность написания города на английском.", reply_markup=get_main_menu())

@dp.message(F.text == "🔮 Задать вопрос Астрологу")
async def ask_free_question(message: types.Message):
    await message.answer("Спрашивай меня о чём угодно. Звёзды укажут верный путь. (Просто отправь свой текстовый вопрос в чат)")

@dp.message()
async def handle_message(message: types.Message):
    if not message.text:
        return
    user_id = message.from_user.id

    try:
        await bot.send_chat_action(chat_id=message.chat.id, action=ChatAction.TYPING)
        user_history = database.get_context(user_id)
        user_history.append({"role": "user", "content": message.text})
        
        ai_response = await ask_yandex_gpt([SYSTEM_PROMPT] + user_history)

        if "Ошибка" not in ai_response:
            user_history.append({"role": "assistant", "content": ai_response})
            database.save_context(user_id, SYSTEM_PROMPT, user_history)

        await message.answer(clean_html_response(ai_response), parse_mode="HTML", reply_markup=get_main_menu())

    except Exception as main_error:
        logging.error(f"Ошибка в handle_message: {main_error}")
        await message.answer("Внутренняя ошибка бота.")

async def main():
    database.init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
