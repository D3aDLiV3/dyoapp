"""
launcher.py — Lanzador de Descuentos y Ofertas (Streamlit).
Compila con PyInstaller para obtener el .exe ancable a la barra de tareas.
"""
import os
import sys
import time
import socket
import threading
import subprocess
import webbrowser
import tkinter as tk
from tkinter import font as tkfont

# PIL opcional — para mostrar el logo en la ventana
try:
    from PIL import Image, ImageTk as _ITK
    _PIL_OK = True
except ImportError:
    _PIL_OK = False

PORT = 8501
URL  = f"http://localhost:{PORT}"

# Paleta de marca ─────────────────────────────────────────────────────────────
C_BG       = "#1a1a2e"   # fondo oscuro
C_HEADER   = "#E42127"   # rojo Descuentos y Ofertas
C_AMARILLO = "#F5C400"   # amarillo/dorado
C_AZUL     = "#3D5A99"   # azul carrito
C_TEXTO    = "#FFFFFF"
C_GRIS     = "#3a3a4a"

# ── Rutas ─────────────────────────────────────────────────────────────────────
if getattr(sys, "frozen", False):
    # Ejecutando como .exe (PyInstaller)
    APP_DIR    = os.path.dirname(sys.executable)
    _ASSETS    = getattr(sys, "_MEIPASS", APP_DIR)
else:
    APP_DIR    = os.path.dirname(os.path.abspath(__file__))
    _ASSETS    = APP_DIR

def _streamlit_exe():
    for candidate in [
        os.path.join(APP_DIR, ".venv", "Scripts", "streamlit.exe"),
        os.path.join(APP_DIR, ".venv", "bin", "streamlit"),
        "streamlit",
    ]:
        if os.path.isfile(candidate):
            return candidate
    return "streamlit"

def _port_libre(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", port)) != 0

# ── Ventana principal ─────────────────────────────────────────────────────────
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Descuentos y Ofertas — Inventario")
        self.geometry("380x280")
        self.resizable(False, False)
        self.configure(bg=C_BG)
        self.protocol("WM_DELETE_WINDOW", self._salir)

        # Ícono de ventana / barra de tareas
        ico_path = os.path.join(_ASSETS, "logo_launcher.ico")
        if os.path.isfile(ico_path):
            try:
                self.iconbitmap(ico_path)
            except Exception:
                pass

        self._proc      = None
        self._corriendo = False
        self._logo_ref  = None   # mantiene referencia para que GC no destruya la imagen

        self._build()
        threading.Thread(target=self._iniciar, daemon=True).start()

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build(self):
        bold14 = tkfont.Font(family="Segoe UI", size=14, weight="bold")
        bold11 = tkfont.Font(family="Segoe UI", size=11, weight="bold")
        reg10  = tkfont.Font(family="Segoe UI", size=10)
        reg9   = tkfont.Font(family="Segoe UI", size=9)

        # ── Banda de cabecera roja ────────────────────────────────────────────
        header = tk.Frame(self, bg=C_HEADER, height=60)
        header.pack(fill="x")
        header.pack_propagate(False)

        # Logo en la cabecera
        logo_path = os.path.join(_ASSETS, "logo_launcher.png")
        if _PIL_OK and os.path.isfile(logo_path):
            img = Image.open(logo_path).resize((46, 46), Image.LANCZOS)
            self._logo_ref = _ITK.PhotoImage(img)
            tk.Label(header, image=self._logo_ref,
                     bg=C_HEADER).pack(side="left", padx=10, pady=7)

        tk.Label(header,
                 text="Descuentos y Ofertas",
                 bg=C_HEADER, fg=C_TEXTO, font=bold14
                 ).pack(side="left", pady=7)

        # ── Subtítulo ─────────────────────────────────────────────────────────
        tk.Label(self,
                 text="Sistema de Inventario FIFO",
                 bg=C_BG, fg=C_AMARILLO, font=bold11
                 ).pack(pady=(14, 2))

        # ── Estado ────────────────────────────────────────────────────────────
        self.lbl_estado = tk.Label(
            self, text="⏳  Iniciando servidor…",
            bg=C_BG, fg=C_AMARILLO, font=reg10)
        self.lbl_estado.pack(pady=2)

        self.lbl_url = tk.Label(
            self, text="", bg=C_BG, fg="#6fc3f7",
            font=reg9, cursor="hand2")
        self.lbl_url.pack(pady=2)
        self.lbl_url.bind("<Button-1>", lambda e: webbrowser.open(URL))

        # ── Botones ───────────────────────────────────────────────────────────
        btn_frame = tk.Frame(self, bg=C_BG)
        btn_frame.pack(pady=16)

        self.btn_abrir = tk.Button(
            btn_frame, text="🌐  Abrir navegador",
            bg=C_HEADER, fg=C_TEXTO,
            activebackground="#c01a1e", activeforeground=C_TEXTO,
            relief="flat", padx=14, pady=7, font=reg10,
            state="disabled",
            command=lambda: webbrowser.open(URL))
        self.btn_abrir.pack(side="left", padx=8)

        tk.Button(
            btn_frame, text="⏹  Detener",
            bg=C_GRIS, fg=C_TEXTO,
            activebackground="#E42127", activeforeground=C_TEXTO,
            relief="flat", padx=14, pady=7, font=reg10,
            command=self._salir).pack(side="left", padx=8)

    def _set_estado(self, texto: str, color: str = C_AMARILLO):
        self.lbl_estado.configure(text=texto, fg=color)

    # ── Lógica ────────────────────────────────────────────────────────────────
    def _iniciar(self):
        app_script = os.path.join(APP_DIR, "app_web.py")

        if not os.path.isfile(app_script):
            self._set_estado("❌  No se encontró app_web.py", "#f38ba8")
            return

        # Si ya hay un servidor corriendo en el puerto, úsalo
        if not _port_libre(PORT):
            self._set_estado("✅  Servidor ya activo", "#6bcb77")
            self._on_listo()
            return

        exe = _streamlit_exe()
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        try:
            self._proc = subprocess.Popen(
                [exe, "run", app_script,
                 "--server.port", str(PORT),
                 "--server.headless", "true",
                 "--browser.gatherUsageStats", "false"],
                cwd=APP_DIR,
                creationflags=flags,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            self._set_estado("❌  Streamlit no encontrado en el entorno", "#f38ba8")
            return

        # Esperar hasta que el puerto responda (max 30 s)
        for _ in range(60):
            if not _port_libre(PORT):
                self._on_listo()
                return
            time.sleep(0.5)

        self._set_estado("⚠️  El servidor tardó demasiado", "#ffd93d")

    def _on_listo(self):
        self._corriendo = True
        self._set_estado("✅  Corriendo en:", "#6bcb77")
        self.lbl_url.configure(text=URL)
        self.btn_abrir.configure(state="normal", bg=C_HEADER)
        webbrowser.open(URL)

    def _salir(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self.destroy()


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    App().mainloop()
