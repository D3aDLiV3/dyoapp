"""
db.py — Capa de acceso a la base de datos SQLite local.
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "wooposadmin.db")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema_local.sql")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Crea las tablas si no existen, usando schema_local.sql."""
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema = f.read()
    with get_connection() as conn:
        conn.executescript(schema)


# ── Órdenes de Compra ────────────────────────────────────────────────────────

def crear_orden_compra(proveedor: str, notas: str = "") -> int:
    sql = "INSERT INTO ordenes_compra (proveedor, notas) VALUES (?, ?)"
    with get_connection() as conn:
        cur = conn.execute(sql, (proveedor, notas))
        return cur.lastrowid


def listar_ordenes_compra() -> list:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM ordenes_compra ORDER BY fecha_ingreso DESC"
        ).fetchall()


# ── Lotes de Inventario (FIFO) ───────────────────────────────────────────────

def crear_lote(id_oc: int, product_id: int, sku: str,
               cantidad: int, precio_compra: float) -> int:
    sql = """
        INSERT INTO lotes_inventario
            (id_oc, product_id, sku, cantidad_inicial, cantidad_actual, precio_compra_unitario)
        VALUES (?, ?, ?, ?, ?, ?)
    """
    with get_connection() as conn:
        cur = conn.execute(sql, (id_oc, product_id, sku, cantidad, cantidad, precio_compra))
        return cur.lastrowid


def listar_lotes_por_producto(product_id: int) -> list:
    """Devuelve lotes ordenados por FIFO (más antiguos primero) con stock > 0."""
    sql = """
        SELECT * FROM lotes_inventario
        WHERE product_id = ? AND cantidad_actual > 0
        ORDER BY id_lote ASC
    """
    with get_connection() as conn:
        return conn.execute(sql, (product_id,)).fetchall()


def listar_todos_lotes() -> list:
    """Devuelve todos los lotes con info de la OC, para el dashboard de inventario."""
    sql = """
        SELECT
            li.id_lote,
            oc.id_oc,
            oc.proveedor,
            oc.fecha_ingreso,
            li.product_id,
            li.sku,
            li.cantidad_inicial,
            li.cantidad_actual,
            li.precio_compra_unitario,
            ROUND(li.cantidad_actual * li.precio_compra_unitario, 2) AS valor_stock
        FROM lotes_inventario li
        LEFT JOIN ordenes_compra oc ON oc.id_oc = li.id_oc
        ORDER BY li.id_lote DESC
    """
    with get_connection() as conn:
        return conn.execute(sql).fetchall()


def descontar_lote(id_lote: int, cantidad: int):
    sql = "UPDATE lotes_inventario SET cantidad_actual = cantidad_actual - ? WHERE id_lote = ?"
    with get_connection() as conn:
        conn.execute(sql, (cantidad, id_lote))


# ── Ventas Procesadas ────────────────────────────────────────────────────────

def registrar_venta(order_id_woo: int, product_id: int, cantidad_vendida: int,
                    precio_venta: float, costo_total: float,
                    utilidad_neta: float, fecha_venta: str):
    sql = """
        INSERT INTO ventas_procesadas
            (order_id_woo, product_id, cantidad_vendida, precio_venta_unitario,
             costo_total_lote, utilidad_neta, fecha_venta)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """
    with get_connection() as conn:
        conn.execute(sql, (order_id_woo, product_id, cantidad_vendida,
                           precio_venta, costo_total, utilidad_neta, fecha_venta))


def orden_ya_procesada(order_id_woo: int) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM ventas_procesadas WHERE order_id_woo = ? LIMIT 1",
            (order_id_woo,)
        ).fetchone()
        return row is not None


def listar_ventas() -> list:
    sql = """
        SELECT
            vp.fecha_venta,
            vp.order_id_woo,
            vp.product_id,
            li.sku,
            vp.cantidad_vendida,
            vp.precio_venta_unitario,
            ROUND(vp.costo_total_lote / vp.cantidad_vendida, 2) AS costo_unitario,
            vp.utilidad_neta
        FROM ventas_procesadas vp
        LEFT JOIN lotes_inventario li
            ON li.product_id = vp.product_id
        GROUP BY vp.id_venta_local
        ORDER BY vp.fecha_venta DESC
    """
    with get_connection() as conn:
        return conn.execute(sql).fetchall()


def analisis_por_producto(desde_fecha: str = None, hasta_fecha: str = None) -> list:
    """
    Agrega ventas_procesadas por producto para el análisis de rentabilidad.

    Retorna una fila por product_id con:
    - total_vendidos, primera_venta, ultima_venta
    - precio_venta_prom (promedio ponderado por unidades)
    - costo_unit_prom   (costo FIFO promedio ponderado)
    - utilidad_total    (suma de utilidad_neta)
    - stock_local       (unidades actuales en lotes_inventario)
    - sku               (del último lote registrado)
    """
    condiciones = []
    params = []
    if desde_fecha:
        condiciones.append("vp.fecha_venta >= ?")
        params.append(desde_fecha)
    if hasta_fecha:
        condiciones.append("vp.fecha_venta <= ?")
        params.append(hasta_fecha)
    where = ("WHERE " + " AND ".join(condiciones)) if condiciones else ""

    sql = f"""
        SELECT
            vp.product_id,
            MAX(li.sku)                                                       AS sku,
            SUM(vp.cantidad_vendida)                                          AS total_vendidos,
            MIN(vp.fecha_venta)                                               AS primera_venta,
            MAX(vp.fecha_venta)                                               AS ultima_venta,
            ROUND(
                SUM(vp.precio_venta_unitario * vp.cantidad_vendida) /
                SUM(vp.cantidad_vendida), 2)                                  AS precio_venta_prom,
            ROUND(
                SUM(vp.costo_total_lote) /
                NULLIF(SUM(vp.cantidad_vendida), 0), 2)                       AS costo_unit_prom,
            SUM(vp.utilidad_neta)                                             AS utilidad_total,
            (
                SELECT COALESCE(SUM(li2.cantidad_actual), 0)
                FROM lotes_inventario li2
                WHERE li2.product_id = vp.product_id
            )                                                                 AS stock_local
        FROM ventas_procesadas vp
        LEFT JOIN lotes_inventario li ON li.product_id = vp.product_id
        {where}
        GROUP BY vp.product_id
        ORDER BY utilidad_total DESC
    """
    with get_connection() as conn:
        return conn.execute(sql, params).fetchall()


def stock_local_por_producto() -> dict:
    """
    Devuelve {product_id: cantidad_actual_total} sumando todos los lotes activos.
    Usado para detectar stock huérfano (WooCommerce > local FIFO).
    """
    sql = """
        SELECT product_id, COALESCE(SUM(cantidad_actual), 0) AS total
        FROM lotes_inventario
        GROUP BY product_id
    """
    with get_connection() as conn:
        rows = conn.execute(sql).fetchall()
    return {row["product_id"]: int(row["total"]) for row in rows}


# ── Funciones de resumen para la página de Inicio ─────────────────────────────────

def resumen_home() -> dict:
    with get_connection() as conn:
        r = {}
        r["n_ocs"] = conn.execute(
            "SELECT COUNT(*) AS n FROM ordenes_compra").fetchone()["n"]
        r["n_ordenes_woo"] = conn.execute(
            "SELECT COUNT(DISTINCT order_id_woo) AS n FROM ventas_procesadas").fetchone()["n"]
        r["utilidad_total"] = float(conn.execute(
            "SELECT COALESCE(SUM(utilidad_neta),0) AS t FROM ventas_procesadas").fetchone()["t"])
        r["valor_stock"] = float(conn.execute(
            "SELECT COALESCE(SUM(cantidad_actual*precio_compra_unitario),0) AS t "
            "FROM lotes_inventario").fetchone()["t"])
        r["n_lotes_activos"] = conn.execute(
            "SELECT COUNT(*) AS n FROM lotes_inventario WHERE cantidad_actual > 0").fetchone()["n"]
        r["n_lotes_agotados"] = conn.execute(
            "SELECT COUNT(*) AS n FROM lotes_inventario WHERE cantidad_actual = 0").fetchone()["n"]
        r["n_lotes_bajo"] = conn.execute(
            "SELECT COUNT(*) AS n FROM lotes_inventario WHERE cantidad_actual > 0 AND cantidad_actual <= 3").fetchone()["n"]
    return r


def ventas_por_mes() -> list:
    sql = """
        SELECT
            strftime('%Y-%m', fecha_venta) AS mes,
            ROUND(SUM(utilidad_neta), 2)   AS utilidad,
            SUM(cantidad_vendida)           AS unidades
        FROM ventas_procesadas
        GROUP BY mes
        ORDER BY mes
    """
    with get_connection() as conn:
        return conn.execute(sql).fetchall()


def top_productos_utilidad(limit: int = 8) -> list:
    sql = """
        SELECT
            vp.product_id,
            MAX(li.sku)                     AS sku,
            ROUND(SUM(vp.utilidad_neta), 2) AS utilidad_total,
            SUM(vp.cantidad_vendida)         AS unidades
        FROM ventas_procesadas vp
        LEFT JOIN lotes_inventario li ON li.product_id = vp.product_id
        GROUP BY vp.product_id
        ORDER BY utilidad_total DESC
        LIMIT ?
    """
    with get_connection() as conn:
        return conn.execute(sql, (limit,)).fetchall()


def ultimas_ocs(limit: int = 5) -> list:
    sql = """
        SELECT
            oc.id_oc,
            oc.proveedor,
            oc.fecha_ingreso,
            COUNT(li.id_lote)                                                   AS n_productos,
            COALESCE(SUM(li.cantidad_inicial), 0)                               AS unidades_total,
            ROUND(COALESCE(SUM(li.cantidad_inicial * li.precio_compra_unitario), 0), 2) AS valor_oc
        FROM ordenes_compra oc
        LEFT JOIN lotes_inventario li ON li.id_oc = oc.id_oc
        GROUP BY oc.id_oc
        ORDER BY oc.fecha_ingreso DESC
        LIMIT ?
    """
    with get_connection() as conn:
        return conn.execute(sql, (limit,)).fetchall()
