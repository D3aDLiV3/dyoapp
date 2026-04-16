
import db
import woo_api
from fb_marketplace_scraper import FacebookMarketplaceScraper
import auditoria_rrss_log as auditlog
from difflib import SequenceMatcher


def _normalizar(texto):
    """Normaliza texto para comparación: minúsculas, sin caracteres especiales extra."""
    import unicodedata
    t = texto.strip().lower()
    # Normalizar unicode (ej: – vs -)
    t = unicodedata.normalize('NFKD', t)
    # Reemplazar caracteres de puntuación similares
    for ch in ['–', '—', '‐', '‑']:
        t = t.replace(ch, '-')
    return t


def _buscar_mejor_match(nombre_woo, fb_map, umbral=0.65):
    """
    Busca el mejor match en fb_map para un nombre de WooCommerce.
    Primero intenta match exacto, luego substring, luego fuzzy.
    Retorna (fb_product, score, match_type) o (None, 0, None).
    """
    nombre_norm = _normalizar(nombre_woo)

    # 1. Match exacto
    if nombre_norm in fb_map:
        return fb_map[nombre_norm], 1.0, 'exact'

    # 2. Match por substring: si el nombre de Woo está contenido en el de FB o viceversa
    for fb_key, fb_val in fb_map.items():
        if nombre_norm in fb_key or fb_key in nombre_norm:
            return fb_val, 0.9, 'substring'

    # 3. Fuzzy match con SequenceMatcher
    mejor_score = 0
    mejor_fb = None
    for fb_key, fb_val in fb_map.items():
        score = SequenceMatcher(None, nombre_norm, fb_key).ratio()
        if score > mejor_score:
            mejor_score = score
            mejor_fb = fb_val

    if mejor_score >= umbral:
        # Validación extra: al menos 2 palabras significativas en común
        palabras_woo = set(w for w in nombre_norm.split() if len(w) > 2)
        palabras_fb = set(w for w in _normalizar(mejor_fb['title']).split() if len(w) > 2)
        comunes = palabras_woo & palabras_fb
        if len(comunes) >= 2:
            return mejor_fb, mejor_score, 'fuzzy'

    return None, 0, None


def comparar_facebook_vs_woo(fb_products, woo_products, stock_local):
    """
    Compara productos de Facebook Marketplace con WooCommerce/local.
    Args:
        fb_products: lista de dicts {'title', 'price'}
        woo_products: lista de dicts de WooCommerce
        stock_local: dict {product_id: stock}
    Returns:
        List[dict]: [Producto, Precio Web, Precio FB, Estado, Fecha Detectado]
    """
    fb_map = {_normalizar(p['title']): p for p in fb_products}
    fb_matched = set()  # tracking de productos FB ya matcheados
    resultados = []

    for pid, stock in stock_local.items():
        if stock <= 0:
            continue
        p_woo = next((p for p in woo_products if int(p.get('id', 0)) == int(pid)), None)
        if not p_woo:
            continue
        nombre = p_woo.get('name', '').strip()
        precio_web = float(p_woo.get('price', 0) or 0)
        fb, score, match_type = _buscar_mejor_match(nombre, fb_map)
        fecha_detectado = ""
        if fb:
            fb_matched.add(_normalizar(fb['title']))
            try:
                precio_fb = float(fb['price'].replace('$', '').replace('COP', '').replace('.', '').replace(',', '').strip())
            except Exception:
                precio_fb = fb['price']

            # Determinar estado según precio y calidad del match
            if abs(precio_web - precio_fb) < 0.01:
                if match_type == 'fuzzy' and score < 0.9:
                    estado = f'Titulo muy diferente (match ~{int(score*100)}%)'
                elif score >= 0.9:
                    estado = 'OK'
                else:
                    estado = f'OK (match ~{int(score*100)}%)'
                if auditlog.buscar_fecha_discrepancia(nombre, "Error de Precio"):
                    auditlog.registrar_parcheo(nombre, "Error de Precio", detalle=f"Precio corregido a {precio_web}")
            else:
                if match_type == 'fuzzy' and score < 0.9:
                    estado = f'Error de Precio / Titulo muy diferente (match ~{int(score*100)}%)'
                else:
                    estado = 'Error de Precio'
                fecha_detectado = auditlog.buscar_fecha_discrepancia(nombre, "Error de Precio")
                if not fecha_detectado:
                    auditlog.registrar_evento(nombre, "Error de Precio", "detectado", detalle=f"Web: {precio_web}, FB: {precio_fb}")
                    fecha_detectado = auditlog.buscar_fecha_discrepancia(nombre, "Error de Precio")
        else:
            precio_fb = ''
            estado = 'No Publicado en FB'
            fecha_detectado = auditlog.buscar_fecha_discrepancia(nombre, "Publicación Oculta")
            if not fecha_detectado:
                auditlog.registrar_evento(nombre, "Publicación Oculta", "detectado")
                fecha_detectado = auditlog.buscar_fecha_discrepancia(nombre, "Publicación Oculta")
        resultados.append({
            'Producto': nombre,
            'Precio Web': precio_web,
            'Precio FB': precio_fb,
            'Estado': estado,
            'Fecha Detectado': fecha_detectado
        })
    return resultados
