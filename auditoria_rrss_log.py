import json
from pathlib import Path
from datetime import datetime

LOG_PATH = Path(__file__).parent / "auditoria_rrss_log.json"

def cargar_log():
    if LOG_PATH.exists():
        try:
            return json.loads(LOG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []

def guardar_log(logs):
    LOG_PATH.write_text(json.dumps(logs, ensure_ascii=False, indent=2), encoding="utf-8")

def registrar_evento(producto, tipo, estado, detalle=None):
    logs = cargar_log()
    now = datetime.now().isoformat(timespec="seconds")
    logs.append({
        "producto": producto,
        "tipo": tipo,  # "Error de Precio" o "Publicación Oculta"
        "estado": estado,  # "detectado" o "parcheado"
        "fecha": now,
        "detalle": detalle or ""
    })
    guardar_log(logs)

def buscar_fecha_discrepancia(producto, tipo):
    logs = cargar_log()
    for entry in reversed(logs):
        if entry["producto"] == producto and entry["tipo"] == tipo and entry["estado"] == "detectado":
            return entry["fecha"]
    return ""

def registrar_parcheo(producto, tipo, detalle=None):
    registrar_evento(producto, tipo, "parcheado", detalle)
