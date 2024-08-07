import os
import logging
import asyncio
import re
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from telegram import Bot

# Путь к chromedriver
chrome_driver_path = 'C:\\Users\\Данила\\Desktop\\GPT\\2\\chrome driver\\chromedriver.exe'

# Настройки логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Настройки браузера
chrome_options = Options()
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--headless")  # Запуск в фоновом режиме

# Инициализация веб-драйвера
driver = webdriver.Chrome(service=Service(chrome_driver_path), options=chrome_options)

# Настройки бота Telegram
telegram_bot_token = '7213896068:AAGbXygK7S1Jv3fCwx6n7jGNaHDSH2SgxfQ'  # Ваш токен бота
channel_id = '@ImperialSochiRS'  # Ваш канал для отправки сообщений

# Создаем экземпляр бота
bot = Bot(token=telegram_bot_token)

# URL-адрес публичного канала Telegram
source_channel_url = "https://t.me/s/developer_sochi"

# Регулярные выражения для поиска имени и телефона
name_pattern = re.compile(r"Евгений|ДругиеИмена")  # Добавьте другие имена через |

# Регулярное выражение для различных форматов телефонных номеров
phone_pattern = re.compile(r"""
    (\+7|8)              # Код страны или префикс
    [\s\-\.]?            # Разделитель (пробел, дефис, точка)
    \(?\d{3}\)?          # Код региона в скобках или без них
    [\s\-\.]?            # Разделитель
    \d{3}                # Первая часть номера
    [\s\-\.]?            # Разделитель
    \d{2}                # Вторая часть номера
    [\s\-\.]?            # Разделитель
    \d{2}                # Третья часть номера
""", re.VERBOSE)

# Функция для закрытия всплывающего окна
def close_popup():
    try:
        logging.info("Проверка на наличие всплывающего окна...")
        popup_close_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Cancel') or contains(text(), 'Отмена')]"))
        )
        if popup_close_button:
            popup_close_button.click()
            logging.info("Всплывающее окно закрыто.")
        else:
            logging.info("Всплывающее окно отсутствует или уже закрыто.")
    except Exception as e:
        logging.info("Всплывающее окно отсутствует или уже закрыто.")

# Получение последних сообщений из канала
def get_latest_messages():
    logging.info("Переходим на страницу канала.")
    driver.get(source_channel_url)
    time.sleep(5)

    # Закрытие всплывающего окна, если оно появляется
    close_popup()

    try:
        # Убедитесь, что скрипт ждет загрузки сообщений
        logging.info("Ожидание загрузки сообщений...")
        time.sleep(5)

        # Найдите все сообщения на странице
        logging.info("Получаем последние сообщения из канала.")
        messages = WebDriverWait(driver, 20).until(
            EC.presence_of_all_elements_located((By.CLASS_NAME, 'tgme_widget_message_text'))
        )

        # Извлекаем URL медиа
        media_elements = WebDriverWait(driver, 20).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, '.tgme_widget_message_photo_wrap, .tgme_widget_message_video'))
        )

        latest_messages = [message.text for message in messages[-5:]]
        latest_media_urls = []
        for media in media_elements[-5:]:
            style = media.get_attribute('style')
            if 'url(' in style:
                url = style.split('url(')[-1].split(')')[0].strip("'\"")
                latest_media_urls.append(url)
            elif media.tag_name == 'video':
                video_url = media.get_attribute('src')
                latest_media_urls.append(video_url)

        # Замена имени и номера телефона в сообщениях
        updated_messages = [
            name_pattern.sub("Координатор Наталия", phone_pattern.sub("+79170467895", message))
            for message in latest_messages
        ]

        return updated_messages, latest_media_urls

    except Exception as e:
        logging.error(f"Ошибка при получении сообщений: {e}")
        return [], []

# Отправка сообщений и медиа в канал
async def send_messages_to_channel(messages, media_urls):
    for message, media_url in zip(messages, media_urls):
        try:
            # Отправляем сообщение с медиа
            if media_url:
                response = requests.get(media_url)
                if response.status_code == 200:
                    file_path = 'temp_media.jpg' if media_url.endswith(('jpg', 'jpeg', 'png')) else 'temp_media.mp4'
                    with open(file_path, 'wb') as f:
                        f.write(response.content)

                    if file_path.endswith('.jpg'):
                        # Отправка фото
                        await bot.send_photo(chat_id=channel_id, photo=open(file_path, 'rb'), caption=message)
                    else:
                        # Отправка видео
                        await bot.send_video(chat_id=channel_id, video=open(file_path, 'rb'), caption=message)

                    logging.info(f"Сообщение с медиа отправлено: {message}")
                    os.remove(file_path)
                else:
                    logging.warning(f"Не удалось скачать медиа: {media_url}")
            else:
                # Отправка только текста
                await bot.send_message(chat_id=channel_id, text=message)
                logging.info(f"Сообщение отправлено: {message}")

        except Exception as e:
            logging.error(f"Ошибка при отправке сообщения: {e}")

# Основная функция
async def main():
    try:
        latest_messages, latest_media_urls = get_latest_messages()
        if latest_messages:
            await send_messages_to_channel(latest_messages, latest_media_urls)
    finally:
        logging.info("Закрываем браузер.")
        driver.quit()

if __name__ == "__main__":
    asyncio.run(main())
