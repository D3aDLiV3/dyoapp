"""
nedb.py — Capa de acceso a datos.

Soporta SQLite (local/offline) y PostgreSQL (cloud centralizado).
Si config.json contiene 'database_url', usa PostgreSQL; si no, SQLite local.
"""
import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime as _datetime
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
        notas         TEXT,
        iva_total     DECIMAL(12,2) DEFAULT 0
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
    """CREATE TABLE IF NOT EXISTS gastos_operativos (
        id_gasto       SERIAL PRIMARY KEY,
        categoria      TEXT    NOT NULL,
        descripcion    TEXT,
        monto          DECIMAL(12,2) NOT NULL,
        fecha          DATE    NOT NULL,
        recurrente     SMALLINT NOT NULL DEFAULT 0,
        fecha_registro TIMESTAMP DEFAULT NOW()
    )""",
    """CREATE TABLE IF NOT EXISTS activos_fijos (
        id_activo         SERIAL PRIMARY KEY,
        nombre            TEXT NOT NULL,
        categoria         TEXT NOT NULL,
        costo_adquisicion DECIMAL(12,2) NOT NULL,
        valor_residual    DECIMAL(12,2) DEFAULT 0,
        fecha_adquisicion DATE,
        vida_util_anios   INTEGER NOT NULL,
        activo            SMALLINT DEFAULT 1,
        notas             TEXT,
        fecha_registro    TIMESTAMP DEFAULT NOW(),
        division          TEXT DEFAULT '',
        valor_comercial   DECIMAL(12,2) DEFAULT 0,
        fecha_ingreso     DATE,
        motivo_baja       TEXT,
        disposicion_baja  TEXT,
        fecha_baja        DATE,
        capital           TEXT DEFAULT 'SDSTI'
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
            # Migración: agregar columnas faltantes
            with conn.cursor() as cur:
                cur.execute("""
                    ALTER TABLE ordenes_compra
                    ADD COLUMN IF NOT EXISTS iva_total DECIMAL(12,2) DEFAULT 0
                """)
            with conn.cursor() as cur:
                cur.execute("""
                    ALTER TABLE ordenes_compra
                    ADD COLUMN IF NOT EXISTS costos_adicionales DECIMAL(12,2) DEFAULT 0
                """)
            with conn.cursor() as cur:
                cur.execute("""
                    ALTER TABLE ordenes_compra
                    ADD COLUMN IF NOT EXISTS desc_costos_adicionales TEXT DEFAULT ''
                """)
            with conn.cursor() as cur:
                cur.execute("""
                    ALTER TABLE lotes_inventario
                    ADD COLUMN IF NOT EXISTS nombre TEXT DEFAULT ''
                """)
            with conn.cursor() as cur:
                cur.execute("""
                    ALTER TABLE lotes_inventario
                    ADD COLUMN IF NOT EXISTS costo_adicional_unitario DECIMAL(10,2) DEFAULT 0
                """)
            # activos_fijos: columnas extendidas
            _af_migs = [
                "ALTER TABLE activos_fijos ALTER COLUMN fecha_adquisicion DROP NOT NULL",
                "ALTER TABLE activos_fijos ADD COLUMN IF NOT EXISTS division TEXT DEFAULT ''",
                "ALTER TABLE activos_fijos ADD COLUMN IF NOT EXISTS valor_comercial DECIMAL(12,2) DEFAULT 0",
                "ALTER TABLE activos_fijos ADD COLUMN IF NOT EXISTS fecha_ingreso DATE",
                "ALTER TABLE activos_fijos ADD COLUMN IF NOT EXISTS motivo_baja TEXT",
                "ALTER TABLE activos_fijos ADD COLUMN IF NOT EXISTS disposicion_baja TEXT",
                "ALTER TABLE activos_fijos ADD COLUMN IF NOT EXISTS fecha_baja DATE",
                "ALTER TABLE activos_fijos ADD COLUMN IF NOT EXISTS capital TEXT DEFAULT 'SDSTI'",
            ]
            for _sql_m in _af_migs:
                try:
                    with conn.cursor() as cur:
                        cur.execute(_sql_m)
                except Exception:
                    pass
    else:
        schema = SCHEMA_PATH.read_text(encoding="utf-8")
        with _conn() as conn:
            conn.executescript(schema)
            # Migración: agregar columnas faltantes
            cols = [r[1] for r in conn.execute("PRAGMA table_info(ordenes_compra)").fetchall()]
            if "iva_total" not in cols:
                conn.execute("ALTER TABLE ordenes_compra ADD COLUMN iva_total DECIMAL(12,2) DEFAULT 0")
            if "costos_adicionales" not in cols:
                conn.execute("ALTER TABLE ordenes_compra ADD COLUMN costos_adicionales DECIMAL(12,2) DEFAULT 0")
            if "desc_costos_adicionales" not in cols:
                conn.execute("ALTER TABLE ordenes_compra ADD COLUMN desc_costos_adicionales TEXT DEFAULT ''")
            cols_lotes = [r[1] for r in conn.execute("PRAGMA table_info(lotes_inventario)").fetchall()]
            if "nombre" not in cols_lotes:
                conn.execute("ALTER TABLE lotes_inventario ADD COLUMN nombre TEXT DEFAULT ''")
            if "costo_adicional_unitario" not in cols_lotes:
                conn.execute("ALTER TABLE lotes_inventario ADD COLUMN costo_adicional_unitario DECIMAL(10,2) DEFAULT 0")
            cols_af = [r[1] for r in conn.execute("PRAGMA table_info(activos_fijos)").fetchall()]
            if "division" not in cols_af:
                conn.execute("ALTER TABLE activos_fijos ADD COLUMN division TEXT DEFAULT ''")
            if "valor_comercial" not in cols_af:
                conn.execute("ALTER TABLE activos_fijos ADD COLUMN valor_comercial DECIMAL(12,2) DEFAULT 0")
            if "fecha_ingreso" not in cols_af:
                conn.execute("ALTER TABLE activos_fijos ADD COLUMN fecha_ingreso DATE")
            if "motivo_baja" not in cols_af:
                conn.execute("ALTER TABLE activos_fijos ADD COLUMN motivo_baja TEXT")
            if "disposicion_baja" not in cols_af:
                conn.execute("ALTER TABLE activos_fijos ADD COLUMN disposicion_baja TEXT")
            if "fecha_baja" not in cols_af:
                conn.execute("ALTER TABLE activos_fijos ADD COLUMN fecha_baja DATE")
            if "capital" not in cols_af:
                conn.execute("ALTER TABLE activos_fijos ADD COLUMN capital TEXT DEFAULT 'SDSTI'")


# ── Órdenes de Compra ─────────────────────────────────────────────────────────

def crear_orden_compra(proveedor: str, notas: str = "", iva_total: float = 0.0,
                       costos_adicionales: float = 0.0, desc_costos_adicionales: str = "") -> int:
    fecha = _datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sql = """
        INSERT INTO ordenes_compra
            (proveedor, notas, iva_total, costos_adicionales, desc_costos_adicionales, fecha_ingreso)
        VALUES (?, ?, ?, ?, ?, ?)
    """
    with _conn() as conn:
        return _insert(conn, sql, (proveedor, notas, iva_total, costos_adicionales, desc_costos_adicionales, fecha), "id_oc")


def eliminar_orden_compra(id_oc: int):
    """Elimina una OC y todos sus lotes. No toca ventas_procesadas."""
    with _conn() as conn:
        _exec(conn, "DELETE FROM lotes_inventario WHERE id_oc = ?", (id_oc,))
        _exec(conn, "DELETE FROM ordenes_compra WHERE id_oc = ?", (id_oc,))


def listar_ordenes_compra() -> list:
    with _conn() as conn:
        return _rows(conn, "SELECT * FROM ordenes_compra ORDER BY fecha_ingreso DESC")


# ── Lotes de Inventario (FIFO) ────────────────────────────────────────────────

def crear_lote(id_oc: int, product_id: int, sku: str,
               cantidad: int, precio_compra: float, nombre: str = "",
               costo_adicional_unitario: float = 0.0) -> int:
    sql = """
        INSERT INTO lotes_inventario
            (id_oc, product_id, sku, nombre, cantidad_inicial, cantidad_actual,
             precio_compra_unitario, costo_adicional_unitario)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """
    with _conn() as conn:
        return _insert(conn, sql,
                       (id_oc, product_id, sku, nombre, cantidad, cantidad,
                        precio_compra, costo_adicional_unitario),
                       "id_lote")


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
        SELECT product_id, sku, nombre, cantidad_inicial, cantidad_actual,
               precio_compra_unitario, costo_adicional_unitario
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
    """Stock restante por producto = OC inicial - ventas importadas (FIFO)."""
    sql = """
        SELECT product_id, COALESCE(SUM(cantidad_actual), 0) AS total
        FROM lotes_inventario
        GROUP BY product_id
    """
    with _conn() as conn:
        rows = _rows(conn, sql)
    return {row["product_id"]: int(row["total"]) for row in rows}


def stock_oc_inicial_por_producto() -> dict:
    """Total de unidades ingresadas al sistema mediante OCs (sin descontar ventas)."""
    sql = """
        SELECT product_id, COALESCE(SUM(cantidad_inicial), 0) AS total
        FROM lotes_inventario
        GROUP BY product_id
    """
    with _conn() as conn:
        rows = _rows(conn, sql)
    return {row["product_id"]: int(row["total"]) for row in rows}


def ventas_totales_por_producto() -> dict:
    """Total de unidades vendidas e importadas al sistema por producto."""
    sql = """
        SELECT product_id, COALESCE(SUM(cantidad_vendida), 0) AS total
        FROM ventas_procesadas
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

    import datetime as _dt
    hoy = _dt.date.today()
    r["gastos_mes"] = total_gastos_mes(hoy.year, hoy.month)
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


# ── Gastos Operativos ────────────────────────────────────────────────────────
CATEGORIAS_GASTO = ["Salario", "Arriendo", "Servicios públicos", "Transporte", "Publicidad", "Otro"]

# Categorías de activos fijos → vida útil estándar en años (Colombia)
CATEGORIAS_ACTIVO = {
    "Equipos de computo":    5,
    "Accesorios de computo": 5,
    "Perifericos":           5,
    "Sistemas de seguridad": 5,
    "Cámaras/Seguridad":     5,
    "Vehículos/Motos":       5,
    "Audiovisuales":        10,
    "Herramientas":         10,
    "Infraestructura":      10,
    "Maquinaria/Equipos":   10,
    "Oficina":              10,
    "Muebles/Vitrinas":     10,
    "Consumibles":           2,
    "Otro":                  5,
}

DIVISIONES_ACTIVO = [
    "Administrativa", "Multimedia", "Soporte tecnico",
    "Desarrollo", "Cyberseguridad", "Operatividad", "",
]

CAPITALES_ACTIVO = ["SDSTI", "DYO", "Compartido"]


def registrar_gasto(categoria: str, descripcion: str, monto: float,
                    fecha: str, recurrente: bool = False) -> int:
    fecha_reg = _datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sql = """
        INSERT INTO gastos_operativos (categoria, descripcion, monto, fecha, recurrente, fecha_registro)
        VALUES (?, ?, ?, ?, ?, ?)
    """
    with _conn() as conn:
        return _insert(conn, sql,
                       (categoria, descripcion, monto, fecha, 1 if recurrente else 0, fecha_reg),
                       "id_gasto")


def listar_gastos(desde: str = None, hasta: str = None) -> list:
    conds, params = [], []
    if desde:
        conds.append("fecha >= ?")
        params.append(desde)
    if hasta:
        conds.append("fecha <= ?")
        params.append(hasta)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    sql = f"""
        SELECT id_gasto, categoria, descripcion, monto, fecha, recurrente
        FROM gastos_operativos
        {where}
        ORDER BY fecha DESC, id_gasto DESC
    """
    with _conn() as conn:
        return _rows(conn, sql, tuple(params))


def eliminar_gasto(id_gasto: int):
    with _conn() as conn:
        _exec(conn, "DELETE FROM gastos_operativos WHERE id_gasto = ?", (id_gasto,))


def gastos_por_mes() -> list:
    sql = """
        SELECT
            strftime('%Y-%m', fecha) AS mes,
            ROUND(SUM(monto), 2)     AS total_gastos
        FROM gastos_operativos
        GROUP BY mes
        ORDER BY mes
    """
    with _conn() as conn:
        return _rows(conn, sql)


def gastos_por_categoria(desde: str = None, hasta: str = None) -> list:
    conds, params = [], []
    if desde:
        conds.append("fecha >= ?")
        params.append(desde)
    if hasta:
        conds.append("fecha <= ?")
        params.append(hasta)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    sql = f"""
        SELECT categoria, ROUND(SUM(monto), 2) AS total
        FROM gastos_operativos
        {where}
        GROUP BY categoria
        ORDER BY total DESC
    """
    with _conn() as conn:
        return _rows(conn, sql, tuple(params))


def total_gastos_mes(anio: int, mes: int) -> float:
    prefijo = f"{anio:04d}-{mes:02d}"
    sql = """
        SELECT COALESCE(SUM(monto), 0) AS total
        FROM gastos_operativos
        WHERE strftime('%Y-%m', fecha) = ?
    """
    with _conn() as conn:
        row = _row(conn, sql, (prefijo,))
    return float(row["total"])


def patrimonio_inventario() -> list:
    """Retorna el valor en inventario por producto (stock actual × costo FIFO ponderado)."""
    sql = """
        SELECT
            li.product_id,
            MAX(li.sku)                                                        AS sku,
            COALESCE(SUM(li.cantidad_actual), 0)                               AS stock_actual,
            ROUND(
                CASE WHEN SUM(li.cantidad_actual) > 0
                     THEN SUM(li.cantidad_actual * li.precio_compra_unitario)
                          / SUM(li.cantidad_actual)
                     ELSE 0
                END, 2)                                                        AS costo_prom,
            ROUND(
                COALESCE(SUM(li.cantidad_actual * li.precio_compra_unitario), 0)
            , 2)                                                               AS valor_inventario
        FROM lotes_inventario li
        GROUP BY li.product_id
        HAVING COALESCE(SUM(li.cantidad_actual), 0) > 0
        ORDER BY valor_inventario DESC
    """
    with _conn() as conn:
        return _rows(conn, sql)


# ── Activos Fijos ────────────────────────────────────────────────────────────

def registrar_activo(nombre: str, categoria: str, costo: float, valor_residual: float,
                     fecha_adquisicion: str, vida_util_anios: int, notas: str = "",
                     division: str = "", valor_comercial: float = 0.0,
                     fecha_ingreso: str = None, capital: str = "SDSTI") -> int:
    fecha_reg = _datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sql = """
        INSERT INTO activos_fijos
            (nombre, categoria, division, capital, costo_adquisicion, valor_residual,
             valor_comercial, fecha_adquisicion, vida_util_anios, activo,
             notas, fecha_registro, fecha_ingreso)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
    """
    with _conn() as conn:
        return _insert(conn, sql,
                       (nombre, categoria, division or "", capital or "SDSTI",
                        costo, valor_residual, valor_comercial or 0.0,
                        fecha_adquisicion, vida_util_anios,
                        notas or None, fecha_reg, fecha_ingreso or None),
                       "id_activo")


def actualizar_activo(id_activo: int, nombre: str, categoria: str, division: str,
                      costo: float, valor_residual: float, valor_comercial: float,
                      fecha_adquisicion: str, fecha_ingreso: str,
                      vida_util_anios: int, notas: str = "", capital: str = "SDSTI"):
    sql = """
        UPDATE activos_fijos SET
            nombre=?, categoria=?, division=?, capital=?,
            costo_adquisicion=?, valor_residual=?, valor_comercial=?,
            fecha_adquisicion=?, fecha_ingreso=?, vida_util_anios=?, notas=?
        WHERE id_activo=?
    """
    with _conn() as conn:
        _exec(conn, sql, (nombre, categoria, division or "", capital or "SDSTI",
                          costo, valor_residual, valor_comercial or 0.0,
                          fecha_adquisicion or None, fecha_ingreso or None,
                          vida_util_anios, notas or None, id_activo))


def listar_activos(solo_activos: bool = False) -> list:
    where = "WHERE activo = 1" if solo_activos else ""
    sql = f"""
        SELECT id_activo, nombre, categoria, division, capital, costo_adquisicion,
               valor_residual, valor_comercial, fecha_adquisicion, fecha_ingreso,
               vida_util_anios, activo, notas, motivo_baja, disposicion_baja, fecha_baja
        FROM activos_fijos
        {where}
        ORDER BY id_activo DESC
    """
    with _conn() as conn:
        return _rows(conn, sql)


def dar_baja_activo(id_activo: int, motivo: str = "", disposicion: str = "",
                    fecha_baja: str = None):
    fecha = fecha_baja or _datetime.now().strftime("%Y-%m-%d")
    sql = """
        UPDATE activos_fijos
        SET activo=0, motivo_baja=?, disposicion_baja=?, fecha_baja=?
        WHERE id_activo=?
    """
    with _conn() as conn:
        _exec(conn, sql, (motivo or None, disposicion or None, fecha, id_activo))


def eliminar_activo(id_activo: int):
    with _conn() as conn:
        _exec(conn, "DELETE FROM activos_fijos WHERE id_activo = ?", (id_activo,))


def importar_activos_iniciales() -> int:
    """Inserta el inventario inicial de activos. Solo corre si la tabla está vacía."""
    if listar_activos(solo_activos=False):
        return 0
    # (nombre, division, categoria, costo, valor_comercial, fecha_adq, fecha_ingreso)
    _INV = [
        ("Soporte para pantalla y portatil", "Administrativa", "Accesorios de computo", 303000, 349000, "2023-11-29", "2023-11-29"),
        ("Audifonos Razer Barracuda", "Administrativa", "Perifericos", 900000, 900000, "2023-11-02", "2023-12-02"),
        ("Estabilizador Gimbal", "Multimedia", "Audiovisuales", 371000, 349000, "2023-12-09", "2023-12-05"),
        ("Mouse Razer Naga", "Administrativa", "Perifericos", 537000, 0, "2024-01-05", None),
        ("Taladro inalambrico", "Soporte tecnico", "Herramientas", 258900, 0, "2024-01-13", None),
        ("Sensor de puerta", "Cyberseguridad", "Sistemas de seguridad", 40000, 0, None, None),
        ("Regleta multitoma 2 metros 6 tomas polo a tierra", "Administrativa", "Infraestructura", 40000, 0, "2024-03-03", "2024-03-03"),
        ("Regleta multitoma 2 metros 6 tomas polo a tierra", "Administrativa", "Infraestructura", 40000, 0, "2024-03-04", "2024-03-03"),
        ("Regleta multitoma 2 metros 6 tomas polo a tierra", "Administrativa", "Infraestructura", 40000, 0, "2024-03-05", "2024-03-03"),
        ("Computador All In One Lenovo", "Desarrollo", "Equipos de computo", 1700000, 0, None, None),
        ('Monitor Xiaomi de 27"', "Multimedia", "Accesorios de computo", 600000, 1100000, None, None),
        ("Monitor Samsung de 27", "Desarrollo", "Accesorios de computo", 847000, 700000, None, None),
        ('Monitor AOC de 27"', "Administrativa", "Accesorios de computo", 500000, 0, None, None),
        ('Monitor HP Compaq LE1711 de 17"', "Soporte tecnico", "Accesorios de computo", 150000, 0, None, None),
        ("Teclado KOORUI", "Desarrollo", "Perifericos", 120000, 0, None, None),
        ("Teclado HYEKU", "Multimedia", "Perifericos", 130000, 0, None, None),
        ("Teclado DRACONIC K530RGB", "Desarrollo", "Perifericos", 350000, 0, None, None),
        ("Audifonos MPOW", "Desarrollo", "Perifericos", 160000, 0, None, None),
        ("Tableta de diseno grafico", "Multimedia", "Audiovisuales", 300000, 0, None, None),
        ("Mouse RAPOO VT900", "Multimedia", "Perifericos", 120000, 0, None, None),
        ("Mouse EVGA X12", "Desarrollo", "Perifericos", 80000, 0, None, None),
        ("Mouse Genius Ergo 8250S", "Multimedia", "Perifericos", 76000, 0, "2024-07-02", "2025-01-24"),
        ("Adaptador/Extensor USB tipo C", "Multimedia", "Accesorios de computo", 120000, 0, None, None),
        ("Escritorio en L Moscu Wengue", "Soporte tecnico", "Oficina", 379000, 0, "2024-03-03", None),
        ("Escritorio Rod Wengue", "Multimedia", "Oficina", 250900, 0, "2023-09-23", None),
        ("Escritorio Rod Wengue", "Desarrollo", "Oficina", 250900, 0, "2023-09-23", None),
        ("Estacion para clonar discos wavlink", "Soporte tecnico", "Herramientas", 250000, 0, None, None),
        ("Juego de destornillador con puntas STREBITO", "Soporte tecnico", "Herramientas", 30000, 0, None, None),
        ("Cafetera KALLEY", "Administrativa", "Oficina", 50000, 0, None, None),
        ("Nevera KALLEY", "Administrativa", "Oficina", 300000, 0, None, None),
        ("Impresora EPSON", "Administrativa", "Oficina", 400000, 0, None, None),
        ("Regleta metalica supresor de picos", "Soporte tecnico", "Infraestructura", 117000, 0, "2024-07-02", "2024-07-02"),
        ("Alfombrilla RGB 90cmx40cm", "Administrativa", "Accesorios de computo", 120000, 0, None, None),
        ("Alfombrilla RGB 80cmx30cm", "Desarrollo", "Accesorios de computo", 120000, 0, None, None),
        ("Reflector difusor profesional flex 110CM", "Multimedia", "Audiovisuales", 84000, 0, "2024-12-12", "2024-12-12"),
        ("Torre servidor", "Soporte tecnico", "Equipos de computo", 500000, 0, None, None),
        ("Computador portatil MAC", "Multimedia", "Equipos de computo", 3000000, 0, None, None),
        ("Silla de Oficina", "Multimedia", "Oficina", 300000, 0, None, None),
        ("Silla de Oficina", "Soporte tecnico", "Oficina", 300000, 0, None, None),
        ("Silla de Oficina", "Desarrollo", "Oficina", 300000, 0, None, None),
        ("Silla de Oficina silleti", "Administrativa", "Oficina", 365000, 0, "2025-03-05", "2025-02-28"),
        ("Portatil lenovo", "Administrativa", "Equipos de computo", 3800000, 0, None, None),
        ("Memoria microSD", "Cyberseguridad", "Sistemas de seguridad", 35000, 0, None, None),
        ("Ventilador Samurai Air Power Pedestal", "Desarrollo", "Oficina", 119000, 0, "2024-07-02", "2024-07-02"),
        ("Ventilador Samurai", "Administrativa", "Oficina", 180000, 0, None, None),
        ("Destornillador redflag", "Soporte tecnico", "Herramientas", 0, 0, None, None),
        ("Destornillador FULCOR", "Soporte tecnico", "Herramientas", 0, 0, None, None),
        ("Radio baofeng + Base de carga", "Soporte tecnico", "Herramientas", 110000, 0, None, None),
        ("Teclado Numerico inalambrico", "Administrativa", "Accesorios de computo", 42000, 0, "2025-01-29", "2025-01-29"),
        ("Cinta Aislante", "Soporte tecnico", "Consumibles", 0, 0, None, None),
        ("Morral laverock", "Soporte tecnico", "Consumibles", 200000, 0, None, None),
        ("Cinta doble faz silicona Acrilico", "Soporte tecnico", "Consumibles", 28000, 0, "2025-01-25", "2025-01-23"),
        ("Kit de Alcohol isopropilico", "Soporte tecnico", "Herramientas", 48000, 0, None, "2025-01-23"),
        ("Camara imou ranger 3MP", "Cyberseguridad", "Sistemas de seguridad", 130000, 0, "2025-02-07", "2025-02-07"),
        ("Kit de iluminacion octabox Godox 80Cm", "Multimedia", "Audiovisuales", 198000, 0, "2025-02-26", "2025-02-26"),
        ("Flash Godox tt600s", "Multimedia", "Audiovisuales", 500000, 0, "2025-02-26", "2025-02-26"),
        ("Morral de fotografia", "Multimedia", "Audiovisuales", 160000, 0, None, None),
        ("Disparador Godox TTL", "Multimedia", "Audiovisuales", 350000, 0, None, None),
        ("Canastas para almacenamiento", "Soporte tecnico", "Oficina", 30000, 0, None, None),
        ("Canastas para almacenamiento", "Soporte tecnico", "Oficina", 30000, 0, None, None),
        ("Canastas para almacenamiento", "Soporte tecnico", "Oficina", 30000, 0, None, None),
        ("Sonda electrica", "Soporte tecnico", "Herramientas", 0, 0, None, None),
        ("Sonda electrica dielectrica", "Soporte tecnico", "Herramientas", 0, 0, None, None),
        ("Probador LAN", "Soporte tecnico", "Herramientas", 0, 0, None, None),
        ("Ponchadora", "Soporte tecnico", "Herramientas", 0, 0, None, None),
        ("Resina Epoxica", "Soporte tecnico", "Consumibles", 0, 0, None, None),
        ("Cable UTP para conexion LAN", "Operatividad", "Infraestructura", 20000, 0, None, None),
        ("Cable UTP para conexion LAN", "Operatividad", "Infraestructura", 0, 0, None, None),
        ("Cable UTP para conexion LAN", "Operatividad", "Infraestructura", 0, 0, None, None),
        ("Cable UTP para conexion LAN", "Operatividad", "Infraestructura", 0, 0, None, None),
        ("Cable UTP para conexion LAN", "Operatividad", "Consumibles", 0, 0, None, None),
        ("Cable UTP para conexion LAN", "Operatividad", "Consumibles", 0, 0, None, None),
        ("Cable UTP para conexion LAN", "Operatividad", "Consumibles", 0, 0, None, None),
        ("Cable UTP para conexion LAN", "Operatividad", "Consumibles", 0, 0, None, None),
        ("Pistola de calor SEEKONE HG350", "", "Herramientas", 0, 0, None, None),
        ("Limpiador electronico Isocore SK085", "", "Herramientas", 0, 0, None, None),
        ("Cautin", "", "Herramientas", 0, 0, None, None),
        ("Sopladora de aire AIR DUSTER VC016", "", "Herramientas", 0, 0, None, None),
        ("Atomizador con limpiador Isocore SK085", "", "Herramientas", 0, 0, None, None),
        ("Atomizador con limpiador Isocore SK085", "", "Herramientas", 0, 0, None, None),
        ("Kit de destornillador JL-1161", "", "Herramientas", 11000, 0, None, None),
        ("Atomizador", "Operatividad", "Otro", 0, 0, None, None),
        ("Atomizador", "Operatividad", "Otro", 0, 0, None, None),
        ("Atomizador", "Operatividad", "Otro", 0, 0, None, None),
        ("Atomizador", "Operatividad", "Otro", 0, 0, None, None),
        ("Atomizador", "Operatividad", "Otro", 0, 0, None, None),
        ("Audifonos Razer Barracuda", "Administrativa", "Perifericos", 550000, 900000, None, None),
        ("Alfombrilla anti estatica con manilla", "Soporte tecnico", "Herramientas", 0, 0, None, None),
        ("Lupa, lampara y base de soporte", "Soporte tecnico", "Herramientas", 0, 0, None, None),
        ("Soporte para tanque de agua", "", "Otro", 0, 0, None, None),
        ("Estante de 3 niveles", "", "Otro", 0, 0, None, None),
        ("Escritorio", "", "Otro", 0, 0, None, None),
        ("Dook encluster M2 a M2", "", "Otro", 235000, 0, None, "2025-09-30"),
        ("Dook Encluster M2 NVME a SATA, M2 SATA a SATA", "Soporte tecnico", "Otro", 225000, 0, None, "2025-09-30"),
        ("Papelera grande negra", "Operatividad", "Otro", 34000, 0, None, "2025-11-17"),
        ("Portatil Acer Spin", "", "Equipos de computo", 2500000, 0, None, None),
        ("Caja monedero", "", "Otro", 120000, 0, None, None),
        ("Impresora termica", "", "Otro", 145000, 0, None, None),
        ("Sistema de seguridad AX Home", "", "Sistemas de seguridad", 800000, 0, None, None),
        ("Imou Triple", "", "Sistemas de seguridad", 480000, 0, None, None),
    ]
    fecha_reg = _datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sql = """
        INSERT INTO activos_fijos
            (nombre, division, capital, categoria, costo_adquisicion, valor_comercial,
             valor_residual, fecha_adquisicion, vida_util_anios, activo,
             fecha_registro, fecha_ingreso)
        VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, 1, ?, ?)
    """
    count = 0
    with _conn() as conn:
        for row in _INV:
            nombre, div, cat, costo, vc, fecha_adq, fecha_ing = row
            vida = CATEGORIAS_ACTIVO.get(cat, 5)
            _exec(conn, sql, (nombre, div, "SDSTI", cat, float(costo), float(vc),
                              fecha_adq, vida, fecha_reg, fecha_ing))
            count += 1
    return count
