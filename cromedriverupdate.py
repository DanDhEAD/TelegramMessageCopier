from selenium import webdriver
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options

# Создаем объект Options
options = Options()

# Устанавливаем ChromeDriver и создаем WebDriver
service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=options)

# Ваш код для работы с WebDriver здесь

driver.quit()  # Закрываем браузер
