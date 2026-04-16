

import time
import json
import shutil
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
COOKIES_FILE = "cookies.json"
PROFILE_URL = "https://www.facebook.com/marketplace/profile/61578198642564"  # URL fijo del perfil a auditar

class FacebookMarketplaceScraper:
    def __init__(self, headless=True, driver_path=None):
        chrome_options = Options()
        if headless:
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
        self.driver = webdriver.Chrome(executable_path=driver_path, options=chrome_options) if driver_path else webdriver.Chrome(options=chrome_options)
        self._load_cookies(COOKIES_FILE)

    def _load_cookies(self, cookies_path):
        self.driver.get("https://www.facebook.com/")
        time.sleep(2)
        with open(cookies_path, 'r') as f:
            cookies = json.load(f)
        for cookie in cookies:
            if 'expirationDate' in cookie:
                cookie['expiry'] = int(cookie['expirationDate'])
                del cookie['expirationDate']
            for k in ['storeId', 'hostOnly', 'sameSite', 'session']:
                cookie.pop(k, None)
            try:
                self.driver.add_cookie(cookie)
            except Exception as e:
                print(f"No se pudo agregar cookie {cookie.get('name')}: {e}")
        self.driver.refresh()
        time.sleep(2)

    def scrape_products(self):
        self.driver.get(PROFILE_URL)
        time.sleep(3)
        # Detección de login/bloqueo
        if (
            'login' in self.driver.current_url or
            'Log in to Facebook' in self.driver.title or
            self.driver.find_elements(By.NAME, 'login')
        ):
            print("¡ALERTA! Facebook pide login. Las cookies caducaron o son inválidas.")
            self.driver.save_screenshot('error.png')
            return []
        # Scroll para cargar productos (más scrolls y espera)
        last_height = self.driver.execute_script("return document.body.scrollHeight")
        for _ in range(25):  # Máximo 25 scrolls
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2.5)
            new_height = self.driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height
        # Guardar screenshot y HTML para depuración después del scroll
        self.driver.save_screenshot('debug_fb.png')
        with open('debug_fb.html', 'w', encoding='utf-8') as f:
            f.write(self.driver.page_source)
        products = []
        items = self.driver.find_elements(By.XPATH, '//div[contains(@aria-label, "Marketplace Listing")]')
        print(f"DEBUG: Se detectaron {len(items)} items tras el scroll.")
        for item in items:
            try:
                title = item.find_element(By.XPATH, './/span[contains(@dir, "auto")]').text
                price = item.find_element(By.XPATH, './/span[contains(text(), "$") or contains(text(), "₡") or contains(text(), "€") or contains(text(), "₲") or contains(text(), "₱") or contains(text(), "₦") or contains(text(), "R$") or contains(text(), "S/") or contains(text(), "Q") or contains(text(), "RD$") or contains(text(), "Bs.") or contains(text(), "L") or contains(text(), "C$") or contains(text(), "₡") or contains(text(), "₲") or contains(text(), "₱") or contains(text(), "₦") or contains(text(), "R$") or contains(text(), "S/") or contains(text(), "Q") or contains(text(), "RD$") or contains(text(), "Bs.") or contains(text(), "L") or contains(text(), "C$")]').text
                products.append({'title': title, 'price': price})
            except Exception:
                continue
        return products

    def close(self):
        self.driver.quit()

    if __name__ == "__main__":
        # Configuración principal para scraping robusto
        PROFILE_URL = "https://www.facebook.com/marketplace/your-profile-url"  # Cambia por tu URL
        COOKIES_PATH = "cookies.json"
        USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"

        scraper = FacebookMarketplaceScraper(
            profile_url=PROFILE_URL,
            cookies_path=COOKIES_PATH,
            user_agent=USER_AGENT,
            headless=True
        )
        productos = scraper.scrape_products()
        print(f"Productos encontrados: {len(productos)}")
        for p in productos:
            print(p)
        scraper.close()
