-- Tabla para registrar cada Orden de Compra (OC)
CREATE TABLE IF NOT EXISTS ordenes_compra (
    id_oc INTEGER PRIMARY KEY AUTOINCREMENT,
    proveedor TEXT,
    fecha_ingreso DATETIME DEFAULT CURRENT_TIMESTAMP,
    notas TEXT,
    iva_total DECIMAL(12,2) DEFAULT 0
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

-- Tabla de Gastos Operativos (salarios, arriendo, servicios, etc.)
CREATE TABLE IF NOT EXISTS gastos_operativos (
    id_gasto       INTEGER PRIMARY KEY AUTOINCREMENT,
    categoria      TEXT    NOT NULL, -- Salario | Arriendo | Servicios | Transporte | Publicidad | Otro
    descripcion    TEXT,
    monto          DECIMAL(12, 2) NOT NULL,
    fecha          DATE    NOT NULL,
    recurrente     INTEGER NOT NULL DEFAULT 0, -- 0=único, 1=recurrente
    fecha_registro DATETIME DEFAULT CURRENT_TIMESTAMP
);
