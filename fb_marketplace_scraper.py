

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
        # --- Directorio de trabajo para Chrome ---
        # Usar /tmp en Linux (siempre escribible, compatible con snap Chromium)
        # o .selenium-tmp en Windows/fallback
        if os.name != 'nt' and os.path.isdir('/tmp'):
            runtime_root = Path('/tmp/selenium-dyo')
        else:
            runtime_root = Path(__file__).resolve().parent / ".selenium-tmp"
        runtime_root.mkdir(parents=True, exist_ok=True)

        # Matar procesos Chrome/chromedriver zombie que puedan bloquear el perfil
        if os.name != 'nt':
            try:
                os.system("pkill -f 'chrome-profile-dyo' 2>/dev/null || true")
                time.sleep(0.5)
            except Exception:
                pass

        # Usar perfil FIJO (no aleatorio) para evitar acumulación de basura
        self._profile_dir = runtime_root / "chrome-profile-dyo"
        if self._profile_dir.exists():
            shutil.rmtree(self._profile_dir, ignore_errors=True)
        self._profile_dir.mkdir(parents=True, exist_ok=True)
        (self._profile_dir / "Default").mkdir(exist_ok=True)

        log.info(f"runtime_root={runtime_root}  profile={self._profile_dir}")
        log.info(f"profile exists={self._profile_dir.exists()}  Default exists={(self._profile_dir / 'Default').exists()}")

        # Variables de entorno para Chrome y chromedriver
        for env_name in ("TMPDIR", "TMP", "TEMP"):
            os.environ[env_name] = str(runtime_root)
        os.environ["HOME"] = str(runtime_root)
        os.environ["XDG_CONFIG_HOME"] = str(runtime_root / "xdg-config")
        os.environ["XDG_CACHE_HOME"] = str(runtime_root / "xdg-cache")
        os.environ["XDG_DATA_HOME"] = str(runtime_root / "xdg-data")
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

        # Detectar binario de Chrome/Chromium
        chromium_path = shutil.which('chromium-browser') or shutil.which('chromium')
        chrome_path = shutil.which('google-chrome')
        binary = chromium_path or chrome_path
        if binary:
            chrome_options.binary_location = binary
            # Detectar si es snap (causa problemas de escritura)
            if '/snap/' in str(Path(binary).resolve()):
                log.warning(f"SNAP Chromium detectado: {binary} → puede causar problemas de perfil")
        log.info(f"Chrome binary: {binary}")

        # Lanzar chromedriver con entorno controlado
        svc_args = {'env': os.environ.copy()}
        if driver_path:
            svc_args['executable_path'] = driver_path
        try:
            svc = Service(**svc_args)
            self.driver = webdriver.Chrome(service=svc, options=chrome_options)
        except TypeError:
            log.warning("Service(env=) no soportado, usando fallback sin env")
            if driver_path:
                self.driver = webdriver.Chrome(executable_path=driver_path, options=chrome_options)
            else:
                self.driver = webdriver.Chrome(options=chrome_options)
        log.info("Chrome iniciado correctamente")
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

        # JS de scroll agresivo: prueba TODAS las estrategias posibles
        # Facebook puede scrollear en: document.scrollingElement, role="main",
        # un div con overflow, o necesitar scrollIntoView.
        scroll_all_js = """
        var items = document.querySelectorAll('a[href*="/marketplace/item/"]');
        var info = {};

        // 1. scrollIntoView en el último producto (fuerza el viewport a moverlo)
        if (items.length > 0) {
            items[items.length - 1].scrollIntoView({behavior: 'instant', block: 'end'});
        }

        // 2. Scroll del document.scrollingElement (viewport principal)
        var se = document.scrollingElement || document.documentElement;
        var before = se.scrollTop;
        se.scrollTop = se.scrollHeight;
        info.scrollingElement = 'before=' + before + ' after=' + se.scrollTop + ' scrollH=' + se.scrollHeight;

        // 3. Scroll de [role="main"] si existe
        var main = document.querySelector('[role="main"]');
        if (main && main.scrollHeight > main.clientHeight) {
            main.scrollTop = main.scrollHeight;
            info.roleMain = 'scrollTop=' + main.scrollTop + ' scrollH=' + main.scrollHeight;
        }

        // 4. Buscar TODOS los contenedores con overflow-y entre los ancestros de los productos
        //    y scrollear cada uno al fondo
        if (items.length > 0) {
            var el = items[0];
            var scrolled = [];
            while (el && el !== document.body && el !== document.documentElement) {
                el = el.parentElement;
                if (!el) break;
                var style = window.getComputedStyle(el);
                var ov = style.overflowY;
                if ((ov === 'scroll' || ov === 'auto' || ov === 'hidden') && el.scrollHeight > el.clientHeight + 10) {
                    var bef = el.scrollTop;
                    el.scrollTop = el.scrollHeight;
                    scrolled.push('tag=' + el.tagName + ' before=' + bef + ' after=' + el.scrollTop + ' sH=' + el.scrollHeight + ' cH=' + el.clientHeight);
                }
            }
            if (scrolled.length > 0) info.ancestors = scrolled.join(' | ');
        }

        // 5. También hacer window.scrollTo como fallback final
        window.scrollTo(0, document.body.scrollHeight);

        return JSON.stringify(info);
        """

        # JS para scroll intermedio (subir y volver, simula usuario)
        scroll_bounce_js = """
        var se = document.scrollingElement || document.documentElement;
        // Subir a la mitad
        se.scrollTop = Math.floor(se.scrollHeight / 2);
        // También scrollIntoView a un producto del medio
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

            # Scroll agresivo: todas las estrategias de una vez
            try:
                sc_info = self.driver.execute_script(scroll_all_js)
            except Exception as ex:
                sc_info = f"error: {ex}"
            time.sleep(2)

            # Cada 4 scrolls: bounce (subir a mitad, esperar, volver a bajar)
            if i % 4 == 3:
                try:
                    self.driver.execute_script(scroll_bounce_js)
                    time.sleep(1)
                    self.driver.execute_script(scroll_all_js)
                except Exception:
                    pass
                time.sleep(1.5)

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
