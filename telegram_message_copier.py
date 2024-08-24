import os
import sys
import asyncio
import logging
import signal
import json
import httpx
import re
import time
from contextlib import asynccontextmanager
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from telegram import Bot

# Проверка на существующий файл-замок
lock_file = "script.lock"

if os.path.exists(lock_file):
    print("Another instance of the script is already running. Exiting.")
    sys.exit()

# Создание файла-замка
with open(lock_file, 'w') as lock:
    lock.write(str(os.getpid()))

# Загрузка конфигурации из файла config.json
with open("config.json", "r", encoding="utf-8") as config_file:
    config = json.load(config_file)

logging.basicConfig(level=logging.INFO)

# Функция загрузки имен из JSON-файла
def load_names_from_json(filename):
    with open(filename, 'r', encoding='utf-8') as file:
        data = json.load(file)
        return data.get("names", [])

# Загружаем имена из словаря
names_list = load_names_from_json(config["names_dictionary_file"])
name_pattern = "|".join(names_list)  # Создаем регулярное выражение для поиска имен

# Настройка WebDriver
options = Options()
options.add_argument("--headless")
options.add_argument("--disable-gpu")

service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=options)

# Функция для отправки контрольной фразы при старте
async def send_start_message():
    bot = Bot(token=config['telegram_bot_token'])
    await bot.send_message(chat_id=config['channel_id'], text="IMPERIAL RS")
    logging.info("Отправлена контрольная фраза: IMPERIAL RS")

# Функция для отправки контрольной фразы при завершении
async def send_end_message():
    bot = Bot(token=config['telegram_bot_token'])
    await bot.send_message(chat_id=config['channel_id'], text="👋")
    logging.info("Отправлена контрольная фраза при завершении работы: 👋")

@asynccontextmanager
async def graceful_shutdown():
    loop = asyncio.get_event_loop()

    def _cancel_tasks():
        logging.info("Получен сигнал отмены. Завершаем задачи...")
        for task in asyncio.all_tasks(loop):
            task.cancel()

    try:
        signal.signal(signal.SIGINT, lambda sig, frame: _cancel_tasks())
        signal.signal(signal.SIGTERM, lambda sig, frame: _cancel_tasks())
        yield
    except asyncio.CancelledError:
        logging.info("Задачи отменены.")
    finally:
        await send_end_message()
        logging.info("Завершение работы завершено.")
        await asyncio.sleep(2)  # Задержка для отправки смайлика перед завершением

# Время начала выполнения скрипта
start_time = time.time()

# Максимальное время работы скрипта в секундах (5 минут)
max_run_time = 5 * 60

# Функция завершения работы
async def shutdown(loop):
    logging.info("Начало процесса завершения работы...")
    try:
        await send_end_message()
    except Exception as e:
        logging.error(f"Ошибка при отправке контрольного сообщения: {e}")
    finally:
        driver.quit()
        logging.info("WebDriver закрыт.")
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        logging.info("Все задачи завершены.")
        loop.stop()
        logging.info("Цикл событий остановлен.")

# Функция для чтения последнего отправленного сообщения из файла
def read_last_message():
    if os.path.exists(config['last_message_file']):
        with open(config['last_message_file'], 'r', encoding='utf-8') as file:
            return file.read().strip()
    return None

# Функция для записи последнего отправленного сообщения в файл
def write_last_message(message):
    with open(config['last_message_file'], 'w', encoding='utf-8') as file:
        file.write(message)

# Функция для получения последнего сообщения
def get_latest_message():
    driver.get(config['source_channel_url'])
    logging.info("Открываем страницу канала.")
    time.sleep(10)  # Ожидание полной загрузки страницы
    logging.info("Ожидание полной загрузки страницы...")

    body = driver.find_element(By.TAG_NAME, 'body')
    body.send_keys(Keys.PAGE_DOWN)
    time.sleep(2)

    message_block = driver.find_elements(By.CSS_SELECTOR, ".tgme_widget_message_wrap")[-1]  # Последнее сообщение
    logging.info(f"Найдено последнее сообщение.")

    try:
        text = message_block.find_element(By.CSS_SELECTOR, ".tgme_widget_message_text").text

        # Замена номеров телефонов
        for pattern in config["phone_patterns"]:
            text = re.sub(pattern, config["phone_replacement"], text)

        # Замена имен
        text = re.sub(name_pattern, config["name_replacement"], text)
        
        media_url = None
        media_type = None
        try:
            media_element = message_block.find_element(By.CSS_SELECTOR, ".tgme_widget_message_photo_wrap")
            media_url = media_element.get_attribute("style").split('url(\"')[1].split('\")')[0]
            media_type = 'photo'
        except Exception:
            try:
                media_element = message_block.find_element(By.CSS_SELECTOR, "video")
                media_url = media_element.get_attribute("src")
                media_type = 'video'
                # Дополнительное логирование атрибутов видео
                video_width = media_element.get_attribute("width")
                video_height = media_element.get_attribute("height")
                logging.info(f"Обнаружено видео: {media_url}, Ширина: {video_width}, Высота: {video_height}")
            except Exception as e:
                logging.warning(f"Не удалось найти медиа для сообщения: {e}")

        logging.info(f"Сообщение: {text}")
        if media_url:
            logging.info(f"Медиа URL: {media_url}")
        
        return text, media_url, media_type

    except Exception as e:
        logging.error(f"Ошибка при извлечении последнего сообщения: {e}")
        return None, None, None

# Функция для загрузки видеофайла перед отправкой
async def download_video(url):
    async with httpx.AsyncClient(timeout=config['timeout']) as client:
        response = await client.get(url)
        with open(config['temp_video_file'], 'wb') as video_file:
            video_file.write(response.content)
        logging.info(f"Видео загружено: {config['temp_video_file']}")

# Функция для отправки сообщения в Telegram канал с логикой повторной отправки
async def send_message_to_channel(message, media_url, media_type):
    bot = Bot(token=config['telegram_bot_token'])
    
    retries = 0
    while retries < config["max_retries"]:
        try:
            if media_type == 'photo':
                await bot.send_photo(chat_id=config['channel_id'], photo=media_url, caption=message)
            elif media_type == 'video':
                await download_video(media_url)
                with open(config['temp_video_file'], 'rb') as video_file:
                    await bot.send_video(chat_id=config['channel_id'], video=video_file, caption=message)
                os.remove(config['temp_video_file'])
            else:
                await bot.send_message(chat_id=config['channel_id'], text=message)
            logging.info(f"Сообщение отправлено: {message}")
            write_last_message(message)
            break
        except Exception as e:
            retries += 1
            logging.error(f"Ошибка при отправке сообщения, попытка {retries}: {e}")
            if retries >= config["max_retries"]:
                logging.error(f"Все попытки отправки сообщения не удались")

async def main():
    await send_start_message()
    last_sent_message = read_last_message()

    try:
        async with graceful_shutdown():
            while True:
                # Проверяем, прошло ли максимальное время работы скрипта
                if time.time() - start_time > max_run_time:
                    logging.info("Превышено максимальное время выполнения. Завершаем работу.")
                    break

                latest_message, latest_media_url, latest_media_type = get_latest_message()
                if latest_message and latest_message != last_sent_message:
                    await send_message_to_channel(latest_message, latest_media_url, latest_media_type)
                    last_sent_message = latest_message
                await asyncio.sleep(config['check_interval'])
    except asyncio.CancelledError:
        logging.info("Основной цикл прерван.")
    except Exception as e:
        logging.error(f"Неожиданная ошибка в основном цикле: {e}")
    finally:
        # Удаление файла-замка при завершении
        os.remove(lock_file)

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        logging.info("Получено прерывание с клавиатуры.")
    finally:
        try:
            loop.run_until_complete(shutdown(loop))
        except RuntimeError:
            logging.info("Цикл событий уже остановлен.")
        finally:
            loop.close()
            logging.info("Скрипт успешно завершен.")
