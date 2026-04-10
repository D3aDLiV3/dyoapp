"""
app_web.py — Versión web de WooPosAdmin usando Streamlit.
Desplegable en VPS. Todos los módulos de negocio se reutilizan sin cambios.
Comando de arranque: streamlit run app_web.py --server.port 8501
"""
import os
import json
import tempfile
import warnings
from io import BytesIO
from pathlib import Path
from datetime import date as dt_date, datetime

import pandas as pd
import plotly.express as px
import streamlit as st

warnings.filterwarnings("ignore")

import db
import woo_api
import fifo
import etiquetas as etiq_mod

# ── Configuración de página ───────────────────────────────────────────────────
st.set_page_config(
    page_title="DYO WooAdmin",
    page_icon="🛒",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    /* ── Sidebar: blanco, angosto, borde derecho sutil ──────────────── */
    section[data-testid="stSidebar"] {
        background: #ffffff !important;
        border-right: 1px solid #E5E7EB !important;
        min-width: 200px !important;
        max-width: 200px !important;
        width: 200px !important;
    }
    section[data-testid="stSidebar"] > div:first-child {
        min-width: 200px !important;
        max-width: 200px !important;
        width: 200px !important;
        padding: 1rem 0.75rem !important;
    }

    /* Todos los textos del sidebar: oscuro */
    section[data-testid="stSidebar"] * { color: #1C2333 !important; }
    section[data-testid="stSidebar"] hr {
        border-color: #E5E7EB !important;
        margin: 0.6rem 0 !important;
    }
    section[data-testid="stSidebar"] .stCaption p,
    section[data-testid="stSidebar"] small {
        color: #9CA3AF !important;
        font-size: 0.7rem !important;
        line-height: 1.4 !important;
    }

    /* ── Navegación: ocultar el círculo radio, solo texto ────────────── */
    section[data-testid="stSidebar"] [data-testid="stRadio"] > div {
        gap: 2px !important;
    }
    /* Ocultar el círculo visual del radio */
    section[data-testid="stSidebar"] [data-testid="stRadio"] label > div:first-child {
        width: 0 !important;
        min-width: 0 !important;
        overflow: hidden !important;
        opacity: 0 !important;
        flex: none !important;
        margin: 0 !important;
        padding: 0 !important;
    }
    section[data-testid="stSidebar"] [data-testid="stRadio"] label {
        display: flex !important;
        align-items: center !important;
        width: 100% !important;
        padding: 7px 12px !important;
        border-radius: 6px !important;
        cursor: pointer !important;
        font-size: 0.84rem !important;
        font-weight: 500 !important;
        color: #374151 !important;
        border-left: 3px solid transparent !important;
        margin: 1px 0 !important;
        transition: background 0.15s !important;
    }
    section[data-testid="stSidebar"] [data-testid="stRadio"] label:hover {
        background: #F9FAFB !important;
        border-left-color: #D42B2B !important;
    }
    section[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) {
        background: #FFF1F1 !important;
        color: #D42B2B !important;
        font-weight: 700 !important;
        border-left-color: #D42B2B !important;
    }
    section[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) p {
        color: #D42B2B !important;
    }

    /* ── Fondo general y contenido ──────────────────────────────── */
    .stApp { background: #F5F6FA !important; }
    .main .block-container {
        background: #F5F6FA !important;
        padding-top: 2rem !important;
    }
    .stApp, .stApp * { color: #1C2333; }

    /* ── Títulos ────────────────────────────────────────────────────── */
    h1 {
        color: #1C2333 !important;
        font-weight: 700 !important;
        font-size: 1.6rem !important;
        border-bottom: 2px solid #E5E7EB;
        padding-bottom: 0.5rem;
        margin-bottom: 1.5rem !important;
    }
    h2, h3, h4 { color: #3A5BA0 !important; font-weight: 600 !important; }

    /* ── Métricas ───────────────────────────────────────────────────── */
    div[data-testid="metric-container"] {
        background: #ffffff !important;
        border-radius: 8px !important;
        padding: 16px 20px !important;
        border-top: 3px solid #3A5BA0 !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.07) !important;
    }
    div[data-testid="metric-container"] label {
        color: #6B7280 !important;
        font-size: 0.72rem !important;
        font-weight: 600 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.05em !important;
    }
    div[data-testid="metric-container"] [data-testid="stMetricValue"] {
        color: #1C2333 !important;
        font-size: 1.65rem !important;
        font-weight: 700 !important;
    }

    /* ── Tablas ─────────────────────────────────────────────────────── */
    .stDataFrame thead th {
        background: #3A5BA0 !important;
        color: #ffffff !important;
        font-size: 0.75rem !important;
        text-transform: uppercase !important;
        letter-spacing: 0.03em !important;
    }
    .stDataFrame { box-shadow: 0 1px 3px rgba(0,0,0,0.07) !important; }

    /* ── Inputs ─────────────────────────────────────────────────────── */
    .stTextInput input, .stNumberInput input {
        background: #ffffff !important;
        border: 1px solid #D1D5DB !important;
        color: #1C2333 !important;
    }
    .stTextInput input:focus, .stNumberInput input:focus {
        border-color: #3A5BA0 !important;
        box-shadow: 0 0 0 2px rgba(58,91,160,0.12) !important;
    }

    /* ── Tabs ──────────────────────────────────────────────────────── */
    .stTabs [data-baseweb="tab"] { color: #6B7280 !important; font-weight: 500 !important; }
    .stTabs [aria-selected="true"] {
        color: #D42B2B !important;
        border-bottom: 2px solid #D42B2B !important;
        font-weight: 700 !important;
    }

    hr { border-color: #E5E7EB !important; opacity: 1 !important; }
</style>
""", unsafe_allow_html=True)

# ── Init DB ───────────────────────────────────────────────────────────────────
db.init_db()

# ── Inicializar session_state ─────────────────────────────────────────────────
_DEFAULTS = {
    "oc_items":           [],
    "oc_producto_actual": None,
    "et_items":           [],
    "et_producto_actual": None,
    "woo_cache":          [],
    "log_ventas":         [],
    "dec_rows":           [],
}
for _k, _v in _DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ── Helpers ───────────────────────────────────────────────────────────────────

def _df_download(df: pd.DataFrame, filename: str, label: str = "📤 Descargar Excel"):
    """Botón de descarga Excel para cualquier DataFrame."""
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False)
    st.download_button(
        label=label,
        data=buf.getvalue(),
        file_name=filename,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@st.cache_data(ttl=300, show_spinner="Cargando productos desde WooCommerce…")
def _cargar_woo_cache() -> list[dict]:
    return woo_api.get_todos_productos()


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    _logo_path = Path(__file__).parent / "Logo Descuentos y ofertas" / "Logo.png"
    c1, c2, c3 = st.columns([1, 3, 1])
    with c2:
        st.image(str(_logo_path), use_container_width=True)
    st.markdown(
        "<p style='text-align:center; font-size:0.72rem; color:#9CA3AF; "
        "margin-top:4px; margin-bottom:0; letter-spacing:0.06em; "
        "text-transform:uppercase;'>WooAdmin</p>",
        unsafe_allow_html=True,
    )
    st.markdown("---")
    PAGINA = st.radio(
        "Módulo",
        options=[
            "🏠 Inicio",
            "📦 Orden de Compra",
            "🛒 Importar Ventas",
            "🏷️ Etiquetas",
            "📊 Análisis",
        ],
        label_visibility="collapsed",
    )
    st.markdown("---")
    st.caption("Gestión de Inventario FIFO\nDescuentos y Ofertas")


# ═════════════════════════════════════════════════════════════════════════════
#  MÓDULO: INICIO
# ═════════════════════════════════════════════════════════════════════════════
def pagina_inicio():
    from datetime import date as _date
    st.title("Panel de Control")

    resumen = db.resumen_home()

    # ── KPIs ─────────────────────────────────────────────────────────────
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Valor en Stock",      f"${resumen['valor_stock']:,.0f}")
    k2.metric("Oórdenes de Compra",  resumen["n_ocs"])
    k3.metric("Ventas WooCommerce",  resumen["n_ordenes_woo"])
    k4.metric("Utilidad Neta Total", f"${resumen['utilidad_total']:,.0f}")

    st.markdown("")

    # ── Gráficas ──────────────────────────────────────────────────────────
    gcol1, gcol2 = st.columns([3, 2])

    with gcol1:
        st.markdown("#### Utilidad mensual")
        meses = db.ventas_por_mes()
        if meses:
            df_m = pd.DataFrame([dict(r) for r in meses])
            fig = px.bar(
                df_m, x="mes", y="utilidad",
                color_discrete_sequence=["#3A5BA0"],
                labels={"mes": "", "utilidad": "Utilidad ($)"},
                height=260,
            )
            fig.update_layout(
                margin=dict(l=0, r=0, t=8, b=0),
                plot_bgcolor="#ffffff", paper_bgcolor="#ffffff",
                font=dict(color="#1C2333", size=11),
                xaxis=dict(tickangle=-35, gridcolor="#F3F4F6"),
                yaxis=dict(gridcolor="#F3F4F6"),
            )
            fig.update_traces(marker_line_width=0)
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("Sin ventas procesadas aún. Ve a Importar Ventas.")

    with gcol2:
        st.markdown("#### Top productos por utilidad")
        top = db.top_productos_utilidad(8)
        if top:
            df_top = pd.DataFrame([dict(r) for r in top])
            df_top["label"] = df_top["sku"].fillna("").apply(
                lambda x: (x[:16] + "…") if len(str(x)) > 16 else (x or "Sin SKU")
            )
            fig2 = px.bar(
                df_top, x="utilidad_total", y="label", orientation="h",
                color_discrete_sequence=["#D42B2B"],
                labels={"utilidad_total": "Utilidad ($)", "label": ""},
                height=260,
            )
            fig2.update_layout(
                margin=dict(l=0, r=0, t=8, b=0),
                plot_bgcolor="#ffffff", paper_bgcolor="#ffffff",
                font=dict(color="#1C2333", size=11),
                yaxis=dict(autorange="reversed", gridcolor="#F3F4F6"),
                xaxis=dict(gridcolor="#F3F4F6"),
            )
            fig2.update_traces(marker_line_width=0)
            st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("Sin datos de ventas.")

    st.markdown("")

    # ── Últimas OCs + Estado de stock ────────────────────────────────────────
    bcol1, bcol2 = st.columns([3, 2])

    with bcol1:
        st.markdown("#### Últimas órdenes de compra")
        ocs = db.ultimas_ocs(6)
        if ocs:
            df_oc = pd.DataFrame([dict(r) for r in ocs])
            df_oc.columns = ["ID", "Proveedor", "Fecha", "Productos", "Unidades", "Valor OC"]
            df_oc["Fecha"]    = df_oc["Fecha"].apply(lambda x: str(x)[:10])
            df_oc["Valor OC"] = df_oc["Valor OC"].apply(lambda x: f"${x:,.0f}")
            st.dataframe(df_oc, use_container_width=True, hide_index=True, height=250)
        else:
            st.info("Sin órdenes de compra registradas.")

    with bcol2:
        st.markdown("#### Estado del inventario")
        a1, a2 = st.columns(2)
        a1.metric("Lotes activos",  resumen["n_lotes_activos"])
        a2.metric("Lotes agotados", resumen["n_lotes_agotados"])
        st.markdown("")
        if resumen["n_lotes_agotados"] > 0:
            st.warning(f"⚠️ **{resumen['n_lotes_agotados']}** lote(s) sin stock")
        if resumen["n_lotes_bajo"] > 0:
            st.warning(f"📉 **{resumen['n_lotes_bajo']}** lote(s) con ≤ 3 unidades")
        if resumen["n_lotes_agotados"] == 0 and resumen["n_lotes_bajo"] == 0:
            st.success("✅ Stock en niveles normales")
        st.markdown("")
        # Mini gráfica donut estado
        if resumen["n_lotes_activos"] + resumen["n_lotes_agotados"] > 0:
            df_d = pd.DataFrame({
                "Estado": ["Activos", "Agotados"],
                "Lotes":  [resumen["n_lotes_activos"], resumen["n_lotes_agotados"]],
            })
            fig3 = px.pie(
                df_d, names="Estado", values="Lotes", hole=0.55,
                color="Estado",
                color_discrete_map={"Activos": "#3A5BA0", "Agotados": "#D42B2B"},
                height=180,
            )
            fig3.update_layout(
                margin=dict(l=0, r=0, t=0, b=0),
                paper_bgcolor="#ffffff",
                showlegend=True,
                legend=dict(font=dict(size=11)),
                font=dict(color="#1C2333"),
            )
            fig3.update_traces(textinfo="percent", textfont_size=12)
            st.plotly_chart(fig3, use_container_width=True, config={"displayModeBar": False})


# ═════════════════════════════════════════════════════════════════════════════
#  MÓDULO: ORDEN DE COMPRA
# ═════════════════════════════════════════════════════════════════════════════
def pagina_oc():
    st.title("📦 Nueva Orden de Compra")

    c1, c2 = st.columns([1, 2])
    with c1:
        proveedor = st.text_input("Proveedor", placeholder="Ej: Proveedor ABC",
                                  key="oc_proveedor")
    with c2:
        notas = st.text_input("Notas", placeholder="Opcional", key="oc_notas")

    st.markdown("---")
    st.markdown("#### Agregar producto")

    cols = st.columns([2.5, 1, 1.5])
    with cols[0]:
        sku_input = st.text_input("SKU / Barcode", key="oc_sku",
                                  placeholder="Escanea o escribe el SKU")
    with cols[1]:
        cantidad = st.number_input("Cantidad", min_value=1, value=1, step=1,
                                   key="oc_cant")
    with cols[2]:
        precio = st.number_input("Precio Compra $", min_value=0.0, value=0.0,
                                 step=0.01, format="%.2f", key="oc_precio")

    if st.session_state.oc_producto_actual:
        p = st.session_state.oc_producto_actual
        st.info(f"✔ **{p['nombre']}** — ID: `{p['id']}`  SKU: `{p['sku']}`")

    bc1, bc2 = st.columns([1, 1])
    with bc1:
        if st.button("🔍 Buscar producto", key="btn_oc_buscar"):
            sk = sku_input.strip()
            if not sk:
                st.warning("Ingresa un SKU o barcode.")
            else:
                with st.spinner("Buscando en WooCommerce…"):
                    try:
                        prod = (woo_api.buscar_producto_por_sku(sk) or
                                woo_api.buscar_producto_por_barcode(sk))
                        if prod:
                            st.session_state.oc_producto_actual = {
                                "id":     prod.get("id"),
                                "nombre": prod.get("name", ""),
                                "sku":    prod.get("sku", sk),
                            }
                            st.rerun()
                        else:
                            st.warning("❌ Producto no encontrado en WooCommerce.")
                    except Exception as e:
                        st.error(f"Error: {e}")

    with bc2:
        if st.button("➕ Agregar a OC", key="btn_oc_agregar", type="primary"):
            if not st.session_state.oc_producto_actual:
                st.warning("Busca un producto primero.")
            elif precio <= 0:
                st.warning("Ingresa un precio de compra mayor a 0.")
            else:
                p = st.session_state.oc_producto_actual
                st.session_state.oc_items.append({
                    "product_id":    p["id"],
                    "nombre":        p["nombre"],
                    "sku":           p["sku"],
                    "cantidad":      int(cantidad),
                    "precio_compra": float(precio),
                })
                st.session_state.oc_producto_actual = None
                st.rerun()

    st.markdown("---")
    if st.session_state.oc_items:
        st.markdown("#### Ítems de la OC")
        df_oc = pd.DataFrame(st.session_state.oc_items)
        st.dataframe(df_oc, use_container_width=True, hide_index=True)
        total = sum(i["cantidad"] * i["precio_compra"] for i in st.session_state.oc_items)
        st.metric("Total OC", f"${total:,.2f}")

        ba, bb = st.columns([1, 1])
        with ba:
            if st.button("✅ Guardar OC + Actualizar WooCommerce",
                         type="primary", key="btn_oc_guardar"):
                prov = proveedor.strip() or "Sin proveedor"
                with st.spinner("Guardando y actualizando stock en WooCommerce…"):
                    try:
                        id_oc = db.crear_orden_compra(prov, notas)
                        for item in st.session_state.oc_items:
                            db.crear_lote(id_oc, item["product_id"],
                                          item["sku"], item["cantidad"],
                                          item["precio_compra"])
                            woo_api.incrementar_stock(item["product_id"],
                                                      item["cantidad"])
                        n = len(st.session_state.oc_items)
                        st.session_state.oc_items.clear()
                        st.session_state.oc_producto_actual = None
                        # Invalidar caché de WooCommerce
                        _cargar_woo_cache.clear()
                        st.success(f"✅ OC #{id_oc} creada — {n} productos "
                                   "actualizados en WooCommerce.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")
        with bb:
            if st.button("🗑️ Limpiar lista", key="btn_oc_limpiar"):
                st.session_state.oc_items.clear()
                st.session_state.oc_producto_actual = None
                st.rerun()
    else:
        st.info("Sin ítems aún. Busca un producto y agrégalo.")


# ═════════════════════════════════════════════════════════════════════════════
#  MÓDULO: IMPORTAR VENTAS (FIFO)
# ═════════════════════════════════════════════════════════════════════════════
def pagina_ventas():
    st.title("🛒 Importar Ventas desde WooCommerce")

    col1, col2 = st.columns([2, 3])
    with col1:
        fecha_in = st.date_input("Desde fecha (vacío = todo el historial)",
                                 value=None, key="v_fecha")

    if st.button("🔄 Importar Ventas", type="primary", key="btn_v_importar"):
        desde = f"{fecha_in}T00:00:00" if fecha_in else None
        log: list[tuple[str, str]] = []     # (nivel, mensaje)
        with st.spinner("Conectando con WooCommerce…"):
            try:
                ordenes = woo_api.obtener_ordenes_completadas(desde_fecha=desde)
                log.append(("info", f"Órdenes encontradas: {len(ordenes)}"))
                resultado = fifo.importar_ordenes_woo(ordenes)
                log.append(("success", f"Procesadas: {len(resultado['procesadas'])}"))
                log.append(("info",
                             f"Omitidas (ya procesadas): {len(resultado['omitidas'])}"))
                if resultado["errores"]:
                    log.append(("warning",
                                 f"Errores ({len(resultado['errores'])}) — ver detalles:"))
                    for e in resultado["errores"]:
                        log.append(("warning",
                                     f"  Orden #{e['order_id']}: {e['error']}"))
            except Exception as e:
                log.append(("error", str(e)))
        st.session_state.log_ventas = log

    if st.session_state.log_ventas:
        st.markdown("#### Resultado")
        for nivel, msg in st.session_state.log_ventas:
            if nivel == "success":
                st.success(msg)
            elif nivel == "warning":
                st.warning(msg)
            elif nivel == "error":
                st.error(msg)
            else:
                st.info(msg)


# ═════════════════════════════════════════════════════════════════════════════
#  MÓDULO: ETIQUETAS
# ═════════════════════════════════════════════════════════════════════════════
def pagina_etiquetas():
    st.title("🏷️ Generador de Etiquetas (Excel)")

    cfg_path = Path(__file__).parent / "config.json"
    with open(cfg_path, encoding="utf-8") as f:
        cfg = json.load(f)
    meta_key = cfg.get("yith_barcode_meta_key", "_ywbc_barcode_value")

    c1, c2 = st.columns([2.5, 1])
    with c1:
        sku_et = st.text_input("SKU / Barcode", key="et_sku")
    with c2:
        cant_et = st.number_input("Cantidad etiquetas", min_value=1,
                                  value=1, step=1, key="et_cant")

    if st.session_state.et_producto_actual:
        p = st.session_state.et_producto_actual
        st.info(f"✔ **{p['nombre']}**  Barcode: `{p['barcode']}`")

    be1, be2 = st.columns([1, 1])
    with be1:
        if st.button("🔍 Buscar", key="btn_et_buscar"):
            with st.spinner("Buscando…"):
                try:
                    prod = (woo_api.buscar_producto_por_sku(sku_et.strip()) or
                            woo_api.buscar_producto_por_barcode(sku_et.strip()))
                    if prod:
                        bc = woo_api.get_barcode_de_producto(prod, meta_key)
                        st.session_state.et_producto_actual = {
                            "nombre":  prod.get("name", ""),
                            "sku":     prod.get("sku", sku_et),
                            "precio":  float(prod.get("price", 0)),
                            "barcode": bc or sku_et,
                        }
                        st.rerun()
                    else:
                        st.warning("Producto no encontrado.")
                except Exception as e:
                    st.error(f"Error: {e}")
    with be2:
        if st.button("➕ Agregar", key="btn_et_agregar", type="primary"):
            if not st.session_state.et_producto_actual:
                st.warning("Busca un producto primero.")
            else:
                p = st.session_state.et_producto_actual
                st.session_state.et_items.append({**p, "cantidad": int(cant_et)})
                st.session_state.et_producto_actual = None
                st.rerun()

    st.markdown("---")
    if st.session_state.et_items:
        st.markdown("#### Productos para etiquetar")
        df_et = pd.DataFrame(st.session_state.et_items)
        st.dataframe(df_et, use_container_width=True, hide_index=True)

        # Generar Excel con ruta temporal
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
                tmp_path = tmp.name
            etiq_mod.exportar_etiquetas(st.session_state.et_items, tmp_path)
            with open(tmp_path, "rb") as f:
                xlsx_bytes = f.read()
            os.unlink(tmp_path)
            st.download_button(
                label="📤 Descargar Excel de Etiquetas",
                data=xlsx_bytes,
                file_name="etiquetas.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
            )
        except Exception as e:
            st.error(f"Error al generar Excel: {e}")

        if st.button("🗑️ Limpiar lista", key="btn_et_limpiar"):
            st.session_state.et_items.clear()
            st.rerun()
    else:
        st.info("Sin ítems. Busca y agrega productos.")


# ═════════════════════════════════════════════════════════════════════════════
#  MÓDULO: ANÁLISIS
# ═════════════════════════════════════════════════════════════════════════════

# ── Helpers de color para DataFrames ─────────────────────────────────────────

def _color_stock(val):
    try:
        n = int(val)
        if n == 0:   return "color: #ff6b6b"
        if n <= 5:   return "color: #ffd93d"
        return "color: #6bcb77"
    except (ValueError, TypeError):
        return "color: #aaaaaa"


def _color_decision(val):
    v = str(val)
    if "RESURTIR"    in v: return "color: #6bcb77; font-weight:bold"
    if "MANTENER"    in v: return "color: #4fc3f7"
    if "PRECIO BAJO" in v: return "color: #ff4d4d; font-weight:bold"
    if "DESCARTAR"   in v: return "color: #ff6b6b"
    if "NICHO"       in v: return "color: #ce93d8"
    if "SUBIR"       in v or "REVISAR" in v: return "color: #ffd93d"
    return ""


def _color_rating(val):
    v = str(val)
    if "Rápido"  in v: return "color: #6bcb77"
    if "Medio"   in v: return "color: #ffd93d"
    if "Lento"   in v: return "color: #ff9f43"
    return ""


@st.dialog("📋 Crear OC — Stock sin asignar en WooCommerce", width="large")
def _dialogo_oc_woo():
    """
    Popup que muestra los productos cuyo stock en WooCommerce supera
    lo registrado en las OCs locales (stock huérfano).
    Solo las unidades en exceso (diff) se incluyen en la nueva OC.
    """
    huerfanos   = st.session_state.get("oc_woo_huerfanos", [])
    stock_local = st.session_state.get("oc_woo_stock_local", {})

    if not huerfanos:
        st.warning("Sin productos con stock huérfano.")
        return

    c1, c2 = st.columns([2, 1])
    with c1:
        prov_woc = st.text_input("Proveedor",
                                  value="Regularización stock WooCommerce",
                                  key="dlg_woc_proveedor")
    with c2:
        precio_def = st.number_input("Precio compra default $",
                                     min_value=0.0, value=0.0,
                                     step=100.0, format="%.2f",
                                     key="dlg_woc_precio_def")

    st.caption(
        "Solo se incluyen las **unidades sin asignar** (WooCommerce − OCs locales). "
        "Edita la columna **P. Compra $** fila por fila.")

    df_huerfanos = pd.DataFrame([{
        "ID":             p.get("id"),
        "Nombre":         p.get("name", ""),
        "SKU":            p.get("sku", "") or "—",
        "Stock WOO":      p.get("stock_quantity", 0),
        "Stock local":    stock_local.get(p.get("id"), 0),
        "Sin asignar":    (p.get("stock_quantity") or 0) - stock_local.get(p.get("id"), 0),
        "P. Compra":      precio_def,
    } for p in huerfanos])

    edited = st.data_editor(
        df_huerfanos,
        use_container_width=True,
        hide_index=True,
        height=min(len(huerfanos) * 35 + 60, 500),
        key="dlg_woc_editor",
        column_config={
            "ID":          st.column_config.NumberColumn("ID",           disabled=True),
            "Nombre":      st.column_config.TextColumn("Nombre",         disabled=True, width="large"),
            "SKU":         st.column_config.TextColumn("SKU",            disabled=True),
            "Stock WOO":   st.column_config.NumberColumn("Stock WOO",    disabled=True),
            "Stock local": st.column_config.NumberColumn("Stock local",  disabled=True),
            "Sin asignar": st.column_config.NumberColumn("Sin asignar ⚠️", disabled=True),
            "P. Compra":   st.column_config.NumberColumn(
                "P. Compra $",
                min_value=0.0,
                step=100.0,
                format="%.2f",
                help="Precio de compra unitario para esta OC",
            ),
        },
    )

    st.markdown("---")
    bc1, bc2 = st.columns([1, 1])
    with bc1:
        if st.button("✅ Crear OC de regularización", type="primary",
                     key="dlg_btn_crear"):
            with st.spinner("Guardando…"):
                try:
                    id_oc = db.crear_orden_compra(
                        prov_woc,
                        "OC de regularización — stock editado directamente en WooCommerce",
                    )
                    guardados = 0
                    for _, row in edited.iterrows():
                        cant = int(row["Sin asignar"])
                        if cant <= 0:
                            continue
                        db.crear_lote(
                            id_oc,
                            int(row["ID"]),
                            "" if row["SKU"] == "—" else str(row["SKU"]),
                            cant,
                            float(row["P. Compra"]),
                        )
                        guardados += 1
                    st.success(f"✅ OC #{id_oc} creada — {guardados} productos regularizados.")
                    # Limpiar flags y forzar re-carga del caché
                    _cargar_woo_cache.clear()
                    st.session_state.pop("oc_woo_huerfanos", None)
                    st.session_state.pop("oc_woo_stock_local", None)
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
    with bc2:
        if st.button("Cancelar", key="dlg_btn_cancelar"):
            st.session_state.pop("oc_woo_huerfanos", None)
            st.session_state.pop("oc_woo_stock_local", None)
            st.rerun()


def pagina_analisis():
    st.title("📊 Análisis")

    (tab_inv, tab_ut, tab_woo,
     tab_surtido, tab_dec) = st.tabs([
        "📦 Inventario Actual",
        "📊 Utilidades",
        "🌐 Stock WooCommerce",
        "🔄 Surtido",
        "🎯 Decisiones",
    ])

    # ── Tab: Inventario ───────────────────────────────────────────────────────
    with tab_inv:
        if st.button("🔄 Cargar Inventario", key="btn_inv"):
            st.cache_data.clear()
        lotes = db.listar_todos_lotes()
        if lotes:
            filas = [dict(row) for row in lotes]
            for r in filas:
                r["valor_stock"] = float(r.get("cantidad_actual", 0) *
                                         r.get("precio_compra_unitario", 0))
            df_inv = pd.DataFrame(filas, columns=[
                "id_lote", "id_oc", "proveedor", "fecha_ingreso",
                "product_id", "sku", "cantidad_inicial",
                "cantidad_actual", "precio_compra_unitario", "valor_stock",
            ])
            df_inv.columns = ["Lote", "OC", "Proveedor", "Fecha OC",
                               "Product ID", "SKU", "Ini.", "Actual",
                               "P. Compra", "Valor Stock"]
            valor_total = df_inv["Valor Stock"].sum()
            st.metric("Valor total en stock", f"${valor_total:,.2f}")
            st.dataframe(df_inv, use_container_width=True, hide_index=True, height=600)
            _df_download(df_inv, "inventario_lotes.xlsx")
        else:
            st.info("Sin lotes registrados. Crea una Orden de Compra primero.")

    # ── Tab: Utilidades ───────────────────────────────────────────────────────
    with tab_ut:
        ventas = db.listar_ventas()
        if ventas:
            filas_v = [dict(row) for row in ventas]
            df_ut = pd.DataFrame(filas_v)
            df_ut.rename(columns={
                "fecha_venta": "Fecha", "order_id_woo": "Orden WOO",
                "product_id": "Product ID", "sku": "SKU",
                "cantidad_vendida": "Cant.", "precio_venta_unitario": "P. Venta",
                "costo_unitario": "Costo Unit.", "utilidad_neta": "Utilidad Neta",
            }, inplace=True)
            utilidad_total = df_ut["Utilidad Neta"].sum()
            col_m1, col_m2, col_m3 = st.columns(3)
            col_m1.metric("Utilidad Total", f"${utilidad_total:,.2f}")
            col_m2.metric("Ventas procesadas", len(df_ut))
            col_m3.metric("Ticket promedio",
                          f"${df_ut['P. Venta'].mean():,.2f}" if len(df_ut) else "$0")
            st.dataframe(df_ut, use_container_width=True, hide_index=True, height=600)
            _df_download(df_ut, "utilidades.xlsx")
        else:
            st.info("Sin ventas procesadas. Ve a 'Importar Ventas' primero.")

    # ── Tab: Stock WooCommerce ────────────────────────────────────────────────
    with tab_woo:
        col_w1, col_w2 = st.columns([2, 3])
        with col_w1:
            if st.button("🔄 Recargar desde WooCommerce", key="btn_woo_reload"):
                _cargar_woo_cache.clear()
                st.rerun()
        with col_w2:
            buscar_woo = st.text_input("Buscar por nombre o SKU",
                                       key="woo_buscar",
                                       placeholder="Escribe para filtrar…")

        with st.spinner("Cargando productos…"):
            productos_woo = _cargar_woo_cache()
            st.session_state.woo_cache = productos_woo

        if productos_woo:
            filas_woo = []
            for p in productos_woo:
                nombre = p.get("name", "") or ""
                sku    = p.get("sku", "") or ""
                if buscar_woo:
                    t = buscar_woo.lower()
                    if t not in nombre.lower() and t not in sku.lower():
                        continue
                stock        = p.get("stock_quantity")
                manage_stock = p.get("manage_stock", False)
                stock_str    = str(stock) if (manage_stock and stock is not None) else "—"
                filas_woo.append({
                    "ID":             p.get("id"),
                    "Nombre":         nombre,
                    "SKU":            sku or "sin SKU",
                    "Precio":         float(p.get("price") or 0),
                    "Stock":          stock_str,
                    "Estado":         p.get("stock_status", ""),
                    "Gestiona Stock": "Sí" if manage_stock else "No",
                })
            df_woo = pd.DataFrame(filas_woo)
            n_agotados = sum(1 for r in filas_woo if r["Stock"] == "0"
                             or r["Estado"] == "outofstock")
            col_w3, col_w4 = st.columns(2)
            col_w3.metric("Productos mostrados", len(df_woo))
            col_w4.metric("Agotados", n_agotados)

            # Color en columna Stock
            styled = (df_woo.style
                      .map(_color_stock, subset=["Stock"])
                      .format({"Precio": "${:.2f}"}))
            st.dataframe(styled, use_container_width=True, hide_index=True,
                         height=620)
            _df_download(df_woo, "stock_woocommerce.xlsx")

            # ── Detectar stock huérfano y ofrecer crear OC ───────────────
            stock_local = db.stock_local_por_producto()
            huerfanos = [
                p for p in productos_woo
                if p.get("manage_stock")
                and (p.get("stock_quantity") or 0) > 0
                and (p.get("stock_quantity") or 0) > stock_local.get(p.get("id"), 0)
            ]

            if huerfanos:
                diff_total = sum(
                    (p.get("stock_quantity") or 0) - stock_local.get(p.get("id"), 0)
                    for p in huerfanos
                )
                st.warning(
                    f"⚠️ **{len(huerfanos)} producto(s)** tienen más stock en WooCommerce "
                    f"que en las OCs registradas ({diff_total} unidades sin asignar). "
                    "Crea una OC para regularizarlos.",
                    icon="⚠️",
                )
                if st.button("📋 Crear OC para stock sin asignar",
                             type="primary", key="btn_abrir_oc_woo"):
                    st.session_state["oc_woo_huerfanos"] = huerfanos
                    st.session_state["oc_woo_stock_local"] = stock_local
                    _dialogo_oc_woo()
            else:
                st.success("✅ Todo el stock de WooCommerce tiene OC asignada.",
                           icon="✅")
        else:
            st.info("Pulsa 'Recargar desde WooCommerce' para cargar los productos.")

    # ── Tab: Surtido ──────────────────────────────────────────────────────────
    with tab_surtido:
        st.markdown("Analiza productos **agotados** que han tenido ventas recientes.")
        cs1, cs2 = st.columns(2)
        with cs1:
            s_desde = st.date_input("Desde (opcional)", value=None, key="s_desde")
        with cs2:
            s_hasta = st.date_input("Hasta (opcional)", value=None, key="s_hasta")

        if st.button("📊 Analizar surtido", type="primary", key="btn_surtido"):
            desde_api = f"{s_desde}T00:00:00" if s_desde else None
            hasta_api = f"{s_hasta}T23:59:59" if s_hasta else None
            hoy       = dt_date.today()
            d_hasta   = s_hasta or hoy
            d_desde   = s_desde
            days      = max((d_hasta - d_desde).days, 1) if d_desde else 365

            with st.spinner("Obteniendo órdenes de WooCommerce…"):
                try:
                    ordenes = woo_api.obtener_ordenes_rango(desde_api, hasta_api)
                    ventas_s: dict[int, dict] = {}
                    for orden in ordenes:
                        for item in orden.get("line_items", []):
                            pid = item.get("product_id")
                            if not pid:
                                continue
                            qty = item.get("quantity", 0)
                            if pid not in ventas_s:
                                ventas_s[pid] = {
                                    "nombre": item.get("name", ""),
                                    "sku": item.get("sku", ""),
                                    "precio": float(item.get("price") or 0),
                                    "total": 0,
                                }
                            ventas_s[pid]["total"] += qty

                    if not ventas_s:
                        st.warning("Sin ventas en el período seleccionado.")
                    else:
                        prods_data = woo_api.obtener_productos_por_ids(list(ventas_s.keys()))
                        sin_stock = []
                        for pid, v in ventas_s.items():
                            prod = prods_data.get(pid)
                            if not prod:
                                continue
                            sq     = prod.get("stock_quantity")
                            estatus = prod.get("stock_status", "")
                            agotado = (estatus == "outofstock") or \
                                      (sq is not None and int(sq) == 0)
                            if not agotado:
                                continue
                            sin_stock.append({
                                "ID":          pid,
                                "Nombre":      prod.get("name") or v["nombre"],
                                "SKU":         prod.get("sku") or v["sku"] or "—",
                                "Precio":      float(prod.get("price") or v["precio"] or 0),
                                "Vendidos":    v["total"],
                                "_vel":        v["total"] / days * 7,
                                "Stock":       sq if sq is not None else 0,
                            })
                        sin_stock.sort(key=lambda x: x["_vel"], reverse=True)
                        n = len(sin_stock)
                        for i, p in enumerate(sin_stock):
                            pos = i / max(n - 1, 1)
                            if pos <= 0.33:
                                rating = "⭐⭐⭐ Rápido"
                            elif pos <= 0.66:
                                rating = "⭐⭐ Medio"
                            else:
                                rating = "⭐ Lento"
                            p["Vel/Sem"] = round(p.pop("_vel"), 2)
                            p["Calificación"] = rating
                        st.session_state["surtido_df"] = pd.DataFrame(
                            sin_stock,
                            columns=["ID", "Nombre", "SKU", "Precio",
                                     "Vendidos", "Vel/Sem", "Calificación", "Stock"],
                        )
                except Exception as e:
                    st.error(f"Error: {e}")

        if "surtido_df" in st.session_state and not st.session_state.surtido_df.empty:
            df_s = st.session_state.surtido_df
            st.info(f"{len(df_s)} productos agotados para surtir")
            styled_s = (df_s.style
                        .map(_color_rating, subset=["Calificación"])
                        .format({"Precio": "${:,.0f}", "Vel/Sem": "{:.2f}"}))
            st.dataframe(styled_s, use_container_width=True, hide_index=True, height=600)
            _df_download(df_s, "surtido.xlsx")

    # ── Tab: Decisiones ───────────────────────────────────────────────────────
    with tab_dec:
        st.markdown(
            "Análisis de rentabilidad por producto — combina **velocidad**, "
            "**margen FIFO** y **utilidad** para generar recomendaciones.")
        cd1, cd2 = st.columns(2)
        with cd1:
            dec_desde = st.date_input("Desde (opcional)", value=None, key="dec_desde")
        with cd2:
            dec_hasta = st.date_input("Hasta (opcional)", value=None, key="dec_hasta")

        if st.button("🔍 Analizar decisiones", type="primary", key="btn_dec"):
            desde_db = f"{dec_desde}T00:00:00" if dec_desde else None
            hasta_db = f"{dec_hasta}T23:59:59" if dec_hasta else None
            hoy      = dt_date.today()

            datos = db.analisis_por_producto(desde_db, hasta_db)
            if not datos:
                st.warning("Sin ventas procesadas. Ve a 'Importar Ventas' primero.")
            else:
                woo_nombres = {p.get("id"): p.get("name", "")
                               for p in st.session_state.woo_cache}
                productos = []
                for r in datos:
                    pid               = r["product_id"]
                    total_vendidos    = r["total_vendidos"] or 0
                    primera_str       = (r["primera_venta"] or "")[:10]
                    precio_venta_prom = float(r["precio_venta_prom"] or 0)
                    costo_unit_prom   = float(r["costo_unit_prom"] or 0)
                    utilidad_total    = float(r["utilidad_total"] or 0)
                    stock_local       = int(r["stock_local"] or 0)
                    sku               = r["sku"] or "—"

                    try:
                        primera    = datetime.strptime(primera_str, "%Y-%m-%d").date()
                        limite     = (datetime.strptime(str(dec_hasta), "%Y-%m-%d").date()
                                      if dec_hasta else hoy)
                        periodo_d  = max((limite - primera).days, 1)
                    except (ValueError, TypeError):
                        periodo_d  = 30

                    vel_sem = total_vendidos / periodo_d * 7
                    margen  = ((precio_venta_prom - costo_unit_prom) /
                                precio_venta_prom * 100
                                if precio_venta_prom > 0 and costo_unit_prom > 0
                                else None)
                    util_sem    = utilidad_total / periodo_d * 7
                    cobertura_d = (stock_local / (vel_sem / 7)
                                   if vel_sem > 0 else None)
                    productos.append({
                        "id":             pid,
                        "sku":            sku,
                        "precio":         precio_venta_prom,
                        "margen_pct":     margen,
                        "vel_sem":        vel_sem,
                        "util_sem":       util_sem,
                        "stock":          stock_local,
                        "cobertura_dias": cobertura_d,
                    })

                # Normalización 0-100
                def _norm(vals):
                    fil = [v for v in vals if v is not None]
                    if not fil: return [50] * len(vals)
                    lo, hi = min(fil), max(fil)
                    rng = hi - lo
                    return [(50 if v is None else (50 if rng == 0
                             else (v - lo) / rng * 100)) for v in vals]

                vel_n    = _norm([p["vel_sem"]    for p in productos])
                margin_n = _norm([p["margen_pct"] for p in productos])
                profit_n = _norm([p["util_sem"]   for p in productos])

                filas_dec = []
                for i, p in enumerate(productos):
                    comp = (0.35 * vel_n[i] + 0.35 * margin_n[i]
                            + 0.30 * profit_n[i])
                    urgente = (p["cobertura_dias"] is not None
                               and 0 < p["cobertura_dias"] < 14)
                    prefix  = "⚡ " if urgente else ""
                    m       = p["margen_pct"]

                    if m is None:
                        if comp >= 70:   reco = f"{prefix}🟢 RESURTIR"
                        elif comp >= 40: reco = f"{prefix}🔵 MANTENER"
                        else:            reco = "🟡 SIN COSTO FIFO"
                    elif m <= 0:         reco = "🔴 PRECIO BAJO"
                    elif comp >= 70 and m >= 25: reco = f"{prefix}🟢 RESURTIR"
                    elif comp >= 70:              reco = f"{prefix}🟡 SUBIR PRECIO"
                    elif comp >= 40 and m >= 25:  reco = f"{prefix}🔵 MANTENER"
                    elif comp >= 40:              reco = "🟡 REVISAR MARGEN"
                    elif m >= 40:                 reco = "🟣 NICHO"
                    else:                         reco = "🔴 DESCARTAR"

                    filas_dec.append({
                        "ID":          p["id"],
                        "Nombre":      woo_nombres.get(p["id"]) or f"(ID:{p['id']})",
                        "SKU":         p["sku"],
                        "P. Venta":    p["precio"],
                        "Margen %":    f"{m:.1f}%" if m is not None else "S/D",
                        "Vel/Sem":     round(p["vel_sem"], 2),
                        "Utilid/Sem":  round(p["util_sem"], 2),
                        "Stock":       p["stock"],
                        "Cobertura":   (f"{p['cobertura_dias']:.0f}d"
                                        if p["cobertura_dias"] is not None else "—"),
                        "Score":       round(comp),
                        "Recomendación": reco,
                    })

                filas_dec.sort(key=lambda x: x["Score"], reverse=True)
                df_dec = pd.DataFrame(filas_dec)
                st.session_state["dec_df"] = df_dec

        if "dec_df" in st.session_state and not st.session_state.dec_df.empty:
            df_dec = st.session_state.dec_df
            n_res = (df_dec["Recomendación"].str.contains("RESURTIR")).sum()
            n_des = (df_dec["Recomendación"].str.contains("DESCARTAR|PRECIO BAJO",
                                                           regex=True)).sum()
            cm1, cm2, cm3 = st.columns(3)
            cm1.metric("Productos analizados", len(df_dec))
            cm2.metric("🟢 A resurtir", int(n_res))
            cm3.metric("🔴 A descartar/revisar", int(n_des))

            styled_d = (df_dec.style
                        .map(_color_decision, subset=["Recomendación"])
                        .format({"P. Venta": "${:,.0f}",
                                 "Utilid/Sem": "${:,.0f}"}))
            st.dataframe(styled_d, use_container_width=True, hide_index=True, height=600)
            _df_download(df_dec, "decisiones_inventario.xlsx")

            # Leyenda
            st.markdown("""
**Leyenda de recomendaciones:**
🟢 **RESURTIR** — Alta velocidad + buen margen → reorden inmediato   |
🔵 **MANTENER** — Venta estable, bien posicionado   |
🟡 **SUBIR PRECIO** — Rota rápido pero deja poco margen   |
🟡 **REVISAR MARGEN** — Ventas moderadas, margen ajustado   |
🟣 **NICHO** — Lento pero muy rentable, no sobre-stockear   |
🔴 **DESCARTAR** — Bajo volumen y bajo margen, liberar capital   |
🔴 **PRECIO BAJO** — Se vende en pérdida   |
⚡ — Cobertura de stock < 14 días, necesita reorden urgente
""")


# ═════════════════════════════════════════════════════════════════════════════
#  ROUTER
# ═════════════════════════════════════════════════════════════════════════════
if PAGINA == "🏠 Inicio":
    pagina_inicio()
elif PAGINA == "📦 Orden de Compra":
    pagina_oc()
elif PAGINA == "🛒 Importar Ventas":
    pagina_ventas()
elif PAGINA == "🏷️ Etiquetas":
    pagina_etiquetas()
elif PAGINA == "📊 Análisis":
    pagina_analisis()
