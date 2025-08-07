import logging
import requests
import json
import os
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import aiohttp
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)
from telethon import TelegramClient, events
from telethon.tl.types import Message

# Конфигурация
API_ID = 21695610  # Получить с my.telegram.org
API_HASH = '1f3ccb2d1d14afc4bacd38133583356a'  # Получить с my.telegram.org
BOT_TOKEN = '7856559014:AAHY8ivsZvOOYA56n98GVHrQy3altzzFv9M'  # Получить от @BotFather
API_KEY = "sk-f6501722e1fb48f695782c0219e4d74f"

# Хранилище данных (в реальном проекте лучше использовать БД)
sub_file = open("sub.txt", "r")
prompt_file = open("prompt.txt", "r")
SUBSCRIPTIONS = sub_file.read().split("\n")
if len(SUBSCRIPTIONS) == 1 and SUBSCRIPTIONS[0] == '':
    SUBSCRIPTIONS = []
PROMPT = prompt_file.read()
sub_file.close()
prompt_file.close()
ACTIVE_CLIENTS: Dict[int, TelegramClient] = {}

# Настройка логгирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def deepseek_api_call(prompt):
    API_URL = "https://api.deepseek.com/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }

    data = {
        "model": "deepseek-chat",  # Уточните актуальное название модели
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,  # Параметр креативности (0-1)
    }

    response = requests.post(API_URL, headers=headers, json=data)
    if response.status_code == 200:
        return response.json()["choices"][0]["message"]["content"]
    else:
        print("Ошибка запроса:", response.status_code)
        print(response.text)  # Вывод ошибки, если что-то пошло не так
        return ""


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start"""
    user_id = update.effective_user.id

    keyboard = [
        [InlineKeyboardButton("Мои подписки", callback_data='list_subscriptions')],
        [InlineKeyboardButton("Добавить канал", callback_data='add_channel')],
        [InlineKeyboardButton("Удалить канал", callback_data='remove_channel')],
        [InlineKeyboardButton("Изменить промпт", callback_data='change_prompt')],
        [InlineKeyboardButton("Получить сводку", callback_data='get_summary')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Выберите действие:",
        reply_markup=reply_markup
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик нажатий кнопок"""
    query = update.callback_query
    await query.answer()


    if query.data == 'list_subscriptions':
        await list_subscriptions(query)
    elif query.data == 'add_channel':
        await query.edit_message_text(
            "Отправьте ссылку на канал или его username (например, @durov или https://t.me/durov):"
        )
        context.user_data['action'] = 'add_channel'
    elif query.data == 'remove_channel':
        await list_subscriptions_for_removal(query)
    elif query.data == 'change_prompt':
        await query.edit_message_text(
            f"Текущий промпт:\n{PROMPT}\n\n"
            "Отправьте новый промпт для нейросети:"
        )
        context.user_data['action'] = 'change_prompt'
    elif query.data == 'get_summary':
        await get_summary(query, context)
    elif query.data.startswith('remove_'):
        channel = query.data[7:]
        await remove_channel(query, channel)


async def list_subscriptions(query) -> None:
    """Показать список подписок"""
    if 0 == len(SUBSCRIPTIONS):
        await query.edit_message_text("У вас пока нет подписок на каналы.")
        return

    subscriptions_list = "\n".join(SUBSCRIPTIONS)
    await query.edit_message_text(f"Ваши подписки:\n{subscriptions_list}")


async def list_subscriptions_for_removal(query) -> None:
    """Показать список подписок для удаления"""
    user_id = query.from_user.id
    if 0 == len(SUBSCRIPTIONS):
        await query.edit_message_text("У вас пока нет подписок на каналы.")
        return

    keyboard = [
        [InlineKeyboardButton(channel, callback_data=f'remove_{channel}')]
        for channel in SUBSCRIPTIONS
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "Выберите канал для удаления:",
        reply_markup=reply_markup
    )


async def remove_channel(query, channel: str) -> None:
    """Удалить канал из подписок"""
    if channel in SUBSCRIPTIONS:
        SUBSCRIPTIONS.remove(channel)
        sub_file1 = open("sub.txt", "w")
        sub_file1.write("\n".join(SUBSCRIPTIONS))

        await query.edit_message_text(f"Канал {channel} удален из ваших подписок.")
    else:
        await query.edit_message_text("Этот канал не найден в ваших подписках.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик текстовых сообщений"""

    action = context.user_data.get('action')
    text = update.message.text

    if action == 'add_channel':
        # Нормализация ссылки на канал
        if text.startswith('https://t.me/'):
            channel = text.split('https://t.me/')[-1].split('/')[0]
        elif text.startswith('@'):
            channel = text[1:]
        else:
            channel = text

        if channel not in SUBSCRIPTIONS:
            SUBSCRIPTIONS.append(channel)
            sub_file1 = open("sub.txt", "w")
            sub_file1.write("\n".join(SUBSCRIPTIONS))
            await update.message.reply_text(f"Канал {channel} добавлен в ваши подписки.")
        else:
            await update.message.reply_text("Этот канал уже есть в ваших подписках.")

        context.user_data.pop('action', None)
        await start(update, context)

    elif action == 'change_prompt':
        prompt_file1 = open("prompt.txt", "w")
        prompt_file1.write(text)
        await update.message.reply_text("Промпт успешно обновлен!")
        context.user_data.pop('action', None)
        await start(update, context)


async def get_summary(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Получить сводку по подпискам"""
    user_id = query.from_user.id
    await query.edit_message_text("Начинаю сбор и анализ сообщений...")

    if not SUBSCRIPTIONS:
        await query.edit_message_text("У вас нет подписок на каналы.")
        return

    # Получаем дату 24 часа назад
    time_24h_ago = datetime.now(pytz.utc) - timedelta(hours=24)
    try:
        # Создаем или используем существующий Telethon клиент
        if user_id not in ACTIVE_CLIENTS:
            session_name = f"user_{user_id}"
            client = TelegramClient(session_name, API_ID, API_HASH, device_model="iphone 1337 pro max", system_version="228.337", app_version="1.0.0.0.0.0.1.179")
            await client.start()
            ACTIVE_CLIENTS[user_id] = client
        else:
            client = ACTIVE_CLIENTS[user_id]

        messages_to_analyze = []

        for channel in SUBSCRIPTIONS:
            try:
                # Получаем сущность канала
                entity = await client.get_entity(channel)

                # Собираем сообщения за последние 24 часа
                async for message in client.iter_messages(
                        entity,
                        limit=20,
                        offset_date=time_24h_ago
                ):
                    if isinstance(message, Message) and message.text:
                        messages_to_analyze.append({
                            'channel': channel,
                            'text': message.text,
                            'date': message.date
                        })
            except Exception as e:
                logger.error(f"Ошибка при получении сообщений из канала {channel}: {e}")
                continue

        if not messages_to_analyze:
            await query.edit_message_text("Нет новых сообщений в подписанных каналах за последние 24 часа.")
            return

        # Формируем текст для анализа
        messages_text = "\n\n".join(
            f"Канал: {msg['channel']}\n"
            f"Дата: {msg['date']}\n"
            f"Текст: {msg['text']}\n"
            for msg in messages_to_analyze
        )

        # Анализируем с помощью DeepSeek
        full_prompt = f"{PROMPT}\n\n{messages_text}"

        try:
            # Здесь замените вызов OpenAI на вызов DeepSeek
            response = await deepseek_api_call(full_prompt)  # Предполагается, что у вас есть функция deepseek_api_call

            summary = response

            await query.message.reply_text(f"📌 Сводка за последние 24 часа:\n\n")
            length = len(summary)
            ind = 0
            while ind < length:
                i = 0
                s = ''
                while i < 4000 and ind < length:
                    s += summary[ind]
                    i += 1
                    ind += 1
                await query.message.reply_text(s)
            await query.message.reply_text(
                f"Проанализировано {len(messages_to_analyze)} сообщений из {len(SUBSCRIPTIONS)} каналов.")
        except Exception as e:
            logger.error(f"Ошибка при обращении к DeepSeek: {e}")
            await query.message.reply_text("Произошла ошибка при анализе сообщений.")
    except Exception as e:
        logger.error(f"Общая ошибка: {e}")
        await query.message.reply_text("Произошла ошибка при получении сводки.")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик ошибок"""
    logger.error(f"Ошибка: {context.error}")


def main() -> None:
    """Запуск бота"""
    if not all([API_ID, API_HASH, BOT_TOKEN, API_KEY]):
        raise ValueError("Не все необходимые переменные окружения установлены!")

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)

    application.run_polling()


if __name__ == "__main__":
    main()
