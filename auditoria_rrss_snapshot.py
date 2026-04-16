import json
from pathlib import Path
from datetime import datetime

SNAPSHOT_PATH = Path(__file__).parent / "auditoria_rrss_snapshots.json"

# Guardar un snapshot de la verificación actual

def guardar_snapshot(resultados, fb_products=None):
    """Guarda el snapshot de la verificación con timestamp."""
    snapshots = cargar_snapshots()
    now = datetime.now().isoformat(timespec="seconds")
    entry = {
        "fecha": now,
        "data": resultados
    }
    if fb_products is not None:
        entry["fb_products"] = fb_products
    snapshots.append(entry)
    # Mantener solo los últimos 10 snapshots para no crecer indefinidamente
    if len(snapshots) > 10:
        snapshots = snapshots[-10:]
    SNAPSHOT_PATH.write_text(json.dumps(snapshots, ensure_ascii=False, indent=2), encoding="utf-8")


def cargar_snapshots():
    if SNAPSHOT_PATH.exists():
        try:
            return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def comparar_ultimos_snapshots():
    """Compara los dos últimos snapshots y retorna una lista de cambios."""
    snaps = cargar_snapshots()
    if len(snaps) < 2:
        return [], None, None
    prev, curr = snaps[-2], snaps[-1]
    prev_map = {r['Producto']: r for r in prev['data']}
    curr_map = {r['Producto']: r for r in curr['data']}
    cambios = []
    # Detectar cambios y diferencias
    productos = set(prev_map) | set(curr_map)
    for prod in productos:
        antes = prev_map.get(prod)
        despues = curr_map.get(prod)
        if antes and not despues:
            cambios.append({
                'Producto': prod,
                'Cambio': 'Eliminado',
                'Antes': antes,
                'Despues': None
            })
        elif not antes and despues:
            cambios.append({
                'Producto': prod,
                'Cambio': 'Nuevo',
                'Antes': None,
                'Despues': despues
            })
        elif antes and despues:
            # Comparar campos relevantes
            cambios_detalle = {}
            for campo in ['Estado', 'Precio Web', 'Precio FB']:
                if antes.get(campo) != despues.get(campo):
                    cambios_detalle[campo] = {'Antes': antes.get(campo), 'Despues': despues.get(campo)}
            if cambios_detalle:
                cambios.append({
                    'Producto': prod,
                    'Cambio': 'Modificado',
                    'Detalle': cambios_detalle,
                    'Antes': antes,
                    'Despues': despues
                })
    return cambios, prev['fecha'], curr['fecha']
