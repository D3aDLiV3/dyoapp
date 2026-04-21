

import time
import json
import re
import os
import shutil
import logging
import tempfile
from logging.handlers import RotatingFileHandler
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
COOKIES_FILE = "cookies.json"
PROFILE_URL = "https://www.facebook.com/marketplace/profile/61578198642564"
ENABLE_FILE_LOGS = os.environ.get("FB_SCRAPER_FILE_LOGS", "0") == "1"
SAVE_DEBUG_ARTIFACTS = os.environ.get("FB_SCRAPER_SAVE_ARTIFACTS", "0") == "1"
FILE_LOG_MAX_BYTES = int(os.environ.get("FB_SCRAPER_FILE_LOG_MAX_BYTES", str(2 * 1024 * 1024)))
FILE_LOG_BACKUP_COUNT = int(os.environ.get("FB_SCRAPER_FILE_LOG_BACKUP_COUNT", "2"))

log = logging.getLogger('fb_scraper')
if not log.handlers:
    if ENABLE_FILE_LOGS:
        _fh = RotatingFileHandler(
            'fb_scraper_debug.log',
            maxBytes=FILE_LOG_MAX_BYTES,
            backupCount=FILE_LOG_BACKUP_COUNT,
            encoding='utf-8'
        )
        _fh.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        log.addHandler(_fh)
        log.setLevel(logging.DEBUG)
    else:
        log.addHandler(logging.NullHandler())
        log.setLevel(logging.WARNING)
log.propagate = False

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

    def _resolver_modal_perfil(self, debug):
        """Cierra o confirma el modal de selección de perfil si Facebook lo muestra."""
        modal_js = """
        function hasVisible(el) {
            if (!el) return false;
            var style = window.getComputedStyle(el);
            return style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0';
        }
        var dialogs = Array.from(document.querySelectorAll('[role="dialog"]')).filter(hasVisible);
        var target = null;
        for (var i = 0; i < dialogs.length; i++) {
            var txt = (dialogs[i].innerText || '').trim();
            if (/continue as|usar otro perfil|use another profile|profile/i.test(txt)) {
                target = dialogs[i];
                break;
            }
        }
        if (!target) {
            return {handled: false, reason: 'no_profile_modal'};
        }

        var buttons = Array.from(target.querySelectorAll('[role="button"], button, div[tabindex="0"]'));
        for (var j = 0; j < buttons.length; j++) {
            var text = (buttons[j].innerText || buttons[j].getAttribute('aria-label') || '').trim();
            if (/continue as/i.test(text)) {
                buttons[j].click();
                return {handled: true, action: 'continue', text: text};
            }
        }
        for (var k = 0; k < buttons.length; k++) {
            var closeText = (buttons[k].innerText || buttons[k].getAttribute('aria-label') || '').trim();
            if (/cerrar|close/i.test(closeText)) {
                buttons[k].click();
                return {handled: true, action: 'close', text: closeText};
            }
        }
        return {handled: false, reason: 'modal_without_known_buttons', text: (target.innerText || '').slice(0, 200)};
        """
        try:
            modal_info = self.driver.execute_script(modal_js)
        except Exception as ex:
            log.warning(f"No se pudo inspeccionar modal de perfil: {ex}")
            return

        if modal_info.get('handled'):
            action = modal_info.get('action', 'unknown')
            text = modal_info.get('text', '')
            debug.append(f"Modal perfil resuelto: action={action} | {text}")
            log.info(f"Modal perfil resuelto: action={action} | {text}")
            time.sleep(3)
        elif modal_info.get('reason') != 'no_profile_modal':
            debug.append(f"Modal perfil detectado pero no resuelto: {modal_info.get('reason')}")
            log.warning(f"Modal perfil detectado pero no resuelto: {modal_info}")

    def scrape_products(self):
        """Scrapea productos. Retorna (products, debug_lines)."""
        debug = []  # líneas de debug para mostrar en la UI
        self.driver.get(PROFILE_URL)
        time.sleep(3)
        self._resolver_modal_perfil(debug)

        # Espera corta por si Facebook tarda en hidratar el HTML tras un reinicio del servidor.
        page_diag_js = """
        function countIn(root) {
            if (!root || !root.querySelectorAll) return 0;
            return root.querySelectorAll('a[href*="/marketplace/item/"]').length;
        }
        var dialog = document.querySelector('[role="dialog"][aria-modal="true"]');
        var main = document.querySelector('[role="main"]');
        var txt = (document.body && document.body.innerText ? document.body.innerText : '').slice(0, 3000);
        return {
            url: location.href,
            docItems: countIn(document),
            dialogItems: countIn(dialog),
            mainItems: countIn(main),
            hasLoginWord: /\blog.?in\b|iniciar sesi[oó]n|\bentrar\b|\blogin\b/i.test(txt),
            hasMarketplaceWord: /marketplace|publicaciones|disponibles y en stock|ordenar por/i.test(txt),
            textSample: txt.slice(0, 600)
        };
        """
        for _ in range(6):
            try:
                diag = self.driver.execute_script(page_diag_js)
            except Exception:
                diag = {}
            if (diag.get('docItems', 0) or diag.get('dialogItems', 0) or diag.get('mainItems', 0)):
                break
            time.sleep(2)

        current_url = self.driver.current_url
        page_title = self.driver.title
        debug.append(f"URL: {current_url}")
        debug.append(f"Título: {page_title}")
        log.info(f"Navegando a {PROFILE_URL} -> {current_url} | {page_title}")

        # Detección de login/bloqueo
        has_marketplace = (
            diag.get('docItems', 0) > 0 or
            diag.get('dialogItems', 0) > 0 or
            diag.get('mainItems', 0) > 0 or
            diag.get('hasMarketplaceWord')
        )
        if not has_marketplace and (
            'login' in current_url or
            'Log in to Facebook' in page_title or
            diag.get('hasLoginWord')
        ):
            msg = "ALERTA: Facebook pide login. Cookies caducadas."
            debug.append(msg)
            log.error(msg)
            if SAVE_DEBUG_ARTIFACTS:
                self.driver.save_screenshot('error.png')
            return [], debug

        debug.append(
            "Diag inicial: "
            f"docItems={diag.get('docItems', 0)} | "
            f"dialogItems={diag.get('dialogItems', 0)} | "
            f"mainItems={diag.get('mainItems', 0)} | "
            f"marketplaceText={diag.get('hasMarketplaceWord')}"
        )
        if diag.get('textSample'):
            log.info(f"Text sample inicial: {diag.get('textSample')[:300]}")

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
        # y priorizando la capa modal del perfil de Marketplace.
        collect_js = """
        function countItems(root) {
            if (!root || !root.querySelectorAll) return 0;
            return root.querySelectorAll('a[href*="/marketplace/item/"]').length;
        }
        function getRoot() {
            var candidates = [
                {name: 'dialog', el: document.querySelector('[role="dialog"][aria-modal="true"]')},
                {name: 'main', el: document.querySelector('[role="main"]')},
                {name: 'document', el: document}
            ];
            var best = candidates[2];
            var bestCount = -1;
            candidates.forEach(function(c) {
                var count = countItems(c.el);
                if (count > bestCount) {
                    best = c;
                    bestCount = count;
                }
            });
            return best;
        }
        var selected = getRoot();
        var root = selected.el;
        var result = [];
        var sugContainers = [];
        var totalItems = root.querySelectorAll('a[href*="/marketplace/item/"]').length;
        var spans = root.querySelectorAll('span');
        for (var i = 0; i < spans.length; i++) {
            var txt = (spans[i].textContent || '').trim();
            if (txt === 'Sugerencias de hoy' || txt === "Today's picks") {
                var container = spans[i];
                var levels = 0;
                while (container.parentElement && container.parentElement !== root && levels < 6) {
                    container = container.parentElement;
                    levels++;
                    var inContainer = container.querySelectorAll('a[href*="/marketplace/item/"]').length;
                    if (inContainer >= 3 && inContainer < totalItems) {
                        sugContainers.push(container);
                        break;
                    }
                }
            }
        }
        var items = root.querySelectorAll('a[href*="/marketplace/item/"]');
        items.forEach(function(a) {
            var dominated = false;
            for (var j = 0; j < sugContainers.length; j++) {
                if (sugContainers[j].contains(a)) { dominated = true; break; }
            }
            if (dominated) return;
            var href = a.getAttribute('href') || '';
            var label = a.getAttribute('aria-label') || '';
            var text = (a.innerText || a.textContent || '').replace(/\s+/g, ' ').trim();
            if (!label && text) {
                label = text;
            }
            if (href) {
                result.push({href: href, label: label, rawText: text});
            }
        });
        return {
            rootName: selected.name,
            rootTag: root === document ? 'document' : root.tagName,
            rootClass: root === document ? '' : (root.className || ''),
            itemCount: items.length,
            items: result
        };
        """

        # JS de scroll centrado en el dialog real del perfil.
        scroll_all_js = """
        function countItems(root) {
            if (!root || !root.querySelectorAll) return 0;
            return root.querySelectorAll('a[href*="/marketplace/item/"]').length;
        }
        function getRoot() {
            var dialog = {name: 'dialog', el: document.querySelector('[role="dialog"][aria-modal="true"]')};
            var main = {name: 'main', el: document.querySelector('[role="main"]')};
            var doc = {name: 'document', el: document};
            if (countItems(dialog.el) >= 6) return dialog;
            if (countItems(main.el) >= 6) return main;
            if (countItems(dialog.el) > 0) return dialog;
            if (countItems(main.el) > 0) return main;
            return doc;
        }
        function hasLoading(root) {
            var scope = (root === document) ? document.body : root;
            if (!scope) return false;
            var selectors = [
                '[role="progressbar"]',
                '[aria-busy="true"]',
                '[data-visualcompletion="loading-state"]',
                '[data-visualcompletion="loading"]',
                '.x1n2onr6',
                '.x1ja2u2z'
            ];
            for (var i = 0; i < selectors.length; i++) {
                if (scope.querySelector(selectors[i])) return true;
            }
            var text = (scope.innerText || '').slice(-800).trim();
            return /cargando|loading|cargando m[aá]s/i.test(text);
        }
        function findScroller(root, lastItem) {
            var candidate = null;
            var maxScrollRoom = -1;
            var bodyRoot = (root === document) ? document.body : root;
            var anchor = lastItem;
            while (anchor && anchor !== bodyRoot && anchor !== document.body && anchor !== document.documentElement) {
                var anchorRoom = anchor.scrollHeight - anchor.clientHeight;
                var anchorStyle = window.getComputedStyle(anchor);
                if ((anchorStyle.overflowY === 'auto' || anchorStyle.overflowY === 'scroll' || anchorStyle.overflowY === 'overlay') && anchorRoom > 120) {
                    return anchor;
                }
                anchor = anchor.parentElement;
            }
            var nodes = [bodyRoot].concat(Array.from(bodyRoot.querySelectorAll('div, section, main')));
            nodes.forEach(function(el) {
                if (!el || el.nodeType !== 1) return;
                if (lastItem && !el.contains(lastItem) && el !== bodyRoot) return;
                var style = window.getComputedStyle(el);
                var overflowY = style.overflowY;
                var scrollRoom = el.scrollHeight - el.clientHeight;
                if ((overflowY === 'auto' || overflowY === 'scroll' || overflowY === 'overlay') && scrollRoom > 120) {
                    if (scrollRoom > maxScrollRoom) {
                        candidate = el;
                        maxScrollRoom = scrollRoom;
                    }
                }
            });
            if (!candidate && lastItem) {
                var el = lastItem.parentElement;
                while (el && el !== bodyRoot && el !== document.body && el !== document.documentElement) {
                    var scrollRoom = el.scrollHeight - el.clientHeight;
                    if (scrollRoom > 120) {
                        candidate = el;
                        break;
                    }
                    el = el.parentElement;
                }
            }
            return candidate;
        }

        var selected = getRoot();
        var root = selected.el;
        var bodyRoot = (root === document) ? document.body : root;
        var items = bodyRoot.querySelectorAll('a[href*="/marketplace/item/"]');
        var info = {
            rootName: selected.name,
            rootTag: root === document ? 'document' : root.tagName,
            itemCount: items.length
        };
        var lastItem = items.length ? items[items.length - 1] : null;
        info.lastHref = lastItem ? (lastItem.getAttribute('href') || '') : '';

        if (lastItem) {
            lastItem.scrollIntoView({behavior: 'instant', block: 'end'});
        }

        var scroller = findScroller(root, lastItem);
        if (scroller) {
            var before = scroller.scrollTop;
            var maxTop = Math.max(0, scroller.scrollHeight - scroller.clientHeight);
            var step = Math.max(700, Math.floor(scroller.clientHeight * 0.9));
            scroller.scrollTop = Math.min(scroller.scrollTop + step, maxTop);
            if (scroller.scrollTop === before && lastItem) {
                lastItem.scrollIntoView({behavior: 'instant', block: 'center'});
                scroller.scrollTop = Math.min(scroller.scrollTop + Math.max(320, Math.floor(step * 0.45)), maxTop);
            }
            info.scroller = 'tag=' + scroller.tagName + ' before=' + before + ' after=' + scroller.scrollTop + ' step=' + step + ' maxTop=' + maxTop + ' scrollH=' + scroller.scrollHeight + ' clientH=' + scroller.clientHeight;
        } else {
            var se = document.scrollingElement || document.documentElement;
            var before = se.scrollTop;
            se.scrollTop = se.scrollTop + Math.max(700, Math.floor(window.innerHeight * 0.9));
            info.scroller = 'fallback before=' + before + ' after=' + se.scrollTop + ' scrollH=' + se.scrollHeight + ' clientH=' + se.clientHeight;
        }
        info.loading = hasLoading(root);

        var thumb = root.querySelector('[data-thumb="1"]');
        if (thumb) {
            info.thumb = 'h=' + thumb.style.height + ' class=' + (thumb.className || '').slice(0, 80);
        }
        return JSON.stringify(info);
        """

        # JS para scroll intermedio dentro del mismo contenedor del dialog.
        scroll_bounce_js = """
        function countItems(root) {
            if (!root || !root.querySelectorAll) return 0;
            return root.querySelectorAll('a[href*="/marketplace/item/"]').length;
        }
        function getRoot() {
            var dialog = document.querySelector('[role="dialog"][aria-modal="true"]');
            var main = document.querySelector('[role="main"]');
            if (countItems(dialog) >= 6) return dialog;
            if (countItems(main) >= 6) return main;
            if (countItems(dialog) > 0) return dialog;
            if (countItems(main) > 0) return main;
            return document;
        }
        var root = getRoot();
        var bodyRoot = (root === document) ? document.body : root;
        var items = bodyRoot.querySelectorAll('a[href*="/marketplace/item/"]');
        if (items.length > 1) {
            var mid = Math.floor(items.length / 2);
            items[mid].scrollIntoView({behavior: 'instant', block: 'center'});
        }
        var nodes = [bodyRoot].concat(Array.from(bodyRoot.querySelectorAll('div, section, main')));
        for (var i = 0; i < nodes.length; i++) {
            var el = nodes[i];
            if (el.nodeType !== 1) continue;
            if ((el.scrollHeight - el.clientHeight) > 120) {
                el.scrollTop = Math.max(0, Math.floor(el.scrollTop * 0.5));
                break;
            }
        }
        """

        feed_state_js = """
        function countItems(root) {
            if (!root || !root.querySelectorAll) return 0;
            return root.querySelectorAll('a[href*="/marketplace/item/"]').length;
        }
        function getRoot() {
            var dialog = {name: 'dialog', el: document.querySelector('[role="dialog"][aria-modal="true"]')};
            var main = {name: 'main', el: document.querySelector('[role="main"]')};
            var doc = {name: 'document', el: document};
            if (countItems(dialog.el) >= 6) return dialog;
            if (countItems(main.el) >= 6) return main;
            if (countItems(dialog.el) > 0) return dialog;
            if (countItems(main.el) > 0) return main;
            return doc;
        }
        function hasLoading(root) {
            var scope = (root === document) ? document.body : root;
            if (!scope) return false;
            var selectors = [
                '[role="progressbar"]',
                '[aria-busy="true"]',
                '[data-visualcompletion="loading-state"]',
                '[data-visualcompletion="loading"]',
                '.x1n2onr6',
                '.x1ja2u2z'
            ];
            for (var i = 0; i < selectors.length; i++) {
                if (scope.querySelector(selectors[i])) return true;
            }
            var text = (scope.innerText || '').slice(-800).trim();
            return /cargando|loading|cargando m[aá]s/i.test(text);
        }
        var selected = getRoot();
        var root = selected.el;
        var bodyRoot = (root === document) ? document.body : root;
        var items = bodyRoot.querySelectorAll('a[href*="/marketplace/item/"]');
        var lastItem = items.length ? items[items.length - 1] : null;
        return {
            rootName: selected.name,
            itemCount: items.length,
            lastHref: lastItem ? (lastItem.getAttribute('href') || '') : '',
            loading: hasLoading(root)
        };
        """

        descartes = {'sin_precio': 0, 'sin_titulo': 0, 'href_invalido': 0}
        _price_full_re = re.compile(
            r'((?:COP|USD|EUR)\s*[\d][.,\d]*|'
            r'\$\s*[\d][.,\d]*|'
            r'[\d][.,\d]*\s*(?:COP|USD|EUR))',
            re.IGNORECASE
        )

        def _clean_meta(s):
            s = re.sub(r',?\s*listing\s+\d+', '', s, flags=re.IGNORECASE)
            s = re.sub(r',?\s*\b(?:Available|Disponible)\b', '', s, flags=re.IGNORECASE)
            return s.strip(' ,|-')

        def _collect_from_js():
            """Recolecta productos usando JS puro, sin WebElement refs."""
            try:
                raw = self.driver.execute_script(collect_js)
            except Exception as ex:
                log.debug(f"  Error en collect_js: {ex}")
                return
            if raw and raw.get('rootTag'):
                log.debug(
                    f"  collect_js root={raw.get('rootName')}/{raw.get('rootTag')} "
                    f"items={raw.get('itemCount', 0)} class={raw.get('rootClass', '')[:80]}"
                )
            for item in ((raw or {}).get('items') or []):
                href = item.get('href', '')
                label = item.get('label', '')
                raw_text = item.get('rawText', '')
                lm = re.search(r'/marketplace/item/(\d+)', href)
                if not lm:
                    descartes['href_invalido'] += 1
                    continue
                lid = lm.group(1)
                if lid in seen:
                    continue
                # Nivel 1: aria-label limpio
                lc = _clean_meta((label or '').replace('\xa0', ' '))
                pm = _price_full_re.search(lc)
                if pm:
                    p = pm.group(0).strip()
                    before = lc[:pm.start()].strip(' ,|-')
                    after_txt = lc[pm.end():].strip(' ,|-')
                    t = before if before else after_txt
                else:
                    # Nivel 2: rawText limpio
                    fb = _clean_meta(raw_text.replace('\xa0', ' '))
                    pm = _price_full_re.search(fb)
                    if pm:
                        p = pm.group(0).strip()
                        before = fb[:pm.start()].strip(' ,|-')
                        after_txt = fb[pm.end():].strip(' ,|-')
                        t = before if before else after_txt
                    else:
                        # Nivel 3: sin precio encontrado
                        descartes['sin_precio'] += 1
                        log.debug(f"  sin precio: label={lc[:120]} raw={raw_text[:120]}")
                        continue
                if not t:
                    descartes['sin_titulo'] += 1
                    log.debug(f"  sin titulo: label={lc[:120]} raw={raw_text[:120]}")
                    continue
                seen[lid] = {'title': t, 'price': p}
                log.debug(f"  NUEVO: [{lid}] {t} | {p}")

        def _get_feed_state():
            try:
                return self.driver.execute_script(feed_state_js) or {}
            except Exception as ex:
                log.debug(f"  Error en feed_state_js: {ex}")
                return {}

        def _wait_until_feed_settles(prev_dom_items, prev_last_href):
            state = {}
            for _ in range(8):
                state = _get_feed_state()
                dom_items = state.get('itemCount', 0)
                last_href = state.get('lastHref', '')
                loading = bool(state.get('loading'))
                if not loading and (dom_items > prev_dom_items or last_href != prev_last_href):
                    return state
                if not loading and dom_items == prev_dom_items and last_href == prev_last_href:
                    return state
                time.sleep(1)
            return state

        for i in range(max_scrolls):
            _collect_from_js()
            prev_total = len(seen)
            before_state = _get_feed_state()
            prev_dom_items = before_state.get('itemCount', 0)
            prev_last_href = before_state.get('lastHref', '')

            # Scroll agresivo: todas las estrategias de una vez
            try:
                sc_info = self.driver.execute_script(scroll_all_js)
            except Exception as ex:
                sc_info = f"error: {ex}"
            after_state = _wait_until_feed_settles(prev_dom_items, prev_last_href)

            # Cada 4 scrolls: bounce (subir a mitad, esperar, volver a bajar)
            if i % 4 == 3:
                try:
                    self.driver.execute_script(scroll_bounce_js)
                    time.sleep(1)
                    self.driver.execute_script(scroll_all_js)
                except Exception:
                    pass
                after_state = _wait_until_feed_settles(
                    after_state.get('itemCount', prev_dom_items),
                    after_state.get('lastHref', prev_last_href)
                )

            _collect_from_js()
            new_total = len(seen)
            dom_after = after_state.get('itemCount', 0)
            last_after = after_state.get('lastHref', '')
            loading_after = bool(after_state.get('loading'))

            line = (
                f"Scroll {i+1}: acumulados={new_total} (+{new_total-prev_total}) "
                f"| dom={prev_dom_items}->{dom_after} "
                f"| lastChanged={last_after != prev_last_href} "
                f"| loading={loading_after} | {sc_info}"
            )
            log.info(line)

            if new_total > prev_total or dom_after > prev_dom_items or last_after != prev_last_href:
                stale_attempts = 0
                debug.append(line)
            else:
                stale_attempts += 1
                if stale_attempts >= max_stale:
                    debug.append(f"Scroll {i+1}: DETENIDO tras {max_stale} scrolls sin cambios. Total={new_total}")
                    log.info(f"Detenido en scroll {i+1} tras {max_stale} stale. Total={new_total}")
                    break

        debug.append(f"TOTAL RECOLECTADOS: {len(seen)}")
        debug.append(f"Descartes: sin_precio={descartes['sin_precio']} sin_titulo={descartes['sin_titulo']} href_invalido={descartes['href_invalido']}")
        log.info(f"Scroll finalizado. Total={len(seen)}")

        if not seen:
            try:
                final_diag = self.driver.execute_script(page_diag_js)
            except Exception:
                final_diag = {}
            debug.append(
                "Diag final sin resultados: "
                f"docItems={final_diag.get('docItems', 0)} | "
                f"dialogItems={final_diag.get('dialogItems', 0)} | "
                f"mainItems={final_diag.get('mainItems', 0)} | "
                f"marketplaceText={final_diag.get('hasMarketplaceWord')} | "
                f"loginText={final_diag.get('hasLoginWord')}"
            )
            log.warning(f"Scraping terminó en 0 productos. Diag={final_diag}")

        if SAVE_DEBUG_ARTIFACTS:
            self.driver.save_screenshot('debug_fb.png')
            with open('debug_fb.html', 'w', encoding='utf-8') as f:
                f.write(self.driver.page_source)
            with open('debug_productos_fb.txt', 'w', encoding='utf-8') as f:
                for lid, prod in seen.items():
                    f.write(f"[{lid}] {prod['title']} | {prod['price']}\n")
            if ENABLE_FILE_LOGS:
                debug.append("Archivos debug: debug_fb.png, debug_fb.html, debug_productos_fb.txt, fb_scraper_debug.log")
            else:
                debug.append("Archivos debug: debug_fb.png, debug_fb.html, debug_productos_fb.txt")

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
