"""
db.py — Capa de acceso a datos.

Soporta SQLite (local/offline) y PostgreSQL (cloud centralizado).
Si config.json contiene 'database_url', usa PostgreSQL; si no, SQLite local.
"""
import json
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path

try:
    import psycopg2
    import psycopg2.extras
    _HAS_PSYCOPG2 = True
except ImportError:
    _HAS_PSYCOPG2 = False

_CONFIG_PATH = Path(__file__).parent / "config.json"
_cfg: dict = (
    json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    if _CONFIG_PATH.exists() else {}
)
_DATABASE_URL: str = _cfg.get("database_url", "")
_USE_PG: bool = bool(_DATABASE_URL) and _HAS_PSYCOPG2

DB_PATH     = Path(__file__).parent / "wooposadmin.db"
SCHEMA_PATH = Path(__file__).parent / "schema_local.sql"

# ── Schema PostgreSQL ─────────────────────────────────────────────────────────
_SCHEMA_PG = [
    """CREATE TABLE IF NOT EXISTS ordenes_compra (
        id_oc         SERIAL PRIMARY KEY,
        proveedor     TEXT,
        fecha_ingreso TIMESTAMP DEFAULT NOW(),
        notas         TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS lotes_inventario (
        id_lote                SERIAL PRIMARY KEY,
        id_oc                  INTEGER REFERENCES ordenes_compra(id_oc),
        product_id             INTEGER,
        sku                    TEXT,
        cantidad_inicial       INTEGER,
        cantidad_actual        INTEGER,
        precio_compra_unitario DECIMAL(10,2)
    )""",
    """CREATE TABLE IF NOT EXISTS ventas_procesadas (
        id_venta_local        SERIAL PRIMARY KEY,
        order_id_woo          INTEGER,
        product_id            INTEGER,
        cantidad_vendida      INTEGER,
        precio_venta_unitario DECIMAL(10,2),
        costo_total_lote      DECIMAL(10,2),
        utilidad_neta         DECIMAL(10,2),
        fecha_venta           TIMESTAMP
    )""",
]

# ── Helpers internos ──────────────────────────────────────────────────────────

@contextmanager
def _conn():
    """Context manager que devuelve conexión SQLite o PostgreSQL."""
    if _USE_PG:
        c = psycopg2.connect(_DATABASE_URL)
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()
    else:
        c = sqlite3.connect(str(DB_PATH))
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys = ON")
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()


def _q(sql: str) -> str:
    """Traduce SQL SQLite → PostgreSQL (placeholders y funciones de fecha)."""
    if not _USE_PG:
        return sql
    # strftime('%Y-%m', campo) → TO_CHAR(campo, 'YYYY-MM')
    sql = re.sub(
        r"strftime\('%Y-%m',\s*([^)]+)\)",
        r"TO_CHAR(\1, 'YYYY-MM')",
        sql,
    )
    sql = sql.replace("?", "%s")
    return sql


def _rows(conn, sql: str, params=()):
    """SELECT → lista de filas dict-like."""
    if _USE_PG:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(_q(sql), params or None)
            return cur.fetchall()
    return conn.execute(sql, params).fetchall()


def _row(conn, sql: str, params=()):
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def _exec(conn, sql: str, params=()):
    """Statement sin retorno (UPDATE, DELETE, INSERT sin RETURNING)."""
    if _USE_PG:
        with conn.cursor() as cur:
            cur.execute(_q(sql), params or None)
    else:
        conn.execute(sql, params)


def _insert(conn, sql: str, params, returning: str) -> int:
    """INSERT que devuelve el ID del nuevo registro."""
    if _USE_PG:
        with conn.cursor() as cur:
            cur.execute(_q(sql) + f" RETURNING {returning}", params)
            return cur.fetchone()[0]
    cur = conn.execute(sql, params)
    return cur.lastrowid


# ── Init ──────────────────────────────────────────────────────────────────────

def init_db():
    """Crea tablas si no existen (SQLite usa schema_local.sql, PG usa DDL inline)."""
    if _USE_PG:
        with _conn() as conn:
            for stmt in _SCHEMA_PG:
                with conn.cursor() as cur:
                    cur.execute(stmt)
    else:
        schema = SCHEMA_PATH.read_text(encoding="utf-8")
        with _conn() as conn:
            conn.executescript(schema)


# ── Órdenes de Compra ─────────────────────────────────────────────────────────

def crear_orden_compra(proveedor: str, notas: str = "") -> int:
    sql = "INSERT INTO ordenes_compra (proveedor, notas) VALUES (?, ?)"
    with _conn() as conn:
        return _insert(conn, sql, (proveedor, notas), "id_oc")


def listar_ordenes_compra() -> list:
    with _conn() as conn:
        return _rows(conn, "SELECT * FROM ordenes_compra ORDER BY fecha_ingreso DESC")


# ── Lotes de Inventario (FIFO) ────────────────────────────────────────────────

def crear_lote(id_oc: int, product_id: int, sku: str,
               cantidad: int, precio_compra: float) -> int:
    sql = """
        INSERT INTO lotes_inventario
            (id_oc, product_id, sku, cantidad_inicial, cantidad_actual, precio_compra_unitario)
        VALUES (?, ?, ?, ?, ?, ?)
    """
    with _conn() as conn:
        return _insert(conn, sql, (id_oc, product_id, sku, cantidad, cantidad, precio_compra), "id_lote")


def listar_lotes_por_producto(product_id: int) -> list:
    sql = """
        SELECT * FROM lotes_inventario
        WHERE product_id = ? AND cantidad_actual > 0
        ORDER BY id_lote ASC
    """
    with _conn() as conn:
        return _rows(conn, sql, (product_id,))


def listar_lotes_por_oc(id_oc: int) -> list:
    sql = """
        SELECT product_id, sku, cantidad_inicial
        FROM lotes_inventario
        WHERE id_oc = ?
        ORDER BY id_lote ASC
    """
    with _conn() as conn:
        return _rows(conn, sql, (id_oc,))


def listar_todos_lotes() -> list:
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
    with _conn() as conn:
        return _rows(conn, sql)


def descontar_lote(id_lote: int, cantidad: int):
    sql = "UPDATE lotes_inventario SET cantidad_actual = cantidad_actual - ? WHERE id_lote = ?"
    with _conn() as conn:
        _exec(conn, sql, (cantidad, id_lote))


# ── Ventas Procesadas ─────────────────────────────────────────────────────────

def registrar_venta(order_id_woo: int, product_id: int, cantidad_vendida: int,
                    precio_venta: float, costo_total: float,
                    utilidad_neta: float, fecha_venta: str):
    sql = """
        INSERT INTO ventas_procesadas
            (order_id_woo, product_id, cantidad_vendida, precio_venta_unitario,
             costo_total_lote, utilidad_neta, fecha_venta)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """
    with _conn() as conn:
        _exec(conn, sql, (order_id_woo, product_id, cantidad_vendida,
                          precio_venta, costo_total, utilidad_neta, fecha_venta))


def orden_ya_procesada(order_id_woo: int) -> bool:
    sql = "SELECT 1 FROM ventas_procesadas WHERE order_id_woo = ? LIMIT 1"
    with _conn() as conn:
        return _row(conn, sql, (order_id_woo,)) is not None


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
        GROUP BY vp.id_venta_local, vp.fecha_venta, vp.order_id_woo, vp.product_id,
                 li.sku, vp.cantidad_vendida, vp.precio_venta_unitario,
                 vp.costo_total_lote, vp.utilidad_neta
        ORDER BY vp.fecha_venta DESC
    """
    with _conn() as conn:
        return _rows(conn, sql)


def analisis_por_producto(desde_fecha: str = None, hasta_fecha: str = None) -> list:
    condiciones, params = [], []
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
    with _conn() as conn:
        return _rows(conn, sql, tuple(params))


def stock_local_por_producto() -> dict:
    sql = """
        SELECT product_id, COALESCE(SUM(cantidad_actual), 0) AS total
        FROM lotes_inventario
        GROUP BY product_id
    """
    with _conn() as conn:
        rows = _rows(conn, sql)
    return {row["product_id"]: int(row["total"]) for row in rows}


def resumen_por_producto() -> list:
    sql = """
        SELECT
            li.product_id,
            MAX(li.sku)                                                        AS sku,
            COALESCE(SUM(li.cantidad_actual), 0)                               AS stock_actual,
            ROUND(
                CASE WHEN SUM(li.cantidad_actual) > 0
                     THEN SUM(li.cantidad_actual * li.precio_compra_unitario)
                          / SUM(li.cantidad_actual)
                     ELSE (SELECT li3.precio_compra_unitario
                           FROM lotes_inventario li3
                           WHERE li3.product_id = li.product_id
                           ORDER BY li3.id_lote DESC LIMIT 1)
                END, 2)                                                        AS precio_compra_pond,
            (SELECT li2.precio_compra_unitario
             FROM lotes_inventario li2
             WHERE li2.product_id = li.product_id
             ORDER BY li2.id_lote DESC LIMIT 1)                                AS ultimo_precio_compra,
            (SELECT MAX(oc2.fecha_ingreso)
             FROM ordenes_compra oc2
             JOIN lotes_inventario lx ON lx.id_oc = oc2.id_oc
             WHERE lx.product_id = li.product_id)                              AS ultima_compra_fecha,
            (SELECT MAX(vp.fecha_venta)
             FROM ventas_procesadas vp
             WHERE vp.product_id = li.product_id)                              AS ultima_venta_fecha,
            (SELECT vp2.precio_venta_unitario
             FROM ventas_procesadas vp2
             WHERE vp2.product_id = li.product_id
             ORDER BY vp2.fecha_venta DESC LIMIT 1)                            AS ultimo_precio_venta
        FROM lotes_inventario li
        GROUP BY li.product_id
        ORDER BY sku ASC
    """
    with _conn() as conn:
        return _rows(conn, sql)


# ── Resumen home ──────────────────────────────────────────────────────────────

def resumen_home() -> dict:
    queries = {
        "n_ocs":           "SELECT COUNT(*) AS n FROM ordenes_compra",
        "n_ordenes_woo":   "SELECT COUNT(DISTINCT order_id_woo) AS n FROM ventas_procesadas",
        "utilidad_total":  "SELECT COALESCE(SUM(utilidad_neta),0) AS t FROM ventas_procesadas",
        "valor_stock":     "SELECT COALESCE(SUM(cantidad_actual*precio_compra_unitario),0) AS t FROM lotes_inventario",
        "n_lotes_activos": "SELECT COUNT(*) AS n FROM lotes_inventario WHERE cantidad_actual > 0",
        "n_lotes_agotados":"SELECT COUNT(*) AS n FROM lotes_inventario WHERE cantidad_actual = 0",
        "n_lotes_bajo":    "SELECT COUNT(*) AS n FROM lotes_inventario WHERE cantidad_actual > 0 AND cantidad_actual <= 3",
    }
    r = {}
    with _conn() as conn:
        for key, sql in queries.items():
            row = _row(conn, sql)
            val = row["n"] if "n" in dict(row) else row["t"]
            r[key] = float(val) if key in ("utilidad_total", "valor_stock") else int(val)
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
    with _conn() as conn:
        return _rows(conn, sql)


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
    with _conn() as conn:
        return _rows(conn, sql, (limit,))


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
        GROUP BY oc.id_oc, oc.proveedor, oc.fecha_ingreso
        ORDER BY oc.fecha_ingreso DESC
        LIMIT ?
    """
    with _conn() as conn:
        return _rows(conn, sql, (limit,))
