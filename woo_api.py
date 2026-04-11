"""
woo_api.py — Capa de comunicación con la REST API de WooCommerce.
"""
import json
import os
from woocommerce import API

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")


def _load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_wcapi():
    cfg = _load_config()
    return API(
        url=cfg["url_sitio"],
        consumer_key=cfg["consumer_key"],
        consumer_secret=cfg["consumer_secret"],
        version="wc/v3",
        timeout=30,
        verify_ssl=False,
        query_string_auth=True,   # fuerza auth por query string (más compatible con hosting compartido)
    )


# ── Productos ────────────────────────────────────────────────────────────────

def buscar_producto_por_sku(sku: str) -> dict | None:
    """Devuelve el primer producto que coincida con el SKU dado, o None."""
    wcapi = get_wcapi()
    response = wcapi.get("products", params={"sku": sku, "per_page": 1})
    response.raise_for_status()
    productos = response.json()
    return productos[0] if productos else None


def buscar_producto_por_barcode(barcode: str) -> dict | None:
    """
    Busca por el meta _ywbc_barcode_value de YITH.
    WooCommerce no filtra por meta en la REST API nativa; se hace buscando
    por SKU primero (YITH suele sincronizarlos) y, si no, paginando productos.
    """
    # Intento rápido: muchas tiendas guardan el barcode como SKU
    producto = buscar_producto_por_sku(barcode)
    if producto:
        return producto

    cfg = _load_config()
    meta_key = cfg.get("yith_barcode_meta_key", "_ywbc_barcode_value")
    wcapi = get_wcapi()
    page = 1
    while True:
        resp = wcapi.get("products", params={"per_page": 100, "page": page})
        resp.raise_for_status()
        productos = resp.json()
        if not productos:
            break
        for p in productos:
            for meta in p.get("meta_data", []):
                if meta.get("key") == meta_key and str(meta.get("value")) == str(barcode):
                    return p
        page += 1
    return None


def obtener_producto_por_id(product_id: int) -> dict:
    wcapi = get_wcapi()
    resp = wcapi.get(f"products/{product_id}")
    resp.raise_for_status()
    return resp.json()


def actualizar_stock(product_id: int, nuevo_stock: int):
    wcapi = get_wcapi()
    resp = wcapi.put(f"products/{product_id}", data={"stock_quantity": nuevo_stock})
    resp.raise_for_status()
    return resp.json()


def incrementar_stock(product_id: int, cantidad: int):
    producto = obtener_producto_por_id(product_id)
    stock_actual = producto.get("stock_quantity") or 0
    return actualizar_stock(product_id, stock_actual + cantidad)


# ── Órdenes de Venta ─────────────────────────────────────────────────────────

def obtener_ordenes_completadas(desde_fecha: str = None) -> list:
    """
    Devuelve órdenes con estado 'completed'.
    desde_fecha: string ISO 8601, p. ej. '2024-01-01T00:00:00'
    """
    wcapi = get_wcapi()
    params = {"status": "completed", "per_page": 100}
    if desde_fecha:
        params["after"] = desde_fecha
    page, resultados = 1, []
    while True:
        params["page"] = page
        resp = wcapi.get("orders", params=params)
        resp.raise_for_status()
        datos = resp.json()
        if not datos:
            break
        resultados.extend(datos)
        page += 1
    return resultados


def obtener_ordenes_rango(desde_fecha: str = None, hasta_fecha: str = None) -> list:
    """
    Devuelve órdenes completadas Y en procesamiento dentro de un rango de fechas.
    Si desde_fecha es None devuelve todos los pedidos históricos.
    Usado para calcular velocidad de ventas en el análisis de Surtido.
    """
    wcapi = get_wcapi()
    resultados = []
    for status in ("completed", "processing"):
        page = 1
        while True:
            params = {"status": status, "per_page": 100, "page": page}
            if desde_fecha:
                params["after"] = desde_fecha
            if hasta_fecha:
                params["before"] = hasta_fecha
            resp = wcapi.get("orders", params=params)
            resp.raise_for_status()
            datos = resp.json()
            if not datos:
                break
            resultados.extend(datos)
            page += 1
    return resultados


def obtener_productos_por_ids(ids: list) -> dict:
    """Retorna {product_id: product_data} para los IDs dados, en lotes de 100."""
    wcapi = get_wcapi()
    resultado = {}
    batch_size = 100
    for i in range(0, len(ids), batch_size):
        batch = ids[i:i + batch_size]
        resp = wcapi.get("products", params={
            "include": ",".join(str(x) for x in batch),
            "per_page": batch_size,
        })
        resp.raise_for_status()
        for p in resp.json():
            resultado[p["id"]] = p
    return resultado


def get_todos_productos() -> list:
    """Devuelve todos los productos de WooCommerce con su stock actual."""
    wcapi = get_wcapi()
    page, resultados = 1, []
    while True:
        resp = wcapi.get("products", params={"per_page": 100, "page": page,
                                              "status": "publish"})
        resp.raise_for_status()
        datos = resp.json()
        if not datos:
            break
        resultados.extend(datos)
        page += 1
    return resultados


def get_barcode_de_producto(producto: dict, meta_key: str = "_ywbc_barcode_value") -> str:
    for meta in producto.get("meta_data", []):
        if meta.get("key") == meta_key:
            return str(meta.get("value", ""))
    return ""
