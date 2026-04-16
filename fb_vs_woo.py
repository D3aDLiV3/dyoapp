
import db
import woo_api
from fb_marketplace_scraper import FacebookMarketplaceScraper
import auditoria_rrss_log as auditlog


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
    woo_map = {p['name'].strip().lower(): p for p in woo_products}
    fb_map = {p['title'].strip().lower(): p for p in fb_products}
    resultados = []

    for pid, stock in stock_local.items():
        if stock <= 0:
            continue
        p_woo = next((p for p in woo_products if int(p.get('id', 0)) == int(pid)), None)
        if not p_woo:
            continue
        nombre = p_woo.get('name', '').strip()
        precio_web = float(p_woo.get('price', 0) or 0)
        fb = fb_map.get(nombre.lower())
        fecha_detectado = ""
        if fb:
            try:
                # Formato colombiano: $ 80.000 (punto = separador de miles)
                precio_fb = float(fb['price'].replace('$', '').replace('COP', '').replace('.', '').replace(',', '').strip())
            except Exception:
                precio_fb = fb['price']
            if abs(precio_web - precio_fb) < 0.01:
                estado = 'OK'
                # Si antes hubo discrepancia, registrar parcheo
                if auditlog.buscar_fecha_discrepancia(nombre, "Error de Precio"):
                    auditlog.registrar_parcheo(nombre, "Error de Precio", detalle=f"Precio corregido a {precio_web}")
            else:
                estado = 'Error de Precio'
                fecha_detectado = auditlog.buscar_fecha_discrepancia(nombre, "Error de Precio")
                if not fecha_detectado:
                    auditlog.registrar_evento(nombre, "Error de Precio", "detectado", detalle=f"Web: {precio_web}, FB: {precio_fb}")
                    fecha_detectado = auditlog.buscar_fecha_discrepancia(nombre, "Error de Precio")
        else:
            precio_fb = ''
            estado = 'Posible Publicación Oculta'
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
