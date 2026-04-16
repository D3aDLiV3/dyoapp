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


def discrepancias_woo_vs_fb(woo, fb):
    """
    Devuelve dos listas:
    - productos_woo_discrepancia: productos en WooCommerce que no están en FB o tienen precio distinto
    - productos_fb_no_en_woo: productos en FB que no están en WooCommerce
    """
    woo_map = {p['Producto'].strip().lower(): p for p in woo}
    fb_map = {p['Producto'].strip().lower(): p for p in fb}
    productos_woo_discrepancia = []
    productos_fb_no_en_woo = []
    for nombre, p in woo_map.items():
        fb_p = fb_map.get(nombre)
        if not fb_p:
            productos_woo_discrepancia.append({**p, 'Motivo': 'No publicado en Facebook'})
        else:
            try:
                precio_fb = float(fb_p.get('Precio FB', 0) or 0)
            except Exception:
                precio_fb = fb_p.get('Precio FB', 0)
            if abs(float(p.get('Precio Web', 0)) - precio_fb) > 0.01:
                productos_woo_discrepancia.append({**p, 'Motivo': 'Precio distinto'})
    for nombre, p in fb_map.items():
        if nombre not in woo_map:
            productos_fb_no_en_woo.append(p)
    return productos_woo_discrepancia, productos_fb_no_en_woo
