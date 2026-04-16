import pandas as pd

def resumen_cambios(cambios):
    """Devuelve un resumen de los cambios detectados."""
    resumen = {
        'Nuevos': 0,
        'Eliminados': 0,
        'Modificados': 0
    }
    for c in cambios:
        if c['Cambio'] == 'Nuevo':
            resumen['Nuevos'] += 1
        elif c['Cambio'] == 'Eliminado':
            resumen['Eliminados'] += 1
        elif c['Cambio'] == 'Modificado':
            resumen['Modificados'] += 1
    return resumen


def discrepancias_woo_vs_fb(resultados_comparacion, fb_products):
    """
    Devuelve dos listas:
    - productos_woo_discrepancia: productos WooCommerce con estado != 'OK'
    - productos_fb_no_en_woo: productos en FB que no están en WooCommerce
    Args:
        resultados_comparacion: lista de dicts de fb_vs_woo.comparar_facebook_vs_woo
            [{Producto, Precio Web, Precio FB, Estado}]
        fb_products: lista de dicts del scraper [{title, price}]
    """
    productos_woo_discrepancia = []
    for p in resultados_comparacion:
        if p.get('Estado') and p['Estado'] != 'OK':
            productos_woo_discrepancia.append(p)

    # Comparar FB vs WooCommerce: productos de FB que no matchean con ninguno de Woo
    woo_nombres = {p['Producto'].strip().lower() for p in resultados_comparacion}
    productos_fb_no_en_woo = []
    for fb in (fb_products or []):
        nombre_fb = fb.get('title', '').strip().lower()
        if nombre_fb and nombre_fb not in woo_nombres:
            productos_fb_no_en_woo.append({
                'Producto FB': fb.get('title', ''),
                'Precio FB': fb.get('price', ''),
            })
    return productos_woo_discrepancia, productos_fb_no_en_woo
