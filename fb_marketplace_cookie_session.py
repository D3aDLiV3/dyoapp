import time
import json
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import shutil

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
COOKIES_FILE = "cookies.json"  # Debes guardar tus cookies aquí
PROFILE_URL = "https://www.facebook.com/marketplace/profile/61578198642564"  # Cambia por tu URL

# --- Configuración de Chrome headless para servidor Linux ---
def get_chrome_driver():
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument(f'user-agent={USER_AGENT}')
    chromium_path = shutil.which('chromium-browser') or shutil.which('chromium')
    chrome_path = shutil.which('google-chrome')
    if chromium_path:
        chrome_options.binary_location = chromium_path
    elif chrome_path:
        chrome_options.binary_location = chrome_path
    else:
        raise RuntimeError('No se encontró Chromium ni Google Chrome en el sistema. Instala uno con apt.')
    driver = webdriver.Chrome(options=chrome_options)
    return driver

# --- Cargar cookies desde archivo ---
def load_cookies(driver, cookies_path):
    with open(cookies_path, 'r') as f:
        cookies = json.load(f)
    driver.get("https://www.facebook.com/")
    time.sleep(2)
    for cookie in cookies:
        # Selenium espera 'expiry' en vez de 'expirationDate'
        if 'expirationDate' in cookie:
            cookie['expiry'] = int(cookie['expirationDate'])
            del cookie['expirationDate']
        # Elimina campos no válidos
        for k in ['storeId', 'hostOnly', 'sameSite', 'session']:
            cookie.pop(k, None)
        try:
            driver.add_cookie(cookie)
        except Exception as e:
            print(f"No se pudo agregar cookie {cookie.get('name')}: {e}")
    driver.refresh()
    time.sleep(2)

# --- Detección de login y alerta ---
def is_login_page(driver):
    return (
        'login' in driver.current_url or
        'Log in to Facebook' in driver.title or
        driver.find_elements(By.NAME, 'login')
    )

def main():
    driver = get_chrome_driver()
    load_cookies(driver, COOKIES_FILE)
    driver.get(PROFILE_URL)
    time.sleep(5)
    if is_login_page(driver):
        print("¡ALERTA! Facebook pide login. Las cookies caducaron o son inválidas.")
        driver.save_screenshot('error.png')
        driver.quit()
        return
    else:
        print("Sesión iniciada correctamente. Scrapeando productos...")
        driver.save_screenshot('marketplace_ok.png')

    # --- SCRAPING DE PRODUCTOS ---
    # Scroll para cargar productos
    last_height = driver.execute_script("return document.body.scrollHeight")
    for _ in range(10):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height
    products = []
    items = driver.find_elements(By.XPATH, '//div[contains(@aria-label, "Marketplace Listing")]')
    for item in items:
        try:
            title = item.find_element(By.XPATH, './/span[contains(@dir, "auto")]').text
            price = item.find_element(By.XPATH, './/span[contains(text(), "$") or contains(text(), "₡") or contains(text(), "€") or contains(text(), "₲") or contains(text(), "₱") or contains(text(), "₦") or contains(text(), "R$") or contains(text(), "S/") or contains(text(), "Q") or contains(text(), "RD$") or contains(text(), "Bs.") or contains(text(), "L") or contains(text(), "C$") or contains(text(), "₡") or contains(text(), "₲") or contains(text(), "₱") or contains(text(), "₦") or contains(text(), "R$") or contains(text(), "S/") or contains(text(), "Q") or contains(text(), "RD$") or contains(text(), "Bs.") or contains(text(), "L") or contains(text(), "C$")]').text
            products.append({'title': title, 'price': price})
        except Exception:
            continue
    print(f"Productos extraídos: {len(products)}")
    for p in products:
        print(p)
    driver.quit()

if __name__ == "__main__":
    main()
