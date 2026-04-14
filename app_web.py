"""
app_web.py — Versión web de WooPosAdmin usando Streamlit.
Desplegable en VPS. Todos los módulos de negocio se reutilizan sin cambios.
Comando de arranque: streamlit run app_web.py --server.port 8501
"""
import os
import json
import logging
import hashlib
import secrets
import tempfile
import warnings
from io import BytesIO
from pathlib import Path
from datetime import date as dt_date, datetime

import pandas as pd
import plotly.express as px
import streamlit as st

# ── Logger de sesiones ──────────────────────────────────────────────────────────
_LOG_PATH = Path(__file__).parent / "sessions.log"
_slog = logging.getLogger("dyo_sessions")
if not _slog.handlers:
    _sh = logging.FileHandler(str(_LOG_PATH), encoding="utf-8")
    _sh.setFormatter(logging.Formatter("%(asctime)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    _slog.addHandler(_sh)
    _slog.setLevel(logging.INFO)

warnings.filterwarnings("ignore")

import db
import woo_api
import fifo
import etiquetas as etiq_mod

# ── Cargar configuración ────────────────────────────────────────────────────────
_CONFIG_PATH = Path(__file__).parent / "config.json"
_CONFIG: dict = json.loads(_CONFIG_PATH.read_text(encoding="utf-8")) if _CONFIG_PATH.exists() else {}

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
_es_sesion_nueva = "autenticado" not in st.session_state
_DEFAULTS = {
    "oc_items":           [],
    "oc_producto_actual": None,
    "oc_guardando":       False,
    "oc_iva_incluido":    False,
    "et_items":           [],
    "et_producto_actual": None,
    "et_oc_items":        None,
    "et_oc_error":        None,
    "et_oc_sin":          [],
    "et_prod_encontrado": None,
    "et_prod_error":      None,
    "et_prod_items":      None,
    "woo_cache":          [],
    "log_ventas":         [],
    "dec_rows":           [],
    "autenticado":        False,
    "usuario_actual":     "",
    "pagina_actual":      "🏠 Inicio",
    "_session_start":     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
}
for _k, _v in _DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

if _es_sesion_nueva:
    _slog.info("NUEVA_SESION | WebSocket nuevo (session_state vacío)")

# ── Autenticación ─────────────────────────────────────────────────────────────

def _verificar_password(password: str, stored: str) -> bool:
    """Verifica PBKDF2-SHA256. Formato: pbkdf2:sha256:<iter>$<hex_salt>$<hex_hash>"""
    try:
        algo_info, salt_hex, hash_hex = stored.split("$")
        _, hash_name, iterations = algo_info.split(":")
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
        computed = hashlib.pbkdf2_hmac(
            hash_name, password.encode("utf-8"), salt, int(iterations)
        )
        return secrets.compare_digest(computed, expected)
    except Exception:
        return False


def _pagina_login():
    st.markdown(
        """<style>section[data-testid="stSidebar"]{display:none!important;}</style>""",
        unsafe_allow_html=True,
    )
    _, col, _ = st.columns([1, 1.4, 1])
    with col:
        _logo_p = Path(__file__).parent / "Logo Descuentos y ofertas" / "Logo.png"
        if _logo_p.exists():
            lc1, lc2, lc3 = st.columns([1, 1, 1])
            with lc2:
                st.image(str(_logo_p), width=80)
        st.markdown(
            """
            <div style="text-align:center;margin:0.75rem 0 1.75rem;">
                <div style="font-size:1.4rem;font-weight:700;color:#1C2333;">WooAdmin</div>
                <div style="font-size:0.82rem;color:#9CA3AF;letter-spacing:0.04em;"
                >DESCUENTOS Y OFERTAS</div>
            </div>""",
            unsafe_allow_html=True,
        )
        with st.form("_login_form"):
            _usr = st.text_input("Usuario")
            _pwd = st.text_input("Contraseña", type="password")
            _ok  = st.form_submit_button(
                "Entrar", use_container_width=True, type="primary"
            )
        if _ok:
            _usuarios = _CONFIG.get("usuarios", {})
            if not _usuarios:
                st.error(
                    "Sin usuarios configurados. "
                    "Ejecuta `setup_usuario.py` en el servidor y reinicia la app."
                )
            elif _usr in _usuarios and _verificar_password(_pwd, _usuarios[_usr]["hash"]):
                _slog.info(f"LOGIN | usuario={_usr}")
                st.session_state.autenticado    = True
                st.session_state.usuario_actual = _usr
                st.rerun()
            else:
                _slog.info(f"LOGIN_FALLIDO | usuario={_usr}")
                st.error("Usuario o contraseña incorrectos.")


if not st.session_state.autenticado:
    _pagina_login()
    st.stop()

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
    try:
        return woo_api.get_todos_productos()
    except Exception as e:
        msg = str(e)
        if "404" in msg:
            st.error(
                "**WooCommerce REST API no disponible (404).**\n\n"
                "Ve a **Panel WP → Ajustes → Enlaces permanentes** y presiona "
                "**Guardar cambios** (aunque ya esté configurado). "
                "Esto regenera las reglas del REST API.",
                icon="🔌",
            )
        else:
            st.error(f"Error al conectar con WooCommerce: {e}", icon="🔌")
        return []


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
            "💰 Finanzas",
        ],
        key="pagina_actual",
        label_visibility="collapsed",
    )
    st.markdown("---")
    st.caption("Gestión de Inventario FIFO\nDescuentos y Ofertas")
    st.markdown("---")
    st.caption(f"👤 {st.session_state.usuario_actual}")
    st.caption(f"🕒 Sesión: {st.session_state._session_start}")
    if st.button("🔒 Cerrar sesión", key="btn_logout", use_container_width=True):
        _slog.info(f"LOGOUT | usuario={st.session_state.usuario_actual}")
        st.session_state.autenticado   = False
        st.session_state.usuario_actual = ""
        st.rerun()


# ═════════════════════════════════════════════════════════════════════════════
#  MÓDULO: INICIO
# ═════════════════════════════════════════════════════════════════════════════
def pagina_inicio():
    from datetime import date as _date
    st.title("Panel de Control")

    resumen = db.resumen_home()

    # ── KPIs ─────────────────────────────────────────────────────────────
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Valor en Stock",          f"${resumen['valor_stock']:,.0f}")
    k2.metric("Órdenes de Compra",       resumen["n_ocs"])
    k3.metric("Ventas WooCommerce",      resumen["n_ordenes_woo"])
    k4.metric("Utilidad Neta Total",     f"${resumen['utilidad_total']:,.0f}")
    k5.metric("Gastos este mes",         f"${resumen['gastos_mes']:,.0f}")

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

    # ── Importar OC desde Excel ───────────────────────────────────────────────
    with st.expander("📂 Cargar OC desde Excel"):
        st.caption(
            "Sube un Excel exportado desde esta pantalla. "
            "Columnas requeridas: **product_id, nombre, sku, cantidad, precio_compra**"
        )
        archivo = st.file_uploader("Selecciona el archivo .xlsx",
                                   type=["xlsx"], key="oc_upload")
        if archivo:
            try:
                df_imp = pd.read_excel(archivo, dtype={"product_id": int,
                                                        "cantidad": int,
                                                        "precio_compra": float})
                cols_req = {"product_id", "nombre", "sku", "cantidad", "precio_compra"}
                faltantes = cols_req - set(df_imp.columns.str.lower())
                if faltantes:
                    st.error(f"Faltan columnas: {', '.join(faltantes)}")
                else:
                    df_imp.columns = df_imp.columns.str.lower()
                    nuevos = []
                    for _, row in df_imp.iterrows():
                        nuevos.append({
                            "product_id":    int(row["product_id"]),
                            "nombre":        str(row["nombre"]),
                            "sku":           str(row["sku"]),
                            "cantidad":      int(row["cantidad"]),
                            "precio_compra": float(row["precio_compra"]),
                        })
                    if st.button(f"✅ Cargar {len(nuevos)} producto(s) a la OC",
                                 type="primary", key="btn_oc_import_confirm"):
                        st.session_state.oc_items = nuevos
                        st.success(f"{len(nuevos)} productos cargados.")
                        st.rerun()
            except Exception as e:
                st.error(f"Error al leer el archivo: {e}")

    st.markdown("---")
    st.markdown("#### Agregar producto")

    # ── Catálogo WooCommerce (cacheado) ───────────────────────────────────────
    catalogo = _cargar_woo_cache()
    if not catalogo:
        st.warning("No se pudo cargar el catálogo de WooCommerce. "
                   "Verifica la conexión y recarga la página.")
        catalogo = []

    # Construir opciones: "SKU — Nombre del producto"
    # El primer elemento es el placeholder
    _PLACEHOLDER = "— Selecciona un producto —"
    opciones_labels = [_PLACEHOLDER] + [
        f"{p.get('sku', '?')} — {p.get('name', '?')}"
        for p in catalogo
    ]
    # Mapa label → producto
    _cat_map = {
        f"{p.get('sku', '?')} — {p.get('name', '?')}": p
        for p in catalogo
    }

    sel_label = st.selectbox(
        "Buscar producto (SKU o nombre)",
        options=opciones_labels,
        index=0,
        key="oc_sel_producto",
        help="Escribe el SKU o parte del nombre para filtrar",
    )

    # Cuando el usuario selecciona un producto real, guardarlo
    if sel_label != _PLACEHOLDER:
        prod_sel = _cat_map.get(sel_label)
        if prod_sel:
            st.session_state.oc_producto_actual = {
                "id":     prod_sel.get("id"),
                "nombre": prod_sel.get("name", ""),
                "sku":    prod_sel.get("sku", ""),
            }
    else:
        # Sólo limpiar si el usuario volvió al placeholder manualmente
        if st.session_state.oc_producto_actual and not st.session_state.get("_oc_just_added"):
            pass  # Conservar selección hasta que se agregue o limpie

    cols = st.columns([1, 1.5, 1])
    with cols[0]:
        cantidad = st.number_input("Cantidad", min_value=1, value=1, step=1,
                                   key="oc_cant")
    with cols[1]:
        precio = st.number_input("Precio Compra $", min_value=0.0, value=0.0,
                                 step=0.01, format="%.2f", key="oc_precio")
    with cols[2]:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        iva_incluido = st.checkbox(
            "Precio IVA incluido",
            key="oc_iva_incluido",
            help="Marca si el precio que ingresas YA incluye el 19% de IVA. "
                 "Si no está marcado, se sumará el 19% automáticamente.",
        )

    # Calcular precio final e IVA unitario
    _IVA = 0.19
    if iva_incluido:
        precio_final   = precio
        iva_unitario   = round(precio - precio / (1 + _IVA), 2)
        precio_sin_iva = round(precio / (1 + _IVA), 2)
    else:
        precio_final   = round(precio * (1 + _IVA), 2)
        iva_unitario   = round(precio * _IVA, 2)
        precio_sin_iva = precio

    if precio > 0:
        if iva_incluido:
            st.caption(f"Base: ${precio_sin_iva:,.2f}  +  IVA: ${iva_unitario:,.2f}  =  **${precio_final:,.2f}**")
        else:
            st.caption(f"${precio:,.2f}  +  19% IVA (${iva_unitario:,.2f})  =  **${precio_final:,.2f}**")

    if st.session_state.oc_producto_actual:
        p = st.session_state.oc_producto_actual
        st.info(f"✔ **{p['nombre']}** — WC ID: `{p['id']}`  SKU: `{p['sku']}`")

    if st.button("➕ Agregar a OC", key="btn_oc_agregar", type="primary"):
        if not st.session_state.oc_producto_actual:
            st.warning("Selecciona un producto primero.")
        elif precio <= 0:
            st.warning("Ingresa un precio de compra mayor a 0.")
        else:
            p = st.session_state.oc_producto_actual
            st.session_state.oc_items.append({
                "product_id":    p["id"],
                "nombre":        p["nombre"],
                "sku":           p["sku"],
                "cantidad":      int(cantidad),
                "precio_compra": float(precio_final),
                "iva_unitario":  float(iva_unitario),
            })
            st.session_state.oc_producto_actual = None
            st.rerun()

    st.markdown("---")
    if st.session_state.oc_items:
        st.markdown("#### Ítems de la OC")
        df_oc = pd.DataFrame(st.session_state.oc_items)
        # Rellenar iva_unitario en items viejos que no lo tengan
        if "iva_unitario" not in df_oc.columns:
            df_oc["iva_unitario"] = 0.0
        df_oc_disp = df_oc[["sku", "nombre", "cantidad", "iva_unitario", "precio_compra"]].copy()
        df_oc_disp["iva_unitario"]  = df_oc_disp["iva_unitario"].apply(lambda x: f"${x:,.2f}")
        df_oc_disp["precio_compra"] = df_oc_disp["precio_compra"].apply(lambda x: f"${x:,.2f}")
        df_oc_disp.columns = ["SKU", "Nombre", "Cantidad", "IVA unitario", "Precio c/IVA"]
        # Columna de botones eliminar por fila
        for i, row in enumerate(st.session_state.oc_items):
            c1, c2, c3, c4, c5, c_del = st.columns([1.2, 2.5, 0.8, 1.2, 1.2, 0.6])
            c1.caption(row["sku"])
            c2.caption(row["nombre"])
            c3.caption(str(row["cantidad"]))
            c4.caption(f"${row.get('iva_unitario', 0):,.2f}")
            c5.caption(f"${row['precio_compra']:,.2f}")
            if c_del.button("🗑️", key=f"del_item_{i}", help="Eliminar este ítem"):
                st.session_state.oc_items.pop(i)
                st.rerun()
        st.markdown("")
        total     = sum(i["cantidad"] * i["precio_compra"] for i in st.session_state.oc_items)
        total_iva = sum(i["cantidad"] * i.get("iva_unitario", 0) for i in st.session_state.oc_items)
        mc1, mc2 = st.columns(2)
        mc1.metric("Total OC (con IVA)", f"${total:,.2f}")
        mc2.metric("IVA total de la OC",  f"${total_iva:,.2f}")

        ba, bb, bc = st.columns([2, 1, 1])
        with ba:
            guardando = st.session_state.get("oc_guardando", False)
            if guardando:
                st.warning("⏳ **Guardando OC y actualizando WooCommerce… espera, no cierres ni recargues.**",
                           icon="⏳")
            elif st.button("✅ Guardar OC + Actualizar WooCommerce",
                           type="primary", key="btn_oc_guardar",
                           disabled=guardando):
                st.session_state["oc_guardando"] = True
                st.rerun()

        # Ejecutar el guardado en el siguiente ciclo (cuando oc_guardando=True)
        if st.session_state.get("oc_guardando"):
            prov = proveedor.strip() or "Sin proveedor"
            try:
                total_iva_oc = sum(
                    i["cantidad"] * i.get("iva_unitario", 0)
                    for i in st.session_state.oc_items
                )
                id_oc = db.crear_orden_compra(prov, notas, total_iva_oc)
                for item in st.session_state.oc_items:
                    db.crear_lote(id_oc, item["product_id"],
                                  item["sku"], item["cantidad"],
                                  item["precio_compra"])
                    woo_api.incrementar_stock(item["product_id"],
                                              item["cantidad"])
                n = len(st.session_state.oc_items)
                st.session_state.oc_items.clear()
                st.session_state.oc_producto_actual = None
                st.session_state["oc_guardando"] = False
                _cargar_woo_cache.clear()
                st.success(f"✅ OC #{id_oc} creada — {n} productos actualizados en WooCommerce.")
                st.rerun()
            except Exception as e:
                st.session_state["oc_guardando"] = False
                st.error(f"Error: {e}")
        with bb:
            _df_download(
                pd.DataFrame(st.session_state.oc_items),
                "oc_borrador.xlsx",
                label="📥 Exportar Excel",
            )
        with bc:
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

    with st.expander("ℹ️ ¿Qué hace esta pestaña?", expanded=False):
        st.markdown("""
**Esta pestaña aplica el método FIFO al historial de ventas de WooCommerce.**

1. Descarga las órdenes *completadas* desde tu tienda WooCommerce.
2. Por cada producto vendido, descuenta unidades del lote de compra más antiguo
   disponible y registra el costo real de venta.
3. Así puedes ver la **utilidad neta real** por venta en la pestaña *Utilidades*.

**¿Por qué aparecen errores?**
Los errores significan que ese producto nunca tuvo una **Orden de Compra registrada**
aquí. Sin OC no hay lote de compra, y sin lote no se puede calcular el costo FIFO.
Solución: ve a **Órdenes de Compra**, registra la OC para esos productos y vuelve a
importar — las órdenes con errores se reintentarán automáticamente.

> Las órdenes sin errores se marcan como procesadas y no se duplican.
        """)

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
                n_err = len(resultado["errores"])
                if n_err:
                    # Ordenar errores por tipo para mostrar resumen primero
                    sin_lote = [e for e in resultado["errores"]
                                if "no hay lotes" in e["error"]]
                    sin_stock = [e for e in resultado["errores"]
                                 if "insuficiente" in e["error"]]
                    otros = [e for e in resultado["errores"]
                             if e not in sin_lote and e not in sin_stock]

                    log.append(("warning",
                                f"⚠️ {n_err} producto(s) no pudieron costearse "
                                f"(sin OC registrada). Esas órdenes quedan pendientes "
                                f"para reintento."))
                    if sin_lote:
                        prods_sin_oc = sorted({e["error"].split("Producto ")[1].split(":")[0]
                                               for e in sin_lote})
                        log.append(("warning",
                                    f"Sin OC → Product IDs: {', '.join(prods_sin_oc)}"))
                    for e in sin_stock + otros:
                        log.append(("warning",
                                    f"  Orden #{e['order_id']}: {e['error']}"))
            except Exception as e:
                log.append(("error", str(e)))
        st.session_state.log_ventas = log

    if st.session_state.log_ventas:
        st.markdown("#### Resultado")
        errores_detalle = []
        for nivel, msg in st.session_state.log_ventas:
            if nivel == "success":
                st.success(msg)
            elif nivel == "warning":
                if "Sin OC → Product IDs:" in msg:
                    errores_detalle.append(msg)
                elif "producto(s) no pudieron" in msg:
                    st.warning(msg)
                else:
                    errores_detalle.append(msg)
            elif nivel == "error":
                st.error(msg)
            else:
                st.info(msg)
        if errores_detalle:
            with st.expander(f"📋 Ver detalle de errores ({len(errores_detalle)} líneas)"):
                for d in errores_detalle:
                    st.text(d.strip())


# ═════════════════════════════════════════════════════════════════════════════
#  MÓDULO: ETIQUETAS
# ═════════════════════════════════════════════════════════════════════════════
def _et_consultar_woo(ids: list, meta_key: str) -> tuple[dict, list]:
    """Consulta WooCommerce y devuelve (woo_map, ids_no_encontrados)."""
    # obtener_productos_por_ids devuelve {product_id: product_dict}
    prods_dict = woo_api.obtener_productos_por_ids([i for i in ids if i != 0])
    woo_map = {}
    for pid_raw, p in prods_dict.items():
        pid = int(pid_raw)
        # Prefer _ywbc_barcode_display_value (already padded + check digit, matches YITH PrintCode)
        # Fall back to the configured meta_key if display value not present
        bc_display = ""
        bc_raw = ""
        for m in p.get("meta_data", []):
            k = str(m.get("key", ""))
            v = str(m.get("value", "") or "").strip()
            if k == "_ywbc_barcode_display_value" and v:
                bc_display = v
            elif k == meta_key and v:
                bc_raw = v
        bc = bc_display or bc_raw or p.get("sku", "") or str(pid)
        woo_map[pid] = {
            "nombre": p.get("name", f"Producto {pid}"),
            "precio": float(p.get("price", 0) or 0),
            "barcode": bc,
            "sku": p.get("sku", ""),
        }
    not_found = [i for i in ids if i != 0 and i not in woo_map]
    return woo_map, not_found


def _et_preview_y_descarga(items: list, key_prefix: str, filename: str):
    """Muestra vista previa y botón de descarga."""
    sin_bc = st.session_state.get(f"{key_prefix}_sin", [])
    if sin_bc:
        st.warning(f"⚠️ {len(sin_bc)} producto(s) no encontrados en WooCommerce: "
                   + ", ".join(str(x) for x in sin_bc))

    total_et = sum(i["cantidad"] for i in items)
    st.markdown(f"#### Vista previa — **{total_et}** etiquetas")
    df_prev = pd.DataFrame([{
        "SKU":              it["sku"] or "—",
        "Título (≤48)": etiq_mod.titulo_corto(it["nombre"]),
        "Precio":           it["precio"],
        "Barcode":          it["barcode"],
        "Cantidad":         it["cantidad"],
    } for it in items])
    # Force Barcode as string dtype so pandas / Streamlit don't strip leading zeros
    df_prev["Barcode"] = df_prev["Barcode"].astype(str)
    st.dataframe(
        df_prev,
        use_container_width=True,
        hide_index=True,
        column_config={"Barcode": st.column_config.TextColumn("Barcode", width="large")},
    )

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
            tmp_path = tmp.name
        etiq_mod.exportar_etiquetas_oc(items, tmp_path)
        with open(tmp_path, "rb") as f:
            xlsx_bytes = f.read()
        os.unlink(tmp_path)
        st.download_button(
            label=f"📥 Descargar {filename}",
            data=xlsx_bytes,
            file_name=filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            key=f"dl_{key_prefix}",
        )
    except Exception as e:
        st.error(f"Error al generar Excel: {e}")


def pagina_etiquetas():
    st.title("🏷️ Generador de Etiquetas")

    cfg_path = Path(__file__).parent / "config.json"
    with open(cfg_path, encoding="utf-8") as f:
        cfg = json.load(f)
    meta_key = cfg.get("yith_barcode_meta_key", "_ywbc_barcode_value")

    modo = st.radio("Modo", ["📦 Por Orden de Compra", "🔍 Por Producto"],
                    horizontal=True, key="et_modo")
    st.markdown("---")

    # ═══════════════════════════════════════════════════════════════════════
    # MODO 1: Por OC
    # ═══════════════════════════════════════════════════════════════════════
    if modo == "📦 Por Orden de Compra":
        ocs = db.listar_ordenes_compra()
        if not ocs:
            st.info("No hay Órdenes de Compra registradas.")
            return

        oc_opciones = {
            f"OC #{oc['id_oc']} — {oc['proveedor']} "
            f"({str(oc['fecha_ingreso'])[:10]})": int(oc["id_oc"])
            for oc in ocs
        }
        oc_sel_label = st.selectbox("Selecciona Orden de Compra",
                                    list(oc_opciones.keys()), key="et_oc_sel")
        id_oc = oc_opciones[oc_sel_label]

        if st.button("🔄 Generar etiquetas", type="primary", key="btn_et_oc"):
            st.session_state["et_oc_items"] = None
            st.session_state["et_oc_error"] = None
            lotes = db.listar_lotes_por_oc(id_oc)
            if not lotes:
                st.session_state["et_oc_error"] = "Esta OC no tiene lotes registrados."
            else:
                ids = [int(r["product_id"]) for r in lotes]
                with st.spinner("Consultando WooCommerce…"):
                    try:
                        woo_map, not_found = _et_consultar_woo(ids, meta_key)
                        items = []
                        for r in lotes:
                            pid  = int(r["product_id"])
                            sku  = r["sku"] or ""
                            cant = int(r["cantidad_inicial"])
                            if pid == 0:
                                continue
                            if pid in woo_map:
                                d = woo_map[pid]
                                items.append({
                                    "product_id": pid,
                                    "nombre":  d["nombre"],
                                    "precio":  d["precio"],
                                    "barcode": d["barcode"],
                                    "sku":     d["sku"] or sku,
                                    "cantidad": cant,
                                })
                            else:
                                not_found.append(f"ID {pid} (SKU: {sku})")
                        st.session_state["et_oc_items"] = items
                        st.session_state["et_oc_sin"]   = not_found
                    except Exception as e:
                        st.session_state["et_oc_error"] = str(e)

        if st.session_state.get("et_oc_error"):
            st.error(st.session_state["et_oc_error"])
        items = st.session_state.get("et_oc_items")
        if items:
            _et_preview_y_descarga(items, "et_oc", f"etiquetas_OC{id_oc}.xlsx")

    # ═══════════════════════════════════════════════════════════════════════
    # MODO 2: Por Producto
    # ═══════════════════════════════════════════════════════════════════════
    else:
        st.caption("Busca un producto por SKU o nombre y genera etiquetas para "
                   "la cantidad que necesites.")

        c1, c2 = st.columns([3, 1])
        with c1:
            busq = st.text_input("SKU / Nombre / Barcode", key="et_prod_busq")
        with c2:
            cant_prod = st.number_input("Cantidad de etiquetas", min_value=1,
                                        value=1, step=1, key="et_prod_cant")

        col_b1, col_b2 = st.columns([1, 1])
        with col_b1:
            if st.button("🔍 Buscar producto", key="btn_et_prod_buscar"):
                st.session_state["et_prod_encontrado"] = None
                st.session_state["et_prod_error"]     = None
                with st.spinner("Buscando en WooCommerce…"):
                    try:
                        prod = (woo_api.buscar_producto_por_sku(busq.strip()) or
                                woo_api.buscar_producto_por_barcode(busq.strip()))
                        if not prod:
                            # Buscar por nombre en caché
                            for p in _cargar_woo_cache():
                                if busq.lower() in (p.get("name") or "").lower():
                                    prod = p
                                    break
                        if prod:
                            pid = int(prod["id"])
                            bc = ""
                            for m in prod.get("meta_data", []):
                                if m.get("key") == meta_key:
                                    bc = str(m.get("value", ""))
                                    break
                            if not bc:
                                bc = prod.get("sku", "") or str(pid)
                            st.session_state["et_prod_encontrado"] = {
                                "product_id": pid,
                                "nombre":  prod.get("name", ""),
                                "precio":  float(prod.get("price", 0) or 0),
                                "barcode": bc,
                                "sku":     prod.get("sku", ""),
                            }
                        else:
                            st.session_state["et_prod_error"] = "Producto no encontrado."
                    except Exception as e:
                        st.session_state["et_prod_error"] = str(e)

        if st.session_state.get("et_prod_error"):
            st.warning(st.session_state["et_prod_error"])

        prod_enc = st.session_state.get("et_prod_encontrado")
        if prod_enc:
            st.success(f"✔ **{prod_enc['nombre']}** — "
                       f"SKU: `{prod_enc['sku'] or '—'}` | "
                       f"Barcode: `{prod_enc['barcode']}` | "
                       f"Precio: ${prod_enc['precio']:,.0f}")

        with col_b2:
            if st.button("➕ Generar etiquetas", type="primary", key="btn_et_prod_gen"):
                if not prod_enc:
                    st.warning("Busca un producto primero.")
                else:
                    items_p = [{
                        **prod_enc,
                        "cantidad": int(cant_prod),
                    }]
                    st.session_state["et_prod_items"] = items_p

        items_p = st.session_state.get("et_prod_items")
        if items_p:
            fname = f"etiquetas_{items_p[0]['sku'] or items_p[0]['product_id']}.xlsx"
            _et_preview_y_descarga(items_p, "et_prod", fname)


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

    (tab_inv, tab_prod, tab_ut, tab_woo,
     tab_surtido, tab_dec) = st.tabs([
        "📦 Inventario por Lotes",
        "📋 Por Producto",
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
                               "P. Compra", "Valor Compra"]

            # ── Enriquecer con precio de venta desde WooCommerce ──────────────
            precio_venta_map: dict[int, float] = {}
            try:
                productos_woo = _cargar_woo_cache()
                precio_venta_map = {
                    int(p["id"]): float(p.get("price", 0) or 0)
                    for p in productos_woo
                }
            except Exception:
                pass

            df_inv["P. Venta"] = (
                df_inv["Product ID"].map(precio_venta_map).fillna(0.0)
            )
            df_inv["Valor Venta"] = df_inv["Actual"] * df_inv["P. Venta"]

            # ── Resúmenes (ocultables) ────────────────────────────────────────
            valor_compra = df_inv["Valor Compra"].sum()
            valor_venta  = df_inv["Valor Venta"].sum()
            margen_pond  = ((valor_venta - valor_compra) / valor_venta * 100
                            if valor_venta > 0 else 0.0)
            unidades_tot = int(df_inv["Actual"].sum())

            with st.expander("📊 Resumen de inventario", expanded=True):
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Unidades totales",        f"{unidades_tot:,}")
                c2.metric("Valor a precio compra",   f"${valor_compra:,.2f}")
                c3.metric("Valor a precio venta",
                           f"${valor_venta:,.2f}" if valor_venta > 0 else "Sin precios WOO")
                c4.metric("Margen ponderado",
                           f"{margen_pond:.1f}%" if valor_venta > 0 else "—",
                           help="(Valor venta − Valor compra) / Valor venta")

            st.dataframe(df_inv, use_container_width=True, hide_index=True, height=600)
            _df_download(df_inv, "inventario_lotes.xlsx")
        else:
            st.info("Sin lotes registrados. Crea una Orden de Compra primero.")

    # ── Tab: Por Producto ─────────────────────────────────────────────────────
    with tab_prod:
        if st.button("🔄 Cargar vista por Producto", key="btn_prod"):
            st.cache_data.clear()

        filas_p = [dict(r) for r in db.resumen_por_producto()]
        if not filas_p:
            st.info("Sin lotes registrados. Crea una Orden de Compra primero.")
        else:
            # Enriquecer con nombre y precio de venta actual desde WooCommerce
            nombre_map:  dict[int, str]   = {}
            pventa_map:  dict[int, float] = {}
            try:
                for p in _cargar_woo_cache():
                    pid = int(p["id"])
                    nombre_map[pid] = p.get("name", "") or ""
                    pventa_map[pid] = float(p.get("price", 0) or 0)
            except Exception:
                pass

            rows = []
            for r in filas_p:
                pid = int(r["product_id"] or 0)
                if pid == 0:
                    continue   # lotes sin producto WOO válido
                stock      = int(r["stock_actual"] or 0)
                p_compra   = float(r["precio_compra_pond"] or 0)
                p_venta    = pventa_map.get(pid, float(r["ultimo_precio_venta"] or 0))
                ganancia_u = round(p_venta - p_compra, 2)
                margen_pct = round(ganancia_u / p_venta * 100, 1) if p_venta > 0 else 0.0
                rows.append({
                    "Product ID":        pid,
                    "SKU":               r["sku"] or "—",
                    "Nombre":            nombre_map.get(pid, "—"),
                    "Stock":             stock,
                    "P. Compra (pond.)": p_compra,
                    "Últ. Compra":       str(r["ultima_compra_fecha"] or "")[:10],
                    "P. Venta (WOO)":    p_venta,
                    "Últ. Venta":        str(r["ultima_venta_fecha"] or "")[:10],
                    "Ganancia/u":        ganancia_u,
                    "Margen %":          margen_pct,
                    "Valor Stock €":     round(stock * p_compra, 2),
                    "Valor Venta €":     round(stock * p_venta, 2),
                })

            df_p = pd.DataFrame(rows)

            # ── Resumen agregado ──────────────────────────────────────────────
            tot_stock   = int(df_p["Stock"].sum())
            tot_compra  = df_p["Valor Stock €"].sum()
            tot_venta   = df_p["Valor Venta €"].sum()
            margen_gral = round((tot_venta - tot_compra) / tot_venta * 100, 1) if tot_venta > 0 else 0.0

            with st.expander("📊 Resumen", expanded=True):
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Productos distintos",   len(df_p))
                c2.metric("Unidades totales",       f"{tot_stock:,}")
                c3.metric("Valor a costo",          f"${tot_compra:,.0f}")
                c4.metric("Valor a precio venta",   f"${tot_venta:,.0f}")
                c5, c6 = st.columns([1, 3])
                c5.metric("Margen ponderado",
                           f"{margen_gral:.1f}%",
                           help="(Valor venta − Valor costo) / Valor venta")

            # Formato de colores: rojo si margen < 0, verde si > 20 %
            def _color_margen(val):
                if val < 0:   return "color: #e74c3c"
                if val >= 20: return "color: #27ae60"
                return ""

            st.dataframe(
                df_p.style.map(_color_margen, subset=["Margen %"])
                    .format({
                        "P. Compra (pond.)": "${:,.0f}",
                        "P. Venta (WOO)":    "${:,.0f}",
                        "Ganancia/u":        "${:,.0f}",
                        "Margen %":          "{:.1f}%",
                        "Valor Stock €":     "${:,.0f}",
                        "Valor Venta €":     "${:,.0f}",
                    }),
                use_container_width=True,
                hide_index=True,
                height=620,
            )
            _df_download(df_p, "inventario_por_producto.xlsx")

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
            df_woo = pd.DataFrame(filas_woo) if filas_woo else pd.DataFrame()
            n_agotados = sum(1 for r in filas_woo if r["Stock"] == "0"
                             or r["Estado"] == "outofstock")
            col_w3, col_w4 = st.columns(2)
            col_w3.metric("Productos mostrados", len(df_woo))
            col_w4.metric("Agotados", n_agotados)

            if df_woo.empty:
                st.info("Ningún producto coincide con el filtro.")
            else:
                # Color en columna Stock
                styled = (df_woo.style
                          .map(_color_stock, subset=["Stock"])
                          .format({"Precio": "${:.2f}"}))
                st.dataframe(styled, use_container_width=True, hide_index=True,
                             height=620)
                _df_download(df_woo, "stock_woocommerce.xlsx")

            # ── Detectar discrepancias de stock ──────────────────────────
            stock_local   = db.stock_local_por_producto()      # OC - ventas importadas
            oc_inicial    = db.stock_oc_inicial_por_producto()  # solo lo que entró por OC
            vendido_local = db.ventas_totales_por_producto()    # ventas importadas al sistema

            # WC > (OC_inicial - ventas_importadas) → stock en WC supera lo que el sistema registra
            # Puede ser: stock pre-existente en WC antes del sistema, o stock agregado fuera del sistema
            huerfanos = [
                p for p in productos_woo
                if p.get("manage_stock")
                and (p.get("stock_quantity") or 0) > 0
                and (p.get("stock_quantity") or 0) > stock_local.get(p.get("id"), 0)
            ]

            # WC < (OC_inicial - ventas_importadas) → WC tiene menos de lo esperado
            # CAUSA MÁS COMÚN: ventas en WooCommerce aún no importadas al sistema
            # También puede ser: reducción manual del stock en WC
            reducidos = [
                p for p in productos_woo
                if p.get("manage_stock")
                and stock_local.get(p.get("id"), 0) > (p.get("stock_quantity") or 0)
            ]

            if reducidos:
                with st.container(border=True):
                    st.warning(
                        f"⚠️ **{len(reducidos)} producto(s)** tienen el stock en WooCommerce por debajo "
                        "del estimado del sistema (OCs − ventas importadas). "
                        "**Causa más probable: ventas recientes en WooCommerce aún no importadas al sistema.** "
                        "Importa las ventas para recalcular. Si el sistema ya está al día, "
                        "puede indicar una reducción manual del stock en WooCommerce.",
                        icon="⚠️",
                    )
                    rows_red = []
                    for p in reducidos:
                        pid = p.get("id")
                        wc_stock   = p.get("stock_quantity") or 0
                        local_stk  = stock_local.get(pid, 0)
                        oc_ini     = oc_inicial.get(pid, 0)
                        vendido    = vendido_local.get(pid, 0)
                        rows_red.append({
                            "ID": pid,
                            "Nombre": (p.get("name") or "")[:50],
                            "SKU": p.get("sku") or "—",
                            "Stock WooCommerce": wc_stock,
                            "Stock sistema (OC−ventas imp.)": local_stk,
                            "Total vendido (importado)": vendido,
                            "Diferencia": wc_stock - local_stk,
                        })
                    st.dataframe(
                        pd.DataFrame(rows_red),
                        use_container_width=True,
                        hide_index=True,
                    )

            if huerfanos:
                diff_total = sum(
                    (p.get("stock_quantity") or 0) - stock_local.get(p.get("id"), 0)
                    for p in huerfanos
                )
                st.warning(
                    f"⚠️ **{len(huerfanos)} producto(s)** tienen más stock en WooCommerce "
                    f"que el registrado en el sistema ({diff_total} uds. por encima del estimado). "
                    "Puede deberse a stock existente en WooCommerce antes de registrar la primera OC, "
                    "a devoluciones procesadas en WooCommerce, o a stock agregado fuera del sistema. "
                    "Si corresponde a una compra real, crea una OC para regularizarlo.",
                    icon="⚠️",
                )
                if st.button("📋 Crear OC para stock sin asignar",
                             type="primary", key="btn_abrir_oc_woo"):
                    st.session_state["oc_woo_huerfanos"] = huerfanos
                    st.session_state["oc_woo_stock_local"] = stock_local
                    _dialogo_oc_woo()

            if not huerfanos and not reducidos:
                st.success("✅ Todo el stock de WooCommerce coincide con las OCs registradas.",
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
                    _pv = r["primera_venta"]
                    primera_str       = (str(_pv)[:10] if _pv else "")
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
#  MÓDULO: FINANZAS
# ═════════════════════════════════════════════════════════════════════════════
def pagina_finanzas():
    from datetime import date as _date, datetime as _dt
    import calendar

    st.title("💰 Finanzas")

    tab_gastos, tab_patrimonio = st.tabs(["📋 Gastos Operativos", "🏦 Patrimonio"])

    # ═══════════════════════════════════════════════════════════════════
    #  TAB 1: GASTOS OPERATIVOS
    # ═══════════════════════════════════════════════════════════════════
    with tab_gastos:
        hoy = _date.today()

        # ── KPIs del mes actual ─────────────────────────────────────────
        gastos_mes  = db.total_gastos_mes(hoy.year, hoy.month)
        gastos_anio = sum(
            float(r["total_gastos"]) for r in db.gastos_por_mes()
            if str(r["mes"]).startswith(str(hoy.year))
        )
        cat_mes = db.gastos_por_categoria(
            desde=f"{hoy.year}-{hoy.month:02d}-01",
            hasta=f"{hoy.year}-{hoy.month:02d}-{calendar.monthrange(hoy.year, hoy.month)[1]:02d}",
        )
        mayor_cat = max(cat_mes, key=lambda r: float(r["total"]), default=None)

        km1, km2, km3 = st.columns(3)
        km1.metric(f"Gastos {hoy.strftime('%B %Y')}", f"${gastos_mes:,.0f}")
        km2.metric(f"Gastos {hoy.year}",              f"${gastos_anio:,.0f}")
        km3.metric("Mayor categoría (mes)",
                   mayor_cat["categoria"] if mayor_cat else "—",
                   f"${float(mayor_cat['total']):,.0f}" if mayor_cat else None)

        st.markdown("---")

        # ── Formulario nuevo gasto ──────────────────────────────────────
        with st.expander("➕ Registrar gasto", expanded=False):
            with st.form("form_nuevo_gasto", clear_on_submit=True):
                fc1, fc2 = st.columns(2)
                cat = fc1.selectbox("Categoría", db.CATEGORIAS_GASTO)
                fecha_g = fc2.date_input("Fecha", value=hoy)
                desc = st.text_input("Descripción (opcional)")
                fc3, fc4 = st.columns([2, 1])
                monto = fc3.number_input("Monto ($)", min_value=0.0, step=1000.0, format="%.0f")
                recurrente = fc4.checkbox("Recurrente mensual")
                if st.form_submit_button("Guardar gasto", type="primary", use_container_width=True):
                    if monto <= 0:
                        st.error("El monto debe ser mayor a 0.")
                    else:
                        db.registrar_gasto(cat, desc.strip() or None, monto,
                                           str(fecha_g), recurrente)
                        st.success(f"Gasto de ${monto:,.0f} registrado.")
                        st.rerun()

        # ── Filtros y tabla ─────────────────────────────────────────────
        st.markdown("#### Historial de gastos")
        fl1, fl2, fl3 = st.columns([2, 2, 1])
        f_desde = fl1.date_input("Desde", value=_date(hoy.year, hoy.month, 1),
                                 key="g_desde")
        f_hasta = fl2.date_input("Hasta", value=hoy, key="g_hasta")

        gastos = db.listar_gastos(desde=str(f_desde), hasta=str(f_hasta))

        if gastos:
            df_g = pd.DataFrame([dict(r) for r in gastos])
            df_g["fecha"]      = df_g["fecha"].apply(lambda x: str(x)[:10])
            df_g["recurrente"] = df_g["recurrente"].apply(lambda x: "✅" if x else "")
            df_g["monto"]      = df_g["monto"].apply(lambda x: f"${float(x):,.0f}")
            df_g = df_g.rename(columns={
                "id_gasto": "ID", "categoria": "Categoría",
                "descripcion": "Descripción", "monto": "Monto",
                "fecha": "Fecha", "recurrente": "Recurrente",
            })
            st.dataframe(df_g[["ID","Fecha","Categoría","Descripción","Monto","Recurrente"]],
                         use_container_width=True, hide_index=True)

            total_periodo = sum(
                float(str(r["monto"]).replace("$", "").replace(",", ""))
                for r in gastos
            )
            st.markdown(f"**Total del período: ${total_periodo:,.0f}**")

            # Eliminar gasto individual
            with st.expander("🗑️ Eliminar gasto"):
                ids_disp = [r["id_gasto"] for r in gastos]
                del_id = st.selectbox("ID del gasto a eliminar", ids_disp)
                if st.button("Eliminar", type="secondary"):
                    db.eliminar_gasto(del_id)
                    st.success(f"Gasto #{del_id} eliminado.")
                    st.rerun()
        else:
            st.info("Sin gastos en el período seleccionado.")

        st.markdown("")

        # ── Gráficas ────────────────────────────────────────────────────
        gcol1, gcol2 = st.columns([3, 2])

        with gcol1:
            st.markdown("#### Gastos por mes")
            meses_g = db.gastos_por_mes()
            if meses_g:
                df_mg = pd.DataFrame([dict(r) for r in meses_g])
                fig_gm = px.bar(
                    df_mg, x="mes", y="total_gastos",
                    color_discrete_sequence=["#D42B2B"],
                    labels={"mes": "", "total_gastos": "Gastos ($)"},
                    height=240,
                )
                fig_gm.update_layout(
                    margin=dict(l=0, r=0, t=8, b=0),
                    plot_bgcolor="#ffffff", paper_bgcolor="#ffffff",
                    font=dict(color="#1C2333", size=11),
                    xaxis=dict(tickangle=-35, gridcolor="#F3F4F6"),
                    yaxis=dict(gridcolor="#F3F4F6"),
                )
                fig_gm.update_traces(marker_line_width=0)
                st.plotly_chart(fig_gm, use_container_width=True, config={"displayModeBar": False})
            else:
                st.info("Sin gastos registrados aún.")

        with gcol2:
            st.markdown("#### Por categoría (período)")
            cats = db.gastos_por_categoria(desde=str(f_desde), hasta=str(f_hasta))
            if cats:
                df_cat = pd.DataFrame([dict(r) for r in cats])
                fig_cat = px.pie(
                    df_cat, names="categoria", values="total", hole=0.45,
                    color_discrete_sequence=[
                        "#D42B2B","#3A5BA0","#F59E0B","#10B981","#8B5CF6","#6B7280",
                    ],
                    height=240,
                )
                fig_cat.update_layout(
                    margin=dict(l=0, r=0, t=8, b=0),
                    paper_bgcolor="#ffffff",
                    legend=dict(font=dict(size=10)),
                )
                fig_cat.update_traces(textposition="inside", textinfo="percent+label")
                st.plotly_chart(fig_cat, use_container_width=True, config={"displayModeBar": False})
            else:
                st.info("Sin datos para el período.")

    # ═══════════════════════════════════════════════════════════════════
    #  TAB 2: PATRIMONIO
    # ═══════════════════════════════════════════════════════════════════
    with tab_patrimonio:
        resumen = db.resumen_home()
        patri_rows = db.patrimonio_inventario()

        valor_inv      = resumen["valor_stock"]
        utilidad_acum  = resumen["utilidad_total"]
        gastos_acum    = sum(float(r["total_gastos"]) for r in db.gastos_por_mes())
        patrimonio_net = valor_inv + utilidad_acum - gastos_acum

        pk1, pk2, pk3, pk4 = st.columns(4)
        pk1.metric("Inventario (costo)",  f"${valor_inv:,.0f}")
        pk2.metric("Utilidad bruta acum.", f"${utilidad_acum:,.0f}")
        pk3.metric("Gastos acumulados",    f"${gastos_acum:,.0f}")
        pk4.metric("Patrimonio neto",      f"${patrimonio_net:,.0f}")

        st.markdown("")

        pcol1, pcol2 = st.columns([3, 2])

        with pcol1:
            st.markdown("#### Inventario por producto")
            if patri_rows:
                df_p = pd.DataFrame([dict(r) for r in patri_rows])
                df_p["costo_prom"]       = df_p["costo_prom"].apply(lambda x: f"${float(x):,.0f}")
                df_p["valor_inventario"] = df_p["valor_inventario"].apply(lambda x: f"${float(x):,.0f}")
                df_p = df_p.rename(columns={
                    "product_id": "ID", "sku": "SKU",
                    "stock_actual": "Stock", "costo_prom": "Costo prom",
                    "valor_inventario": "Valor en inventario",
                })
                st.dataframe(df_p[["SKU","Stock","Costo prom","Valor en inventario"]],
                             use_container_width=True, hide_index=True, height=320)
            else:
                st.info("Sin inventario registrado.")

        with pcol2:
            st.markdown("#### Composición")
            comp_data = {
                "Componente": ["Inventario", "Utilidad bruta", "Gastos"],
                "Valor":      [max(valor_inv, 0), max(utilidad_acum, 0), max(gastos_acum, 0)],
            }
            if any(v > 0 for v in comp_data["Valor"]):
                df_comp = pd.DataFrame(comp_data)
                fig_comp = px.bar(
                    df_comp, x="Componente", y="Valor",
                    color="Componente",
                    color_discrete_map={
                        "Inventario":    "#3A5BA0",
                        "Utilidad bruta": "#10B981",
                        "Gastos":        "#D42B2B",
                    },
                    height=280,
                    labels={"Valor": "$"},
                )
                fig_comp.update_layout(
                    margin=dict(l=0, r=0, t=8, b=0),
                    plot_bgcolor="#ffffff", paper_bgcolor="#ffffff",
                    font=dict(color="#1C2333", size=11),
                    showlegend=False,
                    yaxis=dict(gridcolor="#F3F4F6"),
                )
                fig_comp.update_traces(marker_line_width=0)
                st.plotly_chart(fig_comp, use_container_width=True, config={"displayModeBar": False})
            else:
                st.info("Sin datos suficientes.")


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
elif PAGINA == "💰 Finanzas":
    pagina_finanzas()
