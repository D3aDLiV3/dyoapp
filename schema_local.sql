-- Tabla para registrar cada Orden de Compra (OC)
CREATE TABLE IF NOT EXISTS ordenes_compra (
    id_oc INTEGER PRIMARY KEY AUTOINCREMENT,
    proveedor TEXT,
    fecha_ingreso DATETIME DEFAULT CURRENT_TIMESTAMP,
    notas TEXT
);

-- Tabla de Lotes (Lógica FIFO)
CREATE TABLE IF NOT EXISTS lotes_inventario (
    id_lote INTEGER PRIMARY KEY AUTOINCREMENT,
    id_oc INTEGER,
    product_id INTEGER, -- ID de WooCommerce
    sku TEXT,
    cantidad_inicial INTEGER,
    cantidad_actual INTEGER, -- Aquí se descuenta según se vende
    precio_compra_unitario DECIMAL(10, 2),
    FOREIGN KEY (id_oc) REFERENCES ordenes_compra(id_oc)
);

-- Tabla de Historial de Ventas Procesadas (Auditoría de Utilidad)
CREATE TABLE IF NOT EXISTS ventas_procesadas (
    id_venta_local INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id_woo INTEGER,
    product_id INTEGER,
    cantidad_vendida INTEGER,
    precio_venta_unitario DECIMAL(10, 2),
    costo_total_lote DECIMAL(10, 2), -- Suma de los costos de los lotes usados
    utilidad_neta DECIMAL(10, 2),
    fecha_venta DATETIME
);
