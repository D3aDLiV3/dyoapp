

import time
import json
import re
import shutil
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
COOKIES_FILE = "cookies.json"
PROFILE_URL = "https://www.facebook.com/marketplace/profile/61578198642564"

# Log a archivo para poder revisar en el servidor
logging.basicConfig(
    filename='fb_scraper_debug.log',
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s %(message)s',
    force=True
)
log = logging.getLogger('fb_scraper')

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
        """Scrapea productos. Retorna (products, debug_lines)."""
        debug = []  # líneas de debug para mostrar en la UI
        self.driver.get(PROFILE_URL)
        time.sleep(3)

        current_url = self.driver.current_url
        page_title = self.driver.title
        debug.append(f"URL: {current_url}")
        debug.append(f"Título: {page_title}")
        log.info(f"Navegando a {PROFILE_URL} -> {current_url} | {page_title}")

        # Detección de login/bloqueo
        if (
            'login' in current_url or
            'Log in to Facebook' in page_title or
            self.driver.find_elements(By.NAME, 'login')
        ):
            msg = "ALERTA: Facebook pide login. Cookies caducadas."
            debug.append(msg)
            log.error(msg)
            self.driver.save_screenshot('error.png')
            return [], debug

        debug.append("Sesión OK. Iniciando scroll...")
        log.info("Sesión OK, iniciando scroll")

        # --- Scroll + recolección en tiempo real ---
        # Facebook NO scrollea con window.scrollTo (body height=941 fijo).
        # Usa un div contenedor con overflow. Scrolleamos haciendo
        # scrollIntoView() en el último producto visible para forzar carga.
        seen = {}  # listing_id -> {'title': ..., 'price': ...}
        max_scrolls = 100
        stale_attempts = 0
        max_stale = 10

        def _collect():
            """Lee productos visibles en el DOM y los acumula en seen."""
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
                            log.debug(f"  aria-label sin match: {lc[:120]}")
                            continue
                    if t:
                        seen[lid] = {'title': t, 'price': p}
                        log.debug(f"  NUEVO: [{lid}] {t} | {p}")
                except Exception as ex:
                    log.debug(f"  Error leyendo item: {ex}")
                    continue

        # JS para encontrar el contenedor scrolleable real de Facebook
        find_scroll_container_js = """
        var items = document.querySelectorAll('a[href*="/marketplace/item/"]');
        if (items.length === 0) return null;
        var el = items[0].parentElement;
        while (el && el !== document.body && el !== document.documentElement) {
            var style = window.getComputedStyle(el);
            if ((style.overflowY === 'scroll' || style.overflowY === 'auto') && el.scrollHeight > el.clientHeight) {
                return el;
            }
            el = el.parentElement;
        }
        return null;
        """

        scroll_container = self.driver.execute_script(find_scroll_container_js)
        if scroll_container:
            debug.append("Contenedor scroll detectado (div interno)")
            log.info("Contenedor scroll interno encontrado")
        else:
            debug.append("Sin contenedor scroll especial, usando fallbacks")
            log.info("No se encontró contenedor scroll interno")

        for i in range(max_scrolls):
            _collect()
            prev_total = len(seen)

            # Estrategia 1: scrollIntoView en el último producto visible
            items = self.driver.find_elements(By.XPATH, '//a[contains(@href, "/marketplace/item/")]')
            if items:
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({behavior: 'instant', block: 'end'});",
                    items[-1]
                )
            time.sleep(1)

            # Estrategia 2: si hay contenedor scroll, scrollearlo directamente
            if scroll_container:
                try:
                    self.driver.execute_script(
                        "arguments[0].scrollTop = arguments[0].scrollHeight;",
                        scroll_container
                    )
                except Exception:
                    pass
            else:
                # Fallback: window scroll + keyboard End
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)

            # Estrategia 3: simular tecla End / Page Down vía JS en el body
            try:
                self.driver.execute_script("""
                    document.body.dispatchEvent(new KeyboardEvent('keydown', {key: 'End', code: 'End', bubbles: true}));
                """)
            except Exception:
                pass
            time.sleep(1.5)

            # Cada 4 scrolls: subir un poco y volver a bajar para forzar lazy load
            if i % 4 == 3:
                if items:
                    mid = len(items) // 2
                    self.driver.execute_script(
                        "arguments[0].scrollIntoView({behavior: 'instant', block: 'center'});",
                        items[mid]
                    )
                    time.sleep(0.5)
                    self.driver.execute_script(
                        "arguments[0].scrollIntoView({behavior: 'instant', block: 'end'});",
                        items[-1]
                    )
                    time.sleep(1)

            _collect()
            new_total = len(seen)
            dom_links = len(self.driver.find_elements(By.XPATH, '//a[contains(@href, "/marketplace/item/")]'))

            # Debug info sobre scroll container
            sc_info = ""
            if scroll_container:
                try:
                    sc_info = self.driver.execute_script(
                        "return 'scrollTop=' + arguments[0].scrollTop + ' scrollH=' + arguments[0].scrollHeight + ' clientH=' + arguments[0].clientHeight;",
                        scroll_container
                    )
                except Exception:
                    sc_info = "error"

            line = f"Scroll {i+1}: acumulados={new_total} (+{new_total-prev_total}) | DOM_links={dom_links} | {sc_info}"
            log.info(line)

            if new_total > prev_total:
                stale_attempts = 0
                debug.append(line)
            else:
                stale_attempts += 1
                if stale_attempts >= max_stale:
                    debug.append(f"Scroll {i+1}: DETENIDO tras {max_stale} scrolls sin cambios. Total={new_total}")
                    log.info(f"Detenido en scroll {i+1} tras {max_stale} stale. Total={new_total}")
                    break

        debug.append(f"TOTAL RECOLECTADOS: {len(seen)}")
        log.info(f"Scroll finalizado. Total={len(seen)}")

        # Screenshot y HTML
        self.driver.save_screenshot('debug_fb.png')
        with open('debug_fb.html', 'w', encoding='utf-8') as f:
            f.write(self.driver.page_source)

        # Guardar lista de productos a archivo para inspección
        with open('debug_productos_fb.txt', 'w', encoding='utf-8') as f:
            for lid, prod in seen.items():
                f.write(f"[{lid}] {prod['title']} | {prod['price']}\n")
        debug.append(f"Archivos debug: debug_fb.png, debug_fb.html, debug_productos_fb.txt, fb_scraper_debug.log")

        products = list(seen.values())
        return products, debug

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
