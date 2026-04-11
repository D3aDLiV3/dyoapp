"""
migrate_to_postgres.py — Migra datos desde SQLite local a PostgreSQL.

Uso:
    python migrate_to_postgres.py

Requiere que config.json tenga 'database_url' configurado.
Lee todos los datos de wooposadmin.db y los inserta en PostgreSQL.
Es SEGURO correrlo más de una vez: detecta registros existentes (por ID) y
los omite para no duplicar.
"""
import json
import sqlite3
import sys
from pathlib import Path

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("ERROR: Instala psycopg2-binary primero: pip install psycopg2-binary")
    sys.exit(1)

CONFIG_PATH = Path(__file__).parent / "config.json"
DB_PATH     = Path(__file__).parent / "wooposadmin.db"


def main():
    print("=== Migrar SQLite → PostgreSQL ===\n")

    if not CONFIG_PATH.exists():
        print("ERROR: config.json no encontrado.")
        sys.exit(1)

    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    database_url = cfg.get("database_url", "").strip()
    if not database_url:
        print("ERROR: 'database_url' no está en config.json.")
        print("Agrégalo así:")
        print('  "database_url": "postgresql://usuario:contraseña@host:5432/wooposadmin"')
        sys.exit(1)

    if not DB_PATH.exists():
        print(f"ERROR: No se encontró la base SQLite en {DB_PATH}")
        sys.exit(1)

    # Conectar SQLite
    sqlite_conn = sqlite3.connect(str(DB_PATH))
    sqlite_conn.row_factory = sqlite3.Row

    # Conectar PostgreSQL
    try:
        pg_conn = psycopg2.connect(database_url)
    except Exception as e:
        print(f"ERROR al conectar a PostgreSQL: {e}")
        sys.exit(1)

    pg_conn.autocommit = False
    cur = pg_conn.cursor()

    try:
        # ── Crear tablas si no existen ────────────────────────────────────────
        cur.execute("""
            CREATE TABLE IF NOT EXISTS ordenes_compra (
                id_oc         SERIAL PRIMARY KEY,
                proveedor     TEXT,
                fecha_ingreso TIMESTAMP DEFAULT NOW(),
                notas         TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS lotes_inventario (
                id_lote                SERIAL PRIMARY KEY,
                id_oc                  INTEGER REFERENCES ordenes_compra(id_oc),
                product_id             INTEGER,
                sku                    TEXT,
                cantidad_inicial       INTEGER,
                cantidad_actual        INTEGER,
                precio_compra_unitario DECIMAL(10,2)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS ventas_procesadas (
                id_venta_local        SERIAL PRIMARY KEY,
                order_id_woo          INTEGER,
                product_id            INTEGER,
                cantidad_vendida      INTEGER,
                precio_venta_unitario DECIMAL(10,2),
                costo_total_lote      DECIMAL(10,2),
                utilidad_neta         DECIMAL(10,2),
                fecha_venta           TIMESTAMP
            )
        """)
        pg_conn.commit()

        # ── Migrar ordenes_compra ─────────────────────────────────────────────
        ocs = sqlite_conn.execute("SELECT * FROM ordenes_compra ORDER BY id_oc").fetchall()
        cur.execute("SELECT id_oc FROM ordenes_compra")
        existing_ocs = {r[0] for r in cur.fetchall()}
        oc_nuevas = 0
        for row in ocs:
            if row["id_oc"] in existing_ocs:
                continue
            cur.execute(
                "INSERT INTO ordenes_compra (id_oc, proveedor, fecha_ingreso, notas) "
                "VALUES (%s, %s, %s, %s)",
                (row["id_oc"], row["proveedor"], row["fecha_ingreso"], row["notas"]),
            )
            oc_nuevas += 1
        # Sincronizar secuencia SERIAL
        if ocs:
            cur.execute("SELECT setval('ordenes_compra_id_oc_seq', (SELECT MAX(id_oc) FROM ordenes_compra))")
        pg_conn.commit()
        print(f"  ordenes_compra:     {oc_nuevas} nuevas  (omitidas: {len(existing_ocs)})")

        # ── Migrar lotes_inventario ───────────────────────────────────────────
        lotes = sqlite_conn.execute("SELECT * FROM lotes_inventario ORDER BY id_lote").fetchall()
        cur.execute("SELECT id_lote FROM lotes_inventario")
        existing_lotes = {r[0] for r in cur.fetchall()}
        lotes_nuevos = 0
        for row in lotes:
            if row["id_lote"] in existing_lotes:
                continue
            cur.execute(
                "INSERT INTO lotes_inventario "
                "(id_lote, id_oc, product_id, sku, cantidad_inicial, cantidad_actual, precio_compra_unitario) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (row["id_lote"], row["id_oc"], row["product_id"], row["sku"],
                 row["cantidad_inicial"], row["cantidad_actual"], row["precio_compra_unitario"]),
            )
            lotes_nuevos += 1
        if lotes:
            cur.execute("SELECT setval('lotes_inventario_id_lote_seq', (SELECT MAX(id_lote) FROM lotes_inventario))")
        pg_conn.commit()
        print(f"  lotes_inventario:   {lotes_nuevos} nuevos  (omitidos: {len(existing_lotes)})")

        # ── Migrar ventas_procesadas ──────────────────────────────────────────
        ventas = sqlite_conn.execute("SELECT * FROM ventas_procesadas ORDER BY id_venta_local").fetchall()
        cur.execute("SELECT id_venta_local FROM ventas_procesadas")
        existing_v = {r[0] for r in cur.fetchall()}
        ventas_nuevas = 0
        for row in ventas:
            if row["id_venta_local"] in existing_v:
                continue
            cur.execute(
                "INSERT INTO ventas_procesadas "
                "(id_venta_local, order_id_woo, product_id, cantidad_vendida, "
                "precio_venta_unitario, costo_total_lote, utilidad_neta, fecha_venta) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (row["id_venta_local"], row["order_id_woo"], row["product_id"],
                 row["cantidad_vendida"], row["precio_venta_unitario"],
                 row["costo_total_lote"], row["utilidad_neta"], row["fecha_venta"]),
            )
            ventas_nuevas += 1
        if ventas:
            cur.execute("SELECT setval('ventas_procesadas_id_venta_local_seq', (SELECT MAX(id_venta_local) FROM ventas_procesadas))")
        pg_conn.commit()
        print(f"  ventas_procesadas:  {ventas_nuevas} nuevas  (omitidas: {len(existing_v)})")

        print("\n✅ Migración completada.")

    except Exception as e:
        pg_conn.rollback()
        print(f"\nERROR durante la migración: {e}")
        raise
    finally:
        cur.close()
        pg_conn.close()
        sqlite_conn.close()


if __name__ == "__main__":
    main()
