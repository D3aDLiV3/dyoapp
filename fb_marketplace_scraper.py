

import time
import json
import re
import os
import shutil
import logging
import tempfile
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

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
        runtime_root = Path(__file__).resolve().parent / ".selenium-tmp"
        runtime_root.mkdir(exist_ok=True)

        # Limpieza best-effort de perfiles temporales viejos que hayan quedado.
        for old_dir in runtime_root.glob("chrome-profile-*"):
            try:
                shutil.rmtree(old_dir, ignore_errors=True)
            except Exception:
                pass

        self._profile_dir = Path(tempfile.mkdtemp(prefix="chrome-profile-", dir=str(runtime_root)))

        # Pre-crear la subcarpeta "Default" que Chrome necesita
        (self._profile_dir / "Default").mkdir(exist_ok=True)

        # Redirigir TODAS las variables de entorno que Chrome/chromedriver puedan usar
        env_override = os.environ.copy()
        for env_name in ("TMPDIR", "TMP", "TEMP"):
            env_override[env_name] = str(runtime_root)
            os.environ[env_name] = str(runtime_root)
        env_override["HOME"] = str(runtime_root)
        env_override["XDG_CONFIG_HOME"] = str(runtime_root / "xdg-config")
        env_override["XDG_CACHE_HOME"] = str(runtime_root / "xdg-cache")
        env_override["XDG_DATA_HOME"] = str(runtime_root / "xdg-data")
        os.environ["HOME"] = str(runtime_root)
        tempfile.tempdir = str(runtime_root)

        chrome_options = Options()
        if headless:
            chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument(f'--user-data-dir={self._profile_dir}')
        chrome_options.add_argument(f'--disk-cache-dir={self._profile_dir / "cache"}')
        chrome_options.add_argument('--no-first-run')
        chrome_options.add_argument('--disable-crash-reporter')
        chrome_options.add_argument('--disable-background-networking')
        chrome_options.add_argument(f'user-agent={USER_AGENT}')
        chromium_path = shutil.which('chromium-browser') or shutil.which('chromium')
        chrome_path = shutil.which('google-chrome')
        if chromium_path:
            chrome_options.binary_location = chromium_path
        elif chrome_path:
            chrome_options.binary_location = chrome_path

        # Pasar entorno limpio al proceso de chromedriver
        service_kwargs = {}
        if driver_path:
            service_kwargs['executable_path'] = driver_path
        try:
            svc = Service(**service_kwargs, env=env_override)
            self.driver = webdriver.Chrome(service=svc, options=chrome_options)
        except TypeError:
            # Fallback: versiones viejas de Selenium sin env en Service
            if driver_path:
                self.driver = webdriver.Chrome(executable_path=driver_path, options=chrome_options)
            else:
                self.driver = webdriver.Chrome(options=chrome_options)
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
        # Facebook usa virtual DOM: elementos se crean/destruyen al scrollear.
        # NUNCA guardar referencias WebElement entre scrolls (causa StaleElement).
        # Todo el scroll se hace con JS puro para evitar stale references.
        seen = {}  # listing_id -> {'title': ..., 'price': ...}
        max_scrolls = 100
        stale_attempts = 0
        max_stale = 10

        # JS que recolecta SOLO productos del perfil, excluyendo "Sugerencias de hoy"
        collect_js = """
        var result = [];
        // Encontrar la sección "Sugerencias de hoy" para excluirla
        var sugContainers = [];
        var spans = document.querySelectorAll('span');
        for (var i = 0; i < spans.length; i++) {
            var txt = spans[i].textContent.trim();
            if (txt === 'Sugerencias de hoy' || txt === "Today's picks") {
                var container = spans[i];
                while (container.parentElement && container.parentElement !== document.body) {
                    container = container.parentElement;
                    if (container.querySelectorAll('a[href*="/marketplace/item/"]').length >= 3) {
                        sugContainers.push(container);
                        break;
                    }
                }
            }
        }
        var items = document.querySelectorAll('a[href*="/marketplace/item/"]');
        items.forEach(function(a) {
            // Excluir si está dentro de un contenedor de Sugerencias
            var dominated = false;
            for (var j = 0; j < sugContainers.length; j++) {
                if (sugContainers[j].contains(a)) { dominated = true; break; }
            }
            if (dominated) return;
            var href = a.getAttribute('href') || '';
            var label = a.getAttribute('aria-label') || '';
            if (href && label) {
                result.push({href: href, label: label});
            }
        });
        return result;
        """

        # JS que scrollea haciendo scrollIntoView en el último producto
        scroll_last_js = """
        var items = document.querySelectorAll('a[href*="/marketplace/item/"]');
        if (items.length > 0) {
            items[items.length - 1].scrollIntoView({behavior: 'instant', block: 'end'});
        }
        """

        # JS que scrollea el contenedor padre overflow (si existe)
        scroll_container_js = """
        var items = document.querySelectorAll('a[href*="/marketplace/item/"]');
        if (items.length === 0) return 'no_items';
        var el = items[0].parentElement;
        while (el && el !== document.body && el !== document.documentElement) {
            var style = window.getComputedStyle(el);
            if ((style.overflowY === 'scroll' || style.overflowY === 'auto') && el.scrollHeight > el.clientHeight) {
                el.scrollTop = el.scrollHeight;
                return 'scrollTop=' + el.scrollTop + ' scrollH=' + el.scrollHeight + ' clientH=' + el.clientHeight;
            }
            el = el.parentElement;
        }
        window.scrollTo(0, document.body.scrollHeight);
        return 'window_fallback';
        """

        # JS para scroll intermedio (subir a la mitad y volver)
        scroll_bounce_js = """
        var items = document.querySelectorAll('a[href*="/marketplace/item/"]');
        if (items.length > 1) {
            var mid = Math.floor(items.length / 2);
            items[mid].scrollIntoView({behavior: 'instant', block: 'center'});
        }
        """

        def _collect_from_js():
            """Recolecta productos usando JS puro, sin WebElement refs."""
            try:
                raw = self.driver.execute_script(collect_js)
            except Exception as ex:
                log.debug(f"  Error en collect_js: {ex}")
                return
            for item in (raw or []):
                href = item.get('href', '')
                label = item.get('label', '')
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

        for i in range(max_scrolls):
            _collect_from_js()
            prev_total = len(seen)

            # Scroll: scrollIntoView en el último producto (JS puro)
            try:
                self.driver.execute_script(scroll_last_js)
            except Exception:
                pass
            time.sleep(1)

            # Scroll: contenedor padre overflow o window fallback
            try:
                sc_info = self.driver.execute_script(scroll_container_js)
            except Exception:
                sc_info = "error"
            time.sleep(1.5)

            # Cada 4 scrolls: bounce (subir a mitad, esperar, volver a bajar)
            if i % 4 == 3:
                try:
                    self.driver.execute_script(scroll_bounce_js)
                    time.sleep(0.5)
                    self.driver.execute_script(scroll_last_js)
                except Exception:
                    pass
                time.sleep(1)

            _collect_from_js()
            new_total = len(seen)

            line = f"Scroll {i+1}: acumulados={new_total} (+{new_total-prev_total}) | {sc_info}"
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
        try:
            self.driver.quit()
        except Exception:
            pass
        try:
            shutil.rmtree(self._profile_dir, ignore_errors=True)
        except Exception:
            pass

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
