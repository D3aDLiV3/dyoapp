

import time
import json
import re
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
        # Facebook usa virtual scrolling: solo ~25 productos están en el DOM
        # a la vez. Hay que recolectar productos DURANTE el scroll.
        seen = {}  # listing_id -> {'title': ..., 'price': ...}
        max_scrolls = 80
        stale_attempts = 0
        max_stale = 8  # más tolerancia porque FB puede tardar en cargar

        def _collect_visible():
            """Recolecta productos visibles en el DOM actual al dict seen."""
            items = self.driver.find_elements(By.XPATH, '//a[contains(@href, "/marketplace/item/")]')
            for item in items:
                try:
                    href = item.get_attribute('href') or ''
                    label = item.get_attribute('aria-label')
                    if not label or not href:
                        continue
                    lm = re.search(r'/marketplace/item/(\d+)', href)
                    if not lm:
                        continue
                    lid = lm.group(1)
                    if lid in seen:
                        continue
                    lc = label.replace('\xa0', ' ')
                    m = re.match(r'^(.*?),\s*\$\s*([\d.,]+),\s*(.*?),\s*listing\s+\d+$', lc)
                    if m:
                        t, p = m.group(1).strip(), '$ ' + m.group(2).strip()
                    else:
                        m2 = re.match(r'^(.*?),\s*COP\s*([\d.,]+),\s*(.*?),\s*listing\s+\d+$', lc)
                        if m2:
                            t, p = m2.group(1).strip(), 'COP ' + m2.group(2).strip()
                        else:
                            continue
                    if t:
                        seen[lid] = {'title': t, 'price': p}
                except Exception:
                    continue

        for i in range(max_scrolls):
            _collect_visible()
            prev_total = len(seen)
            # Scroll hacia abajo
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            # Cada 3 scrolls, subir un poco y volver a bajar (trigger lazy load)
            if i % 3 == 2:
                self.driver.execute_script("window.scrollBy(0, -600);")
                time.sleep(0.5)
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1.5)
            _collect_visible()
            new_total = len(seen)
            if new_total > prev_total:
                stale_attempts = 0
                print(f"DEBUG scroll {i+1}: {new_total} productos acumulados (+{new_total - prev_total})")
            else:
                stale_attempts += 1
                if stale_attempts >= max_stale:
                    print(f"DEBUG scroll {i+1}: Sin nuevos productos tras {max_stale} scrolls. Total: {new_total}")
                    break
        print(f"DEBUG: Scroll finalizado. Total productos recolectados: {len(seen)}")
        # Guardar screenshot y HTML para depuración
        self.driver.save_screenshot('debug_fb.png')
        with open('debug_fb.html', 'w', encoding='utf-8') as f:
            f.write(self.driver.page_source)
        products = list(seen.values())
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
