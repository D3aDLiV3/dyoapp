"""
etiquetas.py — Generador de Excel para impresión masiva de etiquetas.
"""
import json
import os
import pandas as pd

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")


def _get_meta_key() -> str:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    return cfg.get("yith_barcode_meta_key", "_ywbc_barcode_value")


def exportar_etiquetas(items: list[dict], ruta_salida: str):
    """
    Genera un archivo Excel con una fila por unidad (para impresión masiva).

    Cada elemento de `items` debe tener:
        - nombre     : str  — Nombre del producto
        - sku        : str  — SKU
        - precio     : float — Precio de venta
        - barcode    : str  — Valor del barcode YITH
        - cantidad   : int  — Número de etiquetas a generar

    Parámetro ruta_salida: path completo del .xlsx a crear.
    """
    filas = []
    for item in items:
        for _ in range(int(item["cantidad"])):
            filas.append({
                "Nombre": item["nombre"],
                "SKU": item["sku"],
                "Precio": item["precio"],
                "Barcode": item["barcode"],
            })

    if not filas:
        raise ValueError("No hay ítems para exportar.")

    df = pd.DataFrame(filas, columns=["Nombre", "SKU", "Precio", "Barcode"])
    df.to_excel(ruta_salida, index=False)
    return ruta_salida
