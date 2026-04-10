"""
app.py — Interfaz gráfica principal (CustomTkinter).
Módulos: Órdenes de Compra · Importar Ventas · Generador de Etiquetas · Dashboard
"""
import tkinter as tk
from tkinter import messagebox, filedialog
import customtkinter as ctk
import threading
import os

import db
import woo_api
import fifo
import etiquetas

# ── Tema ─────────────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


# ═════════════════════════════════════════════════════════════════════════════
#  VENTANA PRINCIPAL
# ═════════════════════════════════════════════════════════════════════════════
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Descuentos y Ofertas — Inventario FIFO")
        self.geometry("1100x700")
        self.resizable(True, True)

        # Ícono de ventana
        _ico = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo_launcher.ico")
        if os.path.isfile(_ico):
            try:
                self.iconbitmap(_ico)
            except Exception:
                pass

        db.init_db()

        # Barra lateral
        self.sidebar = ctk.CTkFrame(self, width=180, corner_radius=0)
        self.sidebar.pack(side="left", fill="y")

        ctk.CTkLabel(self.sidebar, text="Descuentos\ny Ofertas",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color="#E42127").pack(pady=12)
        ctk.CTkLabel(self.sidebar, text="Inventario FIFO",
                     font=ctk.CTkFont(size=10),
                     text_color="#F5C400").pack(pady=(0, 8))

        self.frames: dict[str, ctk.CTkFrame] = {}
        self._build_nav()

        # Contenedor principal
        self.container = ctk.CTkFrame(self, corner_radius=0)
        self.container.pack(side="left", fill="both", expand=True)

        for name, FrameClass in [
            ("oc", FrameOC),
            ("ventas", FrameVentas),
            ("etiquetas", FrameEtiquetas),
            ("dashboard", FrameDashboard),
        ]:
            frame = FrameClass(self.container, self)
            self.frames[name] = frame
            frame.place(relwidth=1, relheight=1)

        self.show_frame("oc")

    def _build_nav(self):
        botones = [
            ("📦 Orden de Compra", "oc"),
            ("🛒 Importar Ventas", "ventas"),
            ("🏷️ Etiquetas", "etiquetas"),
            ("📊 Dashboard", "dashboard"),
        ]
        for label, name in botones:
            btn = ctk.CTkButton(
                self.sidebar, text=label, anchor="w",
                command=lambda n=name: self.show_frame(n)
            )
            btn.pack(fill="x", padx=10, pady=4)

    def show_frame(self, name: str):
        self.frames[name].lift()
        if hasattr(self.frames[name], "on_show"):
            self.frames[name].on_show()


# ═════════════════════════════════════════════════════════════════════════════
#  MÓDULO: ORDEN DE COMPRA
# ═════════════════════════════════════════════════════════════════════════════
class FrameOC(ctk.CTkFrame):
    def __init__(self, parent, app: App):
        super().__init__(parent, corner_radius=0)
        self.app = app
        self._items: list[dict] = []   # líneas de la OC en curso
        self._build()

    def _build(self):
        ctk.CTkLabel(self, text="Nueva Orden de Compra",
                     font=ctk.CTkFont(size=18, weight="bold")).pack(pady=12)

        top = ctk.CTkFrame(self)
        top.pack(fill="x", padx=20)

        ctk.CTkLabel(top, text="Proveedor:").grid(row=0, column=0, sticky="w", padx=4)
        self.ent_proveedor = ctk.CTkEntry(top, width=220)
        self.ent_proveedor.grid(row=0, column=1, padx=4, pady=4)

        ctk.CTkLabel(top, text="Notas:").grid(row=0, column=2, sticky="w", padx=4)
        self.ent_notas = ctk.CTkEntry(top, width=300)
        self.ent_notas.grid(row=0, column=3, padx=4)

        # ── Agregar producto ──────────────────────────────────────────────
        mid = ctk.CTkFrame(self)
        mid.pack(fill="x", padx=20, pady=8)

        ctk.CTkLabel(mid, text="SKU / Barcode:").grid(row=0, column=0, padx=4)
        self.ent_sku = ctk.CTkEntry(mid, width=160)
        self.ent_sku.grid(row=0, column=1, padx=4)
        self.ent_sku.bind("<Return>", lambda e: self._buscar_producto())

        ctk.CTkLabel(mid, text="Cantidad:").grid(row=0, column=2, padx=4)
        self.ent_cantidad = ctk.CTkEntry(mid, width=80)
        self.ent_cantidad.grid(row=0, column=3, padx=4)

        ctk.CTkLabel(mid, text="Precio Compra:").grid(row=0, column=4, padx=4)
        self.ent_precio = ctk.CTkEntry(mid, width=100)
        self.ent_precio.grid(row=0, column=5, padx=4)

        ctk.CTkButton(mid, text="Buscar / Agregar", width=130,
                      command=self._buscar_producto).grid(row=0, column=6, padx=8)

        self.lbl_producto = ctk.CTkLabel(self, text="", text_color="cyan")
        self.lbl_producto.pack()

        # ── Tabla de ítems ────────────────────────────────────────────────
        from tkinter import ttk
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", background="#2b2b2b", foreground="white",
                        fieldbackground="#2b2b2b", rowheight=24)
        style.configure("Treeview.Heading", background="#1f538d", foreground="white")

        cols = ("product_id", "nombre", "sku", "cantidad", "precio_compra")
        self.tabla = ttk.Treeview(self, columns=cols, show="headings", height=8)
        for col, ancho in zip(cols, (80, 260, 120, 80, 110)):
            self.tabla.heading(col, text=col.replace("_", " ").title())
            self.tabla.column(col, width=ancho)
        self.tabla.pack(fill="x", padx=20, pady=6)

        ctk.CTkButton(self, text="✅ Guardar OC y Actualizar WooCommerce",
                      command=self._guardar_oc).pack(pady=12)

        self.lbl_status = ctk.CTkLabel(self, text="")
        self.lbl_status.pack()

    def _buscar_producto(self):
        sku = self.ent_sku.get().strip()
        if not sku:
            return
        self.lbl_producto.configure(text="Buscando…")

        def _fetch():
            try:
                prod = woo_api.buscar_producto_por_sku(sku) or \
                       woo_api.buscar_producto_por_barcode(sku)
                if prod:
                    nombre = prod.get("name", "—")
                    pid = prod.get("id")
                    sku_real = prod.get("sku", sku)
                    self.lbl_producto.configure(
                        text=f"✔ {nombre}  (ID: {pid}  SKU: {sku_real})")
                    self._producto_actual = {"id": pid, "nombre": nombre,
                                             "sku": sku_real}
                else:
                    self.lbl_producto.configure(
                        text="⚠ Producto no encontrado en WooCommerce",
                        text_color="orange")
                    self._producto_actual = None
            except Exception as e:
                self.lbl_producto.configure(text=f"Error: {e}", text_color="red")
                self._producto_actual = None

        threading.Thread(target=_fetch, daemon=True).start()

    def _add_item(self, prod: dict, cantidad: int, precio: float):
        self._items.append({**prod, "cantidad": cantidad, "precio_compra": precio})
        self.tabla.insert("", "end", values=(
            prod["id"], prod["nombre"], prod["sku"], cantidad, precio))

    def _buscar_y_agregar(self):
        if not hasattr(self, "_producto_actual") or not self._producto_actual:
            messagebox.showwarning("Sin producto", "Busca un producto primero.")
            return
        try:
            cantidad = int(self.ent_cantidad.get())
            precio = float(self.ent_precio.get())
        except ValueError:
            messagebox.showerror("Error", "Cantidad y precio deben ser numéricos.")
            return
        self._add_item(self._producto_actual, cantidad, precio)
        self.ent_sku.delete(0, "end")
        self.ent_cantidad.delete(0, "end")
        self.ent_precio.delete(0, "end")
        self.lbl_producto.configure(text="")
        self._producto_actual = None

    def _guardar_oc(self):
        # Si hay un producto buscado pendiente de agregar, lo agrega primero
        if hasattr(self, "_producto_actual") and self._producto_actual:
            try:
                cantidad = int(self.ent_cantidad.get())
                precio = float(self.ent_precio.get())
                self._add_item(self._producto_actual, cantidad, precio)
            except ValueError:
                messagebox.showerror("Error", "Ingresa cantidad y precio antes de guardar.")
                return

        if not self._items:
            messagebox.showwarning("Vacío", "Agrega al menos un producto a la OC.")
            return

        proveedor = self.ent_proveedor.get().strip() or "Sin proveedor"
        notas = self.ent_notas.get().strip()

        def _save():
            try:
                id_oc = db.crear_orden_compra(proveedor, notas)
                for item in self._items:
                    db.crear_lote(id_oc, item["id"], item["sku"],
                                  item["cantidad"], item["precio_compra"])
                    woo_api.incrementar_stock(item["id"], item["cantidad"])
                self.lbl_status.configure(
                    text=f"✅ OC #{id_oc} guardada y stock actualizado en WooCommerce.",
                    text_color="green")
                # Limpiar
                self._items.clear()
                for row in self.tabla.get_children():
                    self.tabla.delete(row)
                self.ent_proveedor.delete(0, "end")
                self.ent_notas.delete(0, "end")
            except Exception as e:
                self.lbl_status.configure(text=f"Error: {e}", text_color="red")

        threading.Thread(target=_save, daemon=True).start()


# ═════════════════════════════════════════════════════════════════════════════
#  MÓDULO: IMPORTAR VENTAS (FIFO)
# ═════════════════════════════════════════════════════════════════════════════
class FrameVentas(ctk.CTkFrame):
    def __init__(self, parent, app: App):
        super().__init__(parent, corner_radius=0)
        self.app = app
        self._build()

    def _build(self):
        ctk.CTkLabel(self, text="Importar Ventas desde WooCommerce",
                     font=ctk.CTkFont(size=18, weight="bold")).pack(pady=12)

        row = ctk.CTkFrame(self)
        row.pack(fill="x", padx=20, pady=8)

        ctk.CTkLabel(row, text="Desde fecha (AAAA-MM-DD):").pack(side="left", padx=6)
        self.ent_fecha = ctk.CTkEntry(row, width=160, placeholder_text="Dejar vacío = todo")
        self.ent_fecha.pack(side="left", padx=6)

        ctk.CTkButton(row, text="🔄 Importar Ventas",
                      command=self._importar).pack(side="left", padx=12)

        self.txt_log = ctk.CTkTextbox(self, height=420)
        self.txt_log.pack(fill="both", expand=True, padx=20, pady=8)

    def _log(self, msg: str):
        self.txt_log.insert("end", msg + "\n")
        self.txt_log.see("end")

    def _importar(self):
        fecha = self.ent_fecha.get().strip()
        desde = f"{fecha}T00:00:00" if fecha else None
        self.txt_log.delete("0.0", "end")
        self._log("Conectando con WooCommerce…")

        def _run():
            try:
                ordenes = woo_api.obtener_ordenes_completadas(desde_fecha=desde)
                self._log(f"Órdenes encontradas: {len(ordenes)}")
                resultado = fifo.importar_ordenes_woo(ordenes)
                self._log(f"✅ Procesadas: {len(resultado['procesadas'])}")
                self._log(f"⏭ Omitidas (ya procesadas): {len(resultado['omitidas'])}")
                if resultado["errores"]:
                    self._log(f"⚠ Errores ({len(resultado['errores'])}):")
                    for e in resultado["errores"]:
                        self._log(f"   Orden #{e['order_id']}: {e['error']}")
            except Exception as e:
                self._log(f"❌ {e}")

        threading.Thread(target=_run, daemon=True).start()


# ═════════════════════════════════════════════════════════════════════════════
#  MÓDULO: GENERADOR DE ETIQUETAS
# ═════════════════════════════════════════════════════════════════════════════
class FrameEtiquetas(ctk.CTkFrame):
    def __init__(self, parent, app: App):
        super().__init__(parent, corner_radius=0)
        self.app = app
        self._items: list[dict] = []
        self._producto_actual = None
        self._build()

    def _build(self):
        ctk.CTkLabel(self, text="Generador de Etiquetas (Excel)",
                     font=ctk.CTkFont(size=18, weight="bold")).pack(pady=12)

        row = ctk.CTkFrame(self)
        row.pack(fill="x", padx=20, pady=4)

        ctk.CTkLabel(row, text="SKU / Barcode:").grid(row=0, column=0, padx=4)
        self.ent_sku = ctk.CTkEntry(row, width=160)
        self.ent_sku.grid(row=0, column=1, padx=4)

        ctk.CTkLabel(row, text="Cantidad etiquetas:").grid(row=0, column=2, padx=4)
        self.ent_cant = ctk.CTkEntry(row, width=80)
        self.ent_cant.grid(row=0, column=3, padx=4)

        ctk.CTkButton(row, text="Buscar", width=90,
                      command=self._buscar).grid(row=0, column=4, padx=6)
        ctk.CTkButton(row, text="➕ Agregar", width=90,
                      command=self._agregar).grid(row=0, column=5, padx=4)

        self.lbl_info = ctk.CTkLabel(self, text="", text_color="cyan")
        self.lbl_info.pack()

        from tkinter import ttk
        cols = ("nombre", "sku", "precio", "barcode", "cantidad")
        self.tabla = ttk.Treeview(self, columns=cols, show="headings", height=8)
        for col, ancho in zip(cols, (260, 120, 80, 160, 80)):
            self.tabla.heading(col, text=col.title())
            self.tabla.column(col, width=ancho)
        self.tabla.pack(fill="x", padx=20, pady=6)

        ctk.CTkButton(self, text="📤 Exportar a Excel",
                      command=self._exportar).pack(pady=10)

        self.lbl_status = ctk.CTkLabel(self, text="")
        self.lbl_status.pack()

    def _buscar(self):
        sku = self.ent_sku.get().strip()
        if not sku:
            return
        self.lbl_info.configure(text="Buscando…")

        def _fetch():
            try:
                import json, os
                cfg_path = os.path.join(os.path.dirname(__file__), "config.json")
                with open(cfg_path) as f:
                    cfg = json.load(f)
                meta_key = cfg.get("yith_barcode_meta_key", "_ywbc_barcode_value")

                prod = woo_api.buscar_producto_por_sku(sku) or \
                       woo_api.buscar_producto_por_barcode(sku)
                if prod:
                    barcode = woo_api.get_barcode_de_producto(prod, meta_key)
                    self._producto_actual = {
                        "nombre": prod.get("name", ""),
                        "sku": prod.get("sku", sku),
                        "precio": float(prod.get("price", 0)),
                        "barcode": barcode or sku,
                    }
                    self.lbl_info.configure(
                        text=f"✔ {self._producto_actual['nombre']}  "
                             f"Barcode: {self._producto_actual['barcode']}")
                else:
                    self.lbl_info.configure(text="⚠ No encontrado", text_color="orange")
                    self._producto_actual = None
            except Exception as e:
                self.lbl_info.configure(text=f"Error: {e}", text_color="red")

        threading.Thread(target=_fetch, daemon=True).start()

    def _agregar(self):
        if not self._producto_actual:
            messagebox.showwarning("Sin producto", "Busca un producto primero.")
            return
        try:
            cantidad = int(self.ent_cant.get())
        except ValueError:
            messagebox.showerror("Error", "Ingresa una cantidad válida.")
            return
        item = {**self._producto_actual, "cantidad": cantidad}
        self._items.append(item)
        self.tabla.insert("", "end", values=(
            item["nombre"], item["sku"], item["precio"],
            item["barcode"], item["cantidad"]))
        self.ent_sku.delete(0, "end")
        self.ent_cant.delete(0, "end")
        self.lbl_info.configure(text="")
        self._producto_actual = None

    def _exportar(self):
        if not self._items:
            messagebox.showwarning("Vacío", "Agrega productos primero.")
            return
        ruta = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
            title="Guardar etiquetas como…"
        )
        if not ruta:
            return
        try:
            etiquetas.exportar_etiquetas(self._items, ruta)
            self.lbl_status.configure(text=f"✅ Exportado: {ruta}", text_color="green")
        except Exception as e:
            self.lbl_status.configure(text=f"Error: {e}", text_color="red")


# ═════════════════════════════════════════════════════════════════════════════
#  MÓDULO: DASHBOARD (INVENTARIO + UTILIDADES)
# ═════════════════════════════════════════════════════════════════════════════
class FrameDashboard(ctk.CTkFrame):
    def __init__(self, parent, app: App):
        super().__init__(parent, corner_radius=0)
        self.app = app
        self._build()

    def _build(self):
        from tkinter import ttk

        encabezado = ctk.CTkFrame(self, fg_color="transparent")
        encabezado.pack(fill="x", padx=20, pady=(12, 4))
        ctk.CTkLabel(encabezado, text="Dashboard",
                     font=ctk.CTkFont(size=18, weight="bold")).pack(side="left")
        ctk.CTkButton(encabezado, text="🔄 Actualizar", width=110,
                      command=self.on_show).pack(side="right")

        tabs = ctk.CTkTabview(self)
        tabs.pack(fill="both", expand=True, padx=20, pady=8)
        tabs.add("📦 Inventario Actual")
        tabs.add("📊 Utilidades")
        self.tabs = tabs

        # ── Tab: Inventario ───────────────────────────────────────────────
        tab_inv = tabs.tab("📦 Inventario Actual")

        cols_inv = ("id_lote", "oc", "proveedor", "fecha_oc", "product_id",
                    "sku", "cant_ini", "cant_actual", "precio_compra", "valor_stock")
        anchos_inv = (60, 50, 130, 130, 85, 120, 70, 80, 110, 100)
        titulos_inv = ("Lote", "OC", "Proveedor", "Fecha OC", "Product ID",
                       "SKU", "Ini.", "Actual", "P. Compra", "Valor Stock")

        frame_inv = ctk.CTkFrame(tab_inv, fg_color="transparent")
        frame_inv.pack(fill="both", expand=True)

        self.tabla_inv = ttk.Treeview(frame_inv, columns=cols_inv,
                                      show="headings", height=18)
        for col, ancho, titulo in zip(cols_inv, anchos_inv, titulos_inv):
            self.tabla_inv.heading(col, text=titulo)
            self.tabla_inv.column(col, width=ancho, anchor="center")

        sc_inv = tk.Scrollbar(frame_inv, orient="vertical",
                              command=self.tabla_inv.yview)
        self.tabla_inv.configure(yscrollcommand=sc_inv.set)
        sc_inv.pack(side="right", fill="y")
        self.tabla_inv.pack(fill="both", expand=True)

        pie_inv = ctk.CTkFrame(tab_inv, fg_color="transparent")
        pie_inv.pack(fill="x", padx=6, pady=(0, 4))
        self.lbl_inv = ctk.CTkLabel(pie_inv, text="", text_color="cyan")
        self.lbl_inv.pack(side="left")
        ctk.CTkButton(pie_inv, text="📤 Exportar Excel", width=150,
                      command=lambda: self._exportar_treeview(
                          self.tabla_inv, titulos_inv, "inventario_lotes"
                      )).pack(side="right")

        # ── Tab: Utilidades ───────────────────────────────────────────────
        tab_ut = tabs.tab("📊 Utilidades")

        cols_ut = ("fecha", "order_id", "product_id", "sku", "cant",
                   "precio_venta", "costo_unit", "utilidad")
        anchos_ut = (130, 80, 90, 120, 60, 110, 110, 110)
        titulos_ut = ("Fecha", "Orden WOO", "Product ID", "SKU", "Cant",
                      "Precio Venta", "Costo Unit.", "Utilidad Neta")

        frame_ut = ctk.CTkFrame(tab_ut, fg_color="transparent")
        frame_ut.pack(fill="both", expand=True)

        self.tabla_ut = ttk.Treeview(frame_ut, columns=cols_ut,
                                     show="headings", height=18)
        for col, ancho, titulo in zip(cols_ut, anchos_ut, titulos_ut):
            self.tabla_ut.heading(col, text=titulo)
            self.tabla_ut.column(col, width=ancho, anchor="center")

        sc_ut = tk.Scrollbar(frame_ut, orient="vertical",
                             command=self.tabla_ut.yview)
        self.tabla_ut.configure(yscrollcommand=sc_ut.set)
        sc_ut.pack(side="right", fill="y")
        self.tabla_ut.pack(fill="both", expand=True)

        pie_ut = ctk.CTkFrame(tab_ut, fg_color="transparent")
        pie_ut.pack(fill="x", padx=6, pady=(0, 4))
        self.lbl_total = ctk.CTkLabel(pie_ut, text="")
        self.lbl_total.pack(side="left")
        ctk.CTkButton(pie_ut, text="📤 Exportar Excel", width=150,
                      command=lambda: self._exportar_treeview(
                          self.tabla_ut, titulos_ut, "utilidades"
                      )).pack(side="right")

        # ── Tab: Stock WooCommerce ────────────────────────────────────────
        tabs.add("🌐 Stock WooCommerce")
        tab_woo = tabs.tab("🌐 Stock WooCommerce")
        self._productos_woo: list[dict] = []   # caché de productos cargados

        ctrl_woo = ctk.CTkFrame(tab_woo, fg_color="transparent")
        ctrl_woo.pack(fill="x", padx=6, pady=(6, 2))

        ctk.CTkButton(ctrl_woo, text="🔄 Cargar desde WooCommerce", width=210,
                      command=self._cargar_woo).pack(side="left", padx=(0, 8))
        ctk.CTkButton(ctrl_woo, text="📋 Crear OC desde WooCommerce", width=220,
                      command=self._crear_oc_desde_woo).pack(side="left", padx=(0, 16))

        ctk.CTkLabel(ctrl_woo, text="Buscar:").pack(side="left")
        self.ent_buscar_woo = ctk.CTkEntry(ctrl_woo, width=220,
                                           placeholder_text="nombre o SKU…")
        self.ent_buscar_woo.pack(side="left", padx=6)
        self.ent_buscar_woo.bind("<KeyRelease>", lambda e: self._filtrar_woo())

        self.lbl_woo_status = ctk.CTkLabel(ctrl_woo, text="", text_color="cyan")
        self.lbl_woo_status.pack(side="left", padx=8)

        cols_woo = ("id", "nombre", "sku", "precio", "stock", "estado_stock",
                    "manage_stock")
        anchos_woo = (60, 280, 130, 80, 70, 110, 100)
        titulos_woo = ("ID", "Nombre", "SKU", "Precio", "Stock", "Estado",
                       "Gestiona Stock")

        frame_woo = ctk.CTkFrame(tab_woo, fg_color="transparent")
        frame_woo.pack(fill="both", expand=True, padx=6)

        self.tabla_woo = ttk.Treeview(frame_woo, columns=cols_woo,
                                      show="headings", height=18,
                                      selectmode="extended")
        for col, ancho, titulo in zip(cols_woo, anchos_woo, titulos_woo):
            self.tabla_woo.heading(col, text=titulo,
                                   command=lambda c=col: self._sort_woo(c))
            self.tabla_woo.column(col, width=ancho, anchor="center")
        self.tabla_woo.tag_configure("agotado", foreground="#ff6b6b")
        self.tabla_woo.tag_configure("bajo",    foreground="#ffd93d")
        self.tabla_woo.tag_configure("ok",      foreground="#6bcb77")
        self.tabla_woo.tag_configure("notrack", foreground="#aaaaaa")

        sc_woo = tk.Scrollbar(frame_woo, orient="vertical",
                              command=self.tabla_woo.yview)
        self.tabla_woo.configure(yscrollcommand=sc_woo.set)
        sc_woo.pack(side="right", fill="y")
        self.tabla_woo.pack(fill="both", expand=True)

        pie_woo = ctk.CTkFrame(tab_woo, fg_color="transparent")
        pie_woo.pack(fill="x", padx=6, pady=(2, 4))
        ctk.CTkButton(pie_woo, text="📤 Exportar Excel", width=160,
                      command=lambda: self._exportar_treeview(
                          self.tabla_woo, titulos_woo, "stock_woocommerce"
                      )).pack(side="right")

        self._sort_woo_col = None
        self._sort_woo_rev = False

        # ── Tab: Surtido ───────────────────────────────────────────────
        tabs.add("🔄 Surtido")
        tab_surtido = tabs.tab("🔄 Surtido")

        ctrl_s = ctk.CTkFrame(tab_surtido, fg_color="transparent")
        ctrl_s.pack(fill="x", padx=6, pady=(6, 2))

        ctk.CTkLabel(ctrl_s, text="Desde:").pack(side="left")
        self.ent_surtido_desde = ctk.CTkEntry(ctrl_s, width=110,
                                              placeholder_text="AAAA-MM-DD")
        self.ent_surtido_desde.pack(side="left", padx=(4, 10))

        ctk.CTkLabel(ctrl_s, text="Hasta:").pack(side="left")
        self.ent_surtido_hasta = ctk.CTkEntry(ctrl_s, width=110,
                                              placeholder_text="AAAA-MM-DD (opc.)")
        self.ent_surtido_hasta.pack(side="left", padx=(4, 12))

        ctk.CTkButton(ctrl_s, text="📊 Analizar", width=120,
                      command=self._cargar_surtido).pack(side="left")

        self.lbl_surtido_status = ctk.CTkLabel(ctrl_s, text="", text_color="cyan")
        self.lbl_surtido_status.pack(side="left", padx=10)

        cols_surtido  = ("id", "nombre", "sku", "precio",
                         "vendidos", "vel_semana", "rating", "stock")
        anchos_surtido = (60, 250, 110, 90, 80, 100, 120, 70)
        titulos_surtido = ("ID", "Nombre", "SKU", "Precio",
                           "Vendidos", "Vel/Semana", "Calificación", "Stock")

        frame_s = ctk.CTkFrame(tab_surtido, fg_color="transparent")
        frame_s.pack(fill="both", expand=True, padx=6)

        self.tabla_surtido = ttk.Treeview(frame_s, columns=cols_surtido,
                                          show="headings", height=16)
        for col, ancho, titulo in zip(cols_surtido, anchos_surtido, titulos_surtido):
            self.tabla_surtido.heading(col, text=titulo)
            self.tabla_surtido.column(col, width=ancho, anchor="center")
        self.tabla_surtido.tag_configure("fast",   foreground="#6bcb77")
        self.tabla_surtido.tag_configure("medium", foreground="#ffd93d")
        self.tabla_surtido.tag_configure("slow",   foreground="#ff9f43")

        sc_s = tk.Scrollbar(frame_s, orient="vertical",
                            command=self.tabla_surtido.yview)
        self.tabla_surtido.configure(yscrollcommand=sc_s.set)
        sc_s.pack(side="right", fill="y")
        self.tabla_surtido.pack(fill="both", expand=True)

        pie_s = ctk.CTkFrame(tab_surtido, fg_color="transparent")
        pie_s.pack(fill="x", padx=6, pady=(2, 4))
        leyenda = ctk.CTkFrame(pie_s, fg_color="transparent")
        leyenda.pack(side="left")
        ctk.CTkLabel(leyenda, text="● Rápido",  text_color="#6bcb77",
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=6)
        ctk.CTkLabel(leyenda, text="● Medio",   text_color="#ffd93d",
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=6)
        ctk.CTkLabel(leyenda, text="● Lento",   text_color="#ff9f43",
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=6)
        ctk.CTkButton(pie_s, text="📤 Exportar Excel", width=160,
                      command=lambda: self._exportar_treeview(
                          self.tabla_surtido, titulos_surtido, "surtido"
                      )).pack(side="right")

        # ── Tab: Decisiones de Inventario ─────────────────────────────────
        tabs.add("🎯 Decisiones")
        tab_d = tabs.tab("🎯 Decisiones")

        ctrl_d = ctk.CTkFrame(tab_d, fg_color="transparent")
        ctrl_d.pack(fill="x", padx=6, pady=(6, 2))

        ctk.CTkLabel(ctrl_d, text="Desde:").pack(side="left")
        self.ent_dec_desde = ctk.CTkEntry(ctrl_d, width=110,
                                          placeholder_text="AAAA-MM-DD (opc.)")
        self.ent_dec_desde.pack(side="left", padx=(4, 10))

        ctk.CTkLabel(ctrl_d, text="Hasta:").pack(side="left")
        self.ent_dec_hasta = ctk.CTkEntry(ctrl_d, width=110,
                                          placeholder_text="AAAA-MM-DD (opc.)")
        self.ent_dec_hasta.pack(side="left", padx=(4, 12))

        ctk.CTkButton(ctrl_d, text="🔍 Analizar", width=120,
                      command=self._cargar_decisiones).pack(side="left")

        self.lbl_dec_status = ctk.CTkLabel(ctrl_d, text="", text_color="cyan")
        self.lbl_dec_status.pack(side="left", padx=10)

        cols_d = ("id", "nombre", "sku", "precio_venta", "margen_pct",
                  "vel_semana", "util_semana", "stock", "cobertura",
                  "score", "recomendacion")
        anchos_d  = (55, 220, 110, 95, 80, 80, 100, 55, 90, 50, 160)
        titulos_d = ("ID", "Nombre", "SKU", "P. Venta", "Margen %",
                     "Vel/Sem", "Utilid/Sem", "Stock", "Cobertura",
                     "Score", "Recomendación")

        frame_d = ctk.CTkFrame(tab_d, fg_color="transparent")
        frame_d.pack(fill="both", expand=True, padx=6)

        self.tabla_dec = ttk.Treeview(frame_d, columns=cols_d,
                                      show="headings", height=15)
        for col, ancho, titulo in zip(cols_d, anchos_d, titulos_d):
            self.tabla_dec.heading(col, text=titulo,
                                   command=lambda c=col: self._sort_dec(c))
            self.tabla_dec.column(col, width=ancho, anchor="center")

        self.tabla_dec.tag_configure("resurtir",  foreground="#6bcb77")
        self.tabla_dec.tag_configure("mantener",  foreground="#4fc3f7")
        self.tabla_dec.tag_configure("precio",    foreground="#ffd93d")
        self.tabla_dec.tag_configure("revisar",   foreground="#ffd93d")
        self.tabla_dec.tag_configure("nicho",     foreground="#ce93d8")
        self.tabla_dec.tag_configure("descartar", foreground="#ff6b6b")
        self.tabla_dec.tag_configure("preciolow", foreground="#ff4d4d")

        sc_d = tk.Scrollbar(frame_d, orient="vertical",
                            command=self.tabla_dec.yview)
        self.tabla_dec.configure(yscrollcommand=sc_d.set)
        sc_d.pack(side="right", fill="y")
        self.tabla_dec.pack(fill="both", expand=True)

        pie_d = ctk.CTkFrame(tab_d, fg_color="transparent")
        pie_d.pack(fill="x", padx=6, pady=(2, 4))
        leyenda_d = ctk.CTkFrame(pie_d, fg_color="transparent")
        leyenda_d.pack(side="left")
        for txt, color in [("● RESURTIR", "#6bcb77"), ("● MANTENER", "#4fc3f7"),
                           ("● REVISAR", "#ffd93d"),  ("● NICHO", "#ce93d8"),
                           ("● DESCARTAR", "#ff4d4d")]:
            ctk.CTkLabel(leyenda_d, text=txt, text_color=color,
                         font=ctk.CTkFont(size=11)).pack(side="left", padx=5)
        ctk.CTkButton(pie_d, text="📤 Exportar Excel", width=160,
                      command=lambda: self._exportar_treeview(
                          self.tabla_dec, titulos_d, "decisiones_inventario"
                      )).pack(side="right")

        self._sort_dec_col = None
        self._sort_dec_rev = False

    def on_show(self):
        self._cargar_inventario()
        self._cargar_utilidades()

    def _exportar_treeview(self, tabla, titulos: tuple, nombre_archivo: str):
        """Exporta a Excel exactamente lo que se ve en la tabla (orden y filtro actual)."""
        filas = [tabla.item(row, "values") for row in tabla.get_children()]
        if not filas:
            messagebox.showinfo("Sin datos", "La tabla no tiene filas para exportar.")
            return
        ruta = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            initialfile=f"{nombre_archivo}.xlsx",
            filetypes=[("Excel", "*.xlsx")],
            title="Guardar como…",
        )
        if not ruta:
            return
        try:
            import pandas as pd
            df = pd.DataFrame(filas, columns=list(titulos))
            df.to_excel(ruta, index=False)
            messagebox.showinfo("Exportado", f"Archivo guardado:\n{ruta}")
        except Exception as e:
            messagebox.showerror("Error al exportar", str(e))

    def _cargar_inventario(self):
        for row in self.tabla_inv.get_children():
            self.tabla_inv.delete(row)
        lotes = db.listar_todos_lotes()
        valor_total = 0.0
        for l in lotes:
            valor_total += float(l["valor_stock"] or 0)
            self.tabla_inv.insert("", "end", values=(
                l["id_lote"],
                l["id_oc"] or "—",
                l["proveedor"] or "—",
                str(l["fecha_ingreso"] or "")[:16],
                l["product_id"],
                l["sku"] or "—",
                l["cantidad_inicial"],
                l["cantidad_actual"],
                f"${float(l['precio_compra_unitario']):.2f}",
                f"${float(l['valor_stock']):.2f}",
            ))
        self.lbl_inv.configure(
            text=f"Valor total en stock: ${valor_total:,.2f}")

    def _cargar_utilidades(self):
        for row in self.tabla_ut.get_children():
            self.tabla_ut.delete(row)
        ventas = db.listar_ventas()
        utilidad_total = 0.0
        for v in ventas:
            self.tabla_ut.insert("", "end", values=(
                v["fecha_venta"], v["order_id_woo"], v["product_id"],
                v["sku"] or "—", v["cantidad_vendida"],
                f"${float(v['precio_venta_unitario']):.2f}",
                f"${float(v['costo_unitario']):.2f}" if v["costo_unitario"] else "—",
                f"${float(v['utilidad_neta']):.2f}",
            ))
            utilidad_total += float(v["utilidad_neta"])
        self.lbl_total.configure(
            text=f"Utilidad Total: ${utilidad_total:,.2f}",
            text_color="lime" if utilidad_total >= 0 else "red")

    def _cargar_woo(self):
        self.lbl_woo_status.configure(text="Cargando…", text_color="cyan")
        for row in self.tabla_woo.get_children():
            self.tabla_woo.delete(row)
        self._productos_woo.clear()

        def _fetch():
            try:
                productos = woo_api.get_todos_productos()
                self._productos_woo.extend(productos)
                self._filtrar_woo()
                self.lbl_woo_status.configure(
                    text=f"{len(productos)} productos cargados", text_color="cyan")
            except Exception as e:
                self.lbl_woo_status.configure(
                    text=f"Error: {e}", text_color="red")

        threading.Thread(target=_fetch, daemon=True).start()

    def _filtrar_woo(self):
        termino = self.ent_buscar_woo.get().strip().lower()
        for row in self.tabla_woo.get_children():
            self.tabla_woo.delete(row)
        for p in self._productos_woo:
            nombre = p.get("name", "") or ""
            sku    = p.get("sku", "") or ""
            if termino and termino not in nombre.lower() and termino not in sku.lower():
                continue
            stock        = p.get("stock_quantity")
            manage_stock = p.get("manage_stock", False)
            estado       = p.get("stock_status", "")
            if not manage_stock:
                stock_str = "—"
                tag = "notrack"
            elif stock is None:
                stock_str = "—"
                tag = "notrack"
            else:
                stock_str = str(stock)
                tag = "agotado" if stock == 0 else ("bajo" if stock <= 5 else "ok")
            self.tabla_woo.insert("", "end", tags=(tag,), values=(
                p.get("id"),
                nombre,
                sku if sku else "sin SKU",
                f"${float(p.get('price') or 0):.2f}",
                stock_str,
                estado,
                "Sí" if manage_stock else "No",
            ))
        visible = len(self.tabla_woo.get_children())
        total   = len(self._productos_woo)
        self.lbl_woo_status.configure(
            text=f"Mostrando {visible} de {total}", text_color="cyan")

    def _sort_woo(self, col: str):
        items = [(self.tabla_woo.set(k, col), k)
                 for k in self.tabla_woo.get_children("")]
        reverse = (self._sort_woo_col == col and not self._sort_woo_rev)
        items.sort(reverse=reverse)
        for index, (_, k) in enumerate(items):
            self.tabla_woo.move(k, "", index)
        self._sort_woo_col = col
        self._sort_woo_rev = reverse

    def _crear_oc_desde_woo(self):
        """Abre ventana para crear la OC inicial usando el stock actual de WooCommerce."""
        if not self._productos_woo:
            messagebox.showwarning("Sin datos",
                "Primero carga los productos con '🔄 Cargar desde WooCommerce'.")
            return

        # Solo productos con stock gestionado y > 0
        con_stock = [p for p in self._productos_woo
                     if p.get("manage_stock") and (p.get("stock_quantity") or 0) > 0]
        if not con_stock:
            messagebox.showinfo("Sin stock",
                "No hay productos con gestión de stock activa y stock > 0.")
            return

        win = ctk.CTkToplevel(self)
        win.title("Crear OC inicial desde WooCommerce")
        win.geometry("860x580")
        win.grab_set()

        ctk.CTkLabel(win, text="Crear OC inicial desde stock WooCommerce",
                     font=ctk.CTkFont(size=15, weight="bold")).pack(pady=10)

        info = ctk.CTkFrame(win, fg_color="transparent")
        info.pack(fill="x", padx=16)
        ctk.CTkLabel(info, text="Proveedor:").pack(side="left")
        ent_prov = ctk.CTkEntry(info, width=180)
        ent_prov.insert(0, "Stock inicial WooCommerce")
        ent_prov.pack(side="left", padx=6)
        ctk.CTkLabel(info, text="Precio compra default:").pack(side="left", padx=(16, 0))
        ent_precio_def = ctk.CTkEntry(info, width=90)
        ent_precio_def.insert(0, "0.00")
        ent_precio_def.pack(side="left", padx=6)
        ctk.CTkLabel(info, text="(puedes editar cada fila)",
                     text_color="gray").pack(side="left")

        from tkinter import ttk
        cols = ("sel", "id", "nombre", "sku", "stock", "precio_compra")
        frame_t = ctk.CTkFrame(win, fg_color="transparent")
        frame_t.pack(fill="both", expand=True, padx=16, pady=8)

        tabla_oc = ttk.Treeview(frame_t, columns=cols, show="headings", height=16,
                                 selectmode="extended")
        for col, ancho, h in zip(cols,
                                  (40, 60, 280, 130, 70, 110),
                                  ("✔", "ID", "Nombre", "SKU", "Stock WOO", "P. Compra")):
            tabla_oc.heading(col, text=h)
            tabla_oc.column(col, width=ancho, anchor="center")
        sc = tk.Scrollbar(frame_t, orient="vertical", command=tabla_oc.yview)
        tabla_oc.configure(yscrollcommand=sc.set)
        sc.pack(side="right", fill="y")
        tabla_oc.pack(fill="both", expand=True)

        precio_ref: dict[str, float] = {}

        def _rellenar_tabla():
            for row in tabla_oc.get_children():
                tabla_oc.delete(row)
            try:
                precio_def = float(ent_precio_def.get())
            except ValueError:
                precio_def = 0.0
            for p in con_stock:
                pid    = str(p.get("id"))
                precio = precio_ref.get(pid, precio_def)
                tabla_oc.insert("", "end", iid=pid, values=(
                    "✔", pid,
                    p.get("name", ""),
                    p.get("sku", "") or "sin SKU",
                    p.get("stock_quantity", 0),
                    f"{precio:.2f}",
                ))

        ent_precio_def.bind("<FocusOut>", lambda e: _rellenar_tabla())
        ent_precio_def.bind("<Return>",   lambda e: _rellenar_tabla())
        _rellenar_tabla()

        # Editar precio de compra haciendo doble clic
        def _editar_precio(event):
            item = tabla_oc.focus()
            if not item:
                return
            col_index = tabla_oc.identify_column(event.x)
            if col_index != "#6":   # columna precio_compra
                return
            bbox = tabla_oc.bbox(item, "#6")
            if not bbox:
                return
            entry_edit = tk.Entry(tabla_oc, justify="center")
            entry_edit.place(x=bbox[0], y=bbox[1], width=bbox[2], height=bbox[3])
            val = tabla_oc.set(item, "precio_compra")
            entry_edit.insert(0, val)
            entry_edit.focus()

            def _guardar(e=None):
                try:
                    nuevo = float(entry_edit.get())
                    precio_ref[item] = nuevo
                    tabla_oc.set(item, "precio_compra", f"{nuevo:.2f}")
                except ValueError:
                    pass
                entry_edit.destroy()

            entry_edit.bind("<Return>",    _guardar)
            entry_edit.bind("<FocusOut>",  _guardar)

        tabla_oc.bind("<Double-1>", _editar_precio)

        lbl_win_status = ctk.CTkLabel(win, text="")
        lbl_win_status.pack(pady=2)

        def _guardar_oc():
            proveedor = ent_prov.get().strip() or "Stock inicial WooCommerce"
            try:
                precio_def = float(ent_precio_def.get())
            except ValueError:
                precio_def = 0.0

            seleccionados = tabla_oc.get_children()   # todos los visibles
            if not seleccionados:
                messagebox.showwarning("Vacío", "No hay productos para guardar.")
                return

            def _save():
                try:
                    id_oc = db.crear_orden_compra(proveedor,
                                                  "OC generada desde stock WooCommerce")
                    guardados = 0
                    for pid_str in seleccionados:
                        vals  = tabla_oc.item(pid_str, "values")
                        # vals: (sel, id, nombre, sku, stock, precio_compra)
                        pid   = int(vals[1])
                        sku   = vals[3] if vals[3] != "sin SKU" else ""
                        cant  = int(vals[4])
                        try:
                            precio = float(vals[5])
                        except ValueError:
                            precio = precio_def
                        if cant <= 0:
                            continue
                        db.crear_lote(id_oc, pid, sku, cant, precio)
                        guardados += 1
                    lbl_win_status.configure(
                        text=f"✅ OC #{id_oc} creada con {guardados} productos.",
                        text_color="green")
                except Exception as e:
                    lbl_win_status.configure(text=f"Error: {e}", text_color="red")

            threading.Thread(target=_save, daemon=True).start()

        btns = ctk.CTkFrame(win, fg_color="transparent")
        btns.pack(pady=8)
        ctk.CTkButton(btns, text="✅ Crear OC", width=140,
                      command=_guardar_oc).pack(side="left", padx=8)
        ctk.CTkButton(btns, text="Cancelar", width=100,
                      command=win.destroy).pack(side="left", padx=8)

    def _cargar_surtido(self):
        from datetime import datetime, date as dt_date

        desde_str = self.ent_surtido_desde.get().strip()
        hasta_str = self.ent_surtido_hasta.get().strip()

        # Validar fechas solo si se proporcionaron
        try:
            d_desde = datetime.strptime(desde_str, "%Y-%m-%d").date() if desde_str else None
            d_hasta = datetime.strptime(hasta_str, "%Y-%m-%d").date() if hasta_str else dt_date.today()
        except ValueError:
            messagebox.showerror("Fecha inválida", "Usa el formato AAAA-MM-DD.")
            return

        # Calcular días del período para la velocidad de ventas
        if d_desde:
            days = max((d_hasta - d_desde).days, 1)
        else:
            days = 365   # sin filtro → normalizar sobre un año estimado

        desde_api = f"{desde_str}T00:00:00" if desde_str else None
        hasta_api = f"{hasta_str}T23:59:59" if hasta_str else None

        self.lbl_surtido_status.configure(text="Cargando órdenes…", text_color="cyan")
        for row in self.tabla_surtido.get_children():
            self.tabla_surtido.delete(row)

        def _fetch():
            try:
                ordenes = woo_api.obtener_ordenes_rango(desde_api, hasta_api)
                self.lbl_surtido_status.configure(
                    text=f"{len(ordenes)} órdenes → analizando productos…")

                # Agregar unidades vendidas por product_id
                ventas: dict[int, dict] = {}
                for orden in ordenes:
                    for item in orden.get("line_items", []):
                        pid = item.get("product_id")
                        if not pid:
                            continue
                        qty = item.get("quantity", 0)
                        if pid not in ventas:
                            ventas[pid] = {
                                "nombre": item.get("name", ""),
                                "sku":    item.get("sku", ""),
                                "precio": float(item.get("price") or 0),
                                "total":  0,
                            }
                        ventas[pid]["total"] += qty

                if not ventas:
                    self.lbl_surtido_status.configure(
                        text="Sin ventas en el período seleccionado.",
                        text_color="orange")
                    return

                # Obtener stock actual de WooCommerce para esos productos
                productos_data = woo_api.obtener_productos_por_ids(list(ventas.keys()))

                # Filtrar solo los agotados (stock == 0 o outofstock)
                sin_stock = []
                for pid, v in ventas.items():
                    prod = productos_data.get(pid)
                    if not prod:
                        continue
                    stock_qty    = prod.get("stock_quantity")
                    stock_status = prod.get("stock_status", "")
                    agotado = (stock_status == "outofstock") or \
                              (stock_qty is not None and int(stock_qty) == 0)
                    if not agotado:
                        continue
                    sin_stock.append({
                        "id":       pid,
                        "nombre":   prod.get("name") or v["nombre"],
                        "sku":      prod.get("sku") or v["sku"] or "—",
                        "precio":   float(prod.get("price") or v["precio"] or 0),
                        "vendidos": v["total"],
                        # vel/semana = unidades vendidas / días * 7
                        "vel":      v["total"] / days * 7,
                        "stock":    stock_qty if stock_qty is not None else 0,
                    })

                if not sin_stock:
                    self.lbl_surtido_status.configure(
                        text="✅ Todos los productos vendidos en ese período tienen stock.",
                        text_color="lime")
                    return

                # Ordenar por velocidad descendente
                sin_stock.sort(key=lambda x: x["vel"], reverse=True)

                # Calificación por percentil relativo dentro de la lista
                # (evita penalizar por fecha de creación del producto)
                n = len(sin_stock)
                for i, p in enumerate(sin_stock):
                    pos = i / max(n - 1, 1)   # 0.0 (más rápido) .. 1.0 (más lento)
                    if pos <= 0.33:
                        tag, rating = "fast",   "⭐⭐⭐ Rápido"
                    elif pos <= 0.66:
                        tag, rating = "medium", "⭐⭐ Medio"
                    else:
                        tag, rating = "slow",   "⭐ Lento"

                    self.tabla_surtido.insert("", "end", tags=(tag,), values=(
                        p["id"],
                        p["nombre"],
                        p["sku"],
                        f"${p['precio']:,.0f}",
                        p["vendidos"],
                        f"{p['vel']:.2f}",
                        rating,
                        p["stock"],
                    ))

                self.lbl_surtido_status.configure(
                    text=f"{n} productos agotados para surtir — "
                         + (f"período: {days} días" if desde_str else "análisis general (todos los pedidos)"),
                    text_color="cyan")

            except Exception as e:
                self.lbl_surtido_status.configure(
                    text=f"Error: {e}", text_color="red")

        threading.Thread(target=_fetch, daemon=True).start()

    # ── Análisis de Decisiones ────────────────────────────────────────────

    @staticmethod
    def _recomendar(composite: float, margen_pct, cobertura_dias):
        """
        Devuelve (texto_recomendacion, tag_color) según el score compuesto y el margen.

        Lógica inspirada en la Matriz BCG extendida con datos FIFO:
          · composite >= 70 + margen >= 25 % → RESURTIR  (estrella)
          · composite >= 70 + margen <  25 % → SUBIR PRECIO (vende, pero poco margen)
          · composite >= 40 + margen >= 25 % → MANTENER  (vaca de efectivo)
          · composite >= 40 + margen <  25 % → REVISAR MARGEN
          · composite <  40 + margen >= 40 % → NICHO      (lento pero muy rentable)
          · composite <  40 + margen <  40 % → DESCARTAR  (perro)
          · margen <= 0                       → PRECIO BAJO (se vende en pérdida)
          · Sin costo FIFO todavía            → solo velocidad
        Un prefijo ⚡ URGENTE aparece si la cobertura de stock es < 14 días.
        """
        urgente = (cobertura_dias is not None and 0 < cobertura_dias < 14)
        prefix  = "⚡ " if urgente else ""

        if margen_pct is None:
            # Sin costo FIFO: clasificar solo por velocidad relativa
            if composite >= 70:
                return f"{prefix}🟢 RESURTIR",     "resurtir"
            elif composite >= 40:
                return f"{prefix}🔵 MANTENER",     "mantener"
            else:
                return "🟡 SIN COSTO FIFO",        "revisar"

        if margen_pct <= 0:
            return "🔴 PRECIO BAJO",               "preciolow"
        elif composite >= 70 and margen_pct >= 25:
            return f"{prefix}🟢 RESURTIR",         "resurtir"
        elif composite >= 70 and margen_pct < 25:
            return f"{prefix}🟡 SUBIR PRECIO",     "precio"
        elif composite >= 40 and margen_pct >= 25:
            return f"{prefix}🔵 MANTENER",         "mantener"
        elif composite >= 40 and margen_pct < 25:
            return "🟡 REVISAR MARGEN",            "revisar"
        elif margen_pct >= 40:
            return "🟣 NICHO",                     "nicho"
        else:
            return "🔴 DESCARTAR",                 "descartar"

    def _sort_dec(self, col: str):
        items = [(self.tabla_dec.set(k, col), k)
                 for k in self.tabla_dec.get_children("")]
        reverse = (self._sort_dec_col == col and not self._sort_dec_rev)
        items.sort(reverse=reverse)
        for index, (_, k) in enumerate(items):
            self.tabla_dec.move(k, "", index)
        self._sort_dec_col = col
        self._sort_dec_rev = reverse

    def _cargar_decisiones(self):
        """
        Calcula el score compuesto de cada producto y genera recomendaciones.

        Métricas por producto (datos locales de ventas_procesadas + lotes_inventario):
          · vel_semana    = unidades / semana (período desde primera venta hasta hoy)
          · margen_pct    = (precio_venta - costo_FIFO) / precio_venta × 100
          · util_semana   = utilidad_neta / semana
          · cobertura     = stock_actual / (vel/día)  → días hasta agotarse
          · score         = 0.35·vel_norm + 0.35·margen_norm + 0.30·profit_norm  (0–100)
        """
        from datetime import datetime, date as dt_date

        desde_str = self.ent_dec_desde.get().strip()
        hasta_str = self.ent_dec_hasta.get().strip()
        try:
            if desde_str:
                datetime.strptime(desde_str, "%Y-%m-%d")
            if hasta_str:
                datetime.strptime(hasta_str, "%Y-%m-%d")
        except ValueError:
            messagebox.showerror("Fecha inválida", "Usa el formato AAAA-MM-DD.")
            return

        desde_db = f"{desde_str}T00:00:00" if desde_str else None
        hasta_db = f"{hasta_str}T23:59:59" if hasta_str else None

        self.lbl_dec_status.configure(text="Analizando…", text_color="cyan")
        for row in self.tabla_dec.get_children():
            self.tabla_dec.delete(row)

        def _compute():
            try:
                datos = db.analisis_por_producto(desde_db, hasta_db)
                if not datos:
                    self.lbl_dec_status.configure(
                        text="Sin ventas procesadas. Ve a 'Importar Ventas' primero.",
                        text_color="orange")
                    return

                today = dt_date.today()
                productos = []

                for r in datos:
                    pid              = r["product_id"]
                    total_vendidos   = r["total_vendidos"] or 0
                    primera_str      = (r["primera_venta"] or "")[:10]
                    precio_venta_prom = float(r["precio_venta_prom"] or 0)
                    costo_unit_prom  = float(r["costo_unit_prom"] or 0)
                    utilidad_total   = float(r["utilidad_total"] or 0)
                    stock_local      = int(r["stock_local"] or 0)
                    sku              = r["sku"] or "—"

                    # Período: desde primera venta hasta hoy (o hasta_str si se filtró)
                    try:
                        primera = datetime.strptime(primera_str, "%Y-%m-%d").date()
                        limite  = (datetime.strptime(hasta_str, "%Y-%m-%d").date()
                                   if hasta_str else today)
                        periodo_dias = max((limite - primera).days, 1)
                    except (ValueError, TypeError):
                        periodo_dias = 30

                    vel_semana = total_vendidos / periodo_dias * 7

                    # Margen: solo si hay costo FIFO registrado
                    if precio_venta_prom > 0 and costo_unit_prom > 0:
                        margen_pct = (precio_venta_prom - costo_unit_prom) \
                                     / precio_venta_prom * 100
                    else:
                        margen_pct = None

                    util_semana = utilidad_total / periodo_dias * 7

                    # Cobertura: días de stock al ritmo de ventas actual
                    if vel_semana > 0:
                        cobertura_dias = stock_local / (vel_semana / 7)
                    else:
                        cobertura_dias = None

                    productos.append({
                        "id":                pid,
                        "sku":               sku,
                        "precio_venta_prom": precio_venta_prom,
                        "margen_pct":        margen_pct,
                        "vel_semana":        vel_semana,
                        "util_semana":       util_semana,
                        "stock":             stock_local,
                        "cobertura_dias":    cobertura_dias,
                    })

                # ── Normalización min-max 0-100 ───────────────────────────
                def _norm_list(values):
                    """Normaliza una lista de floats/None a 0-100."""
                    filtered = [v for v in values if v is not None]
                    if not filtered:
                        return [50] * len(values)
                    lo, hi = min(filtered), max(filtered)
                    rng = hi - lo
                    return [
                        (50 if v is None else (50 if rng == 0 else (v - lo) / rng * 100))
                        for v in values
                    ]

                vel_norms    = _norm_list([p["vel_semana"]  for p in productos])
                margin_norms = _norm_list([p["margen_pct"]  for p in productos])
                profit_norms = _norm_list([p["util_semana"] for p in productos])

                # ── Score compuesto + recomendación ──────────────────────
                for i, p in enumerate(productos):
                    composite = (0.35 * vel_norms[i]
                                 + 0.35 * margin_norms[i]
                                 + 0.30 * profit_norms[i])
                    p["composite"] = composite
                    p["reco"], p["tag"] = self._recomendar(
                        composite, p["margen_pct"], p["cobertura_dias"])

                # Ordenar por score descendente
                productos.sort(key=lambda x: x["composite"], reverse=True)

                # ── Poblar tabla ──────────────────────────────────────────
                # Mapa rápido de nombres desde la caché de WooCommerce
                woo_nombres = {wp.get("id"): wp.get("name", "")
                               for wp in self._productos_woo}

                for p in productos:
                    nombre = woo_nombres.get(p["id"]) or f"(ID: {p['id']})"
                    margen_str    = (f"{p['margen_pct']:.1f}%"
                                     if p["margen_pct"] is not None else "S/D")
                    cobertura_str = (f"{p['cobertura_dias']:.0f} días"
                                     if p["cobertura_dias"] is not None else "—")
                    self.tabla_dec.insert("", "end", tags=(p["tag"],), values=(
                        p["id"],
                        nombre,
                        p["sku"],
                        f"${p['precio_venta_prom']:,.0f}",
                        margen_str,
                        f"{p['vel_semana']:.2f}",
                        f"${p['util_semana']:,.0f}",
                        p["stock"],
                        cobertura_str,
                        f"{p['composite']:.0f}",
                        p["reco"],
                    ))

                n_res = sum(1 for p in productos if "RESURTIR"  in p["reco"])
                n_des = sum(1 for p in productos if "DESCARTAR" in p["reco"]
                                                 or "PRECIO BAJO" in p["reco"])
                self.lbl_dec_status.configure(
                    text=(f"{len(productos)} productos analizados · "
                          f"🟢 {n_res} a resurtir · 🔴 {n_des} a descartar"),
                    text_color="cyan")

            except Exception as e:
                import traceback; traceback.print_exc()
                self.lbl_dec_status.configure(
                    text=f"Error: {e}", text_color="red")

        threading.Thread(target=_compute, daemon=True).start()


# ═════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = App()
    app.mainloop()
