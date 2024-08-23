import asyncio
import logging
import time
import re
import os
import httpx
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from telegram import Bot
import signal
import sys

# Настройки
config = {
    "chrome_driver_path": "C:\\Users\\Данила\\Desktop\\GPT\\2\\chrome driver\\chromedriver.exe",
    "telegram_bot_token": "7213896068:AAGbXygK7S1Jv3fCwx6n7jGNaHDSH2SgxfQ",
    "channel_id": "@ImperialSochiRS",
    "source_channel_url": "https://t.me/s/developer_sochi",
    "phone_replacement": "+79170467895",
    "name_replacement": "Координатор Наталия",
    "name_pattern": "Артур|Евгений|Иван|Александр|ДругиеИмена",
    "temp_video_file": "temp_video.mp4",  # Временный файл для загрузки видео
    "max_retries": 3,  # Количество попыток повторной отправки
    "timeout": 60,  # Время ожидания для запросов (в секундах)
    "check_interval": 60,  # Интервал между проверками новых сообщений (в секундах)
    "last_message_file": "last_message.txt"  # Файл для хранения последнего сообщения
}

logging.basicConfig(level=logging.INFO)

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

# Обработка сигналов завершения работы (например, Ctrl+C)
def signal_handler(sig, frame):
    loop = asyncio.get_event_loop()
    logging.info(f"Получен сигнал {sig}. Немедленное завершение.")
    asyncio.ensure_future(shutdown(loop))

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

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
        text = re.sub(r"\b(\+7|8)?[\s\-\.]?\(?\d{3}\)?[\s\-\.]?\d{3}[\s\-\.]?\d{2}[\s\-\.]?\d{2}\b", config["phone_replacement"], text)
        text = re.sub(config["name_pattern"], config["name_replacement"], text)
        
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
            write_last_message(message)  # Сохранение последнего отправленного сообщения
            break  # Если отправка прошла успешно, выйти из цикла повторной отправки
        except Exception as e:
            retries += 1
            logging.error(f"Ошибка при отправке сообщения, попытка {retries}: {e}")
            if retries >= config["max_retries"]:
                logging.error(f"Все попытки отправки сообщения не удались")

# Основная функция
async def main():
    await send_start_message()
    last_sent_message = read_last_message()

    try:
        while True:
            latest_message, latest_media_url, latest_media_type = get_latest_message()
            
            if latest_message and latest_message != last_sent_message:
                await send_message_to_channel(latest_message, latest_media_url, latest_media_type)
                last_sent_message = latest_message

            await asyncio.sleep(config['check_interval'])
    except asyncio.CancelledError:
        logging.info("Основной цикл прерван.")
    except Exception as e:
        logging.error(f"Неожиданная ошибка в основном цикле: {e}")

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
