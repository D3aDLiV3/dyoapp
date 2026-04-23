"""
fifo.py — Algoritmo FIFO para calcular utilidades al procesar ventas.
"""
from db import (
    listar_lotes_por_producto,
    descontar_lote,
    registrar_venta,
    orden_ya_procesada,
)


class SinLoteDisponibleError(Exception):
    """Se lanza cuando no hay lotes de compra registrados para un producto vendido."""


def procesar_orden_fifo(order_id_woo: int, product_id: int,
                        cantidad_vendida: int, precio_venta_unitario: float,
                        fecha_venta: str):
    """
    Aplica FIFO sobre los lotes del producto para calcular el costo real y
    registra la venta en ventas_procesadas.

    Parámetros
    ----------
    order_id_woo        : ID de la orden en WooCommerce.
    product_id          : ID del producto en WooCommerce.
    cantidad_vendida    : Unidades vendidas en esta línea de orden.
    precio_venta_unitario : Precio por unidad (del JSON de la orden).
    fecha_venta         : Fecha ISO de la orden.
    """
    lotes = listar_lotes_por_producto(product_id)

    if not lotes:
        raise SinLoteDisponibleError(
            f"Producto {product_id}: no hay lotes de compra registrados. "
            "Registra la OC antes de importar ventas."
        )

    pendiente = cantidad_vendida
    costo_total = 0.0

    for lote in lotes:
        if pendiente <= 0:
            break

        disponible = lote["cantidad_actual"]
        usar = min(disponible, pendiente)

        costo_total += usar * float(lote["precio_compra_unitario"])
        descontar_lote(lote["id_lote"], usar)
        pendiente -= usar

    if pendiente > 0:
        raise SinLoteDisponibleError(
            f"Producto {product_id}: stock en lotes insuficiente. "
            f"Faltan {pendiente} unidades en los registros de compra."
        )

    ingreso_total = cantidad_vendida * precio_venta_unitario
    utilidad_neta = ingreso_total - costo_total

    registrar_venta(
        order_id_woo=order_id_woo,
        product_id=product_id,
        cantidad_vendida=cantidad_vendida,
        precio_venta=precio_venta_unitario,
        costo_total=costo_total,
        utilidad_neta=utilidad_neta,
        fecha_venta=fecha_venta,
    )


def importar_ordenes_woo(ordenes: list) -> dict:
    """
    Procesa una lista de órdenes de WooCommerce (ya obtenidas por woo_api).
    - Omite órdenes ya procesadas (todos sus productos cuentan como procesados).
    - Si un producto en una orden no tiene OC registrada, la orden NO se marca como
      procesada para que pueda reintentarse una vez se registre la OC.
    - Productos con product_id=0 (borrados / manuales) se omiten silenciosamente.

    Devuelve un dict con listas 'procesadas', 'omitidas' y 'errores'.
    """
    resultado = {"procesadas": [], "omitidas": [], "errores": []}

    for orden in ordenes:
        order_id = orden["id"]
        fecha = orden.get("date_completed") or orden.get("date_created", "")

        if orden_ya_procesada(order_id):
            resultado["omitidas"].append(order_id)
            continue

        orden_con_error = False
        for item in orden.get("line_items", []):
            product_id = item.get("product_id") or 0
            if product_id == 0:
                # Producto borrado / línea manual — no se puede costear, se omite
                continue
            cantidad = item.get("quantity", 0)
            precio_venta = float(item.get("price", 0))

            try:
                procesar_orden_fifo(
                    order_id_woo=order_id,
                    product_id=product_id,
                    cantidad_vendida=cantidad,
                    precio_venta_unitario=precio_venta,
                    fecha_venta=fecha,
                )
            except SinLoteDisponibleError as e:
                resultado["errores"].append({"order_id": order_id, "error": str(e)})
                orden_con_error = True
            except Exception as e:
                resultado["errores"].append({"order_id": order_id, "error": str(e)})
                orden_con_error = True

        # Solo marcar como procesada si no hubo errores reintentables
        if not orden_con_error:
            resultado["procesadas"].append(order_id)

    return resultado
