#!/bin/bash
# =============================================================================
# deploy_vps.sh — Script de instalación de WooPosAdmin en VPS Ubuntu/Debian
# Uso: bash deploy_vps.sh
# =============================================================================
set -e

APP_DIR="/opt/wooposadmin"
REPO_URL="https://github.com/TU_USUARIO/TU_REPO.git"   # <-- Cambia esto
SERVICE_NAME="wooposadmin"
NGINX_CONF="app.descuentosyofertas.net.conf"

echo "======================================================"
echo "  WooPosAdmin — Instalación en VPS"
echo "======================================================"

# 1. Dependencias del sistema
echo "[1/7] Instalando dependencias del sistema..."
sudo apt-get update -q
sudo apt-get install -y python3 python3-venv python3-pip nginx certbot python3-certbot-nginx git

# 2. Clonar repositorio
echo "[2/7] Clonando repositorio en $APP_DIR..."
if [ -d "$APP_DIR" ]; then
    echo "  → El directorio ya existe. Haciendo git pull..."
    cd "$APP_DIR"
    git pull
else
    sudo git clone "$REPO_URL" "$APP_DIR"
    sudo chown -R "$USER:$USER" "$APP_DIR"
    cd "$APP_DIR"
fi

# 3. Crear virtualenv e instalar dependencias Python
echo "[3/7] Creando entorno virtual e instalando paquetes..."
python3 -m venv .venv
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
deactivate

# 4. Crear config.json con credenciales reales
echo "[4/7] Configuración de credenciales..."
if [ ! -f "$APP_DIR/config.json" ]; then
    cp "$APP_DIR/config.example.json" "$APP_DIR/config.json"
    echo ""
    echo "  ⚠  IMPORTANTE: Edita el archivo con tus credenciales reales:"
    echo "     nano $APP_DIR/config.json"
    echo ""
    read -p "  Presiona ENTER cuando hayas terminado de editar config.json..."
fi

# 5. Inicializar base de datos
echo "[5/7] Inicializando base de datos SQLite..."
"$APP_DIR/.venv/bin/python" -c "import sys; sys.path.insert(0,'$APP_DIR'); import db; db.init_db()"

# 6. Instalar y arrancar servicio systemd
echo "[6/7] Configurando servicio systemd..."
# Ajusta el usuario al usuario actual del sistema
sed "s/User=ubuntu/User=$USER/g; s|WorkingDirectory=.*|WorkingDirectory=$APP_DIR|g; s|ExecStart=.*|ExecStart=$APP_DIR/.venv/bin/streamlit run $APP_DIR/app_web.py|g" \
    "$APP_DIR/wooposadmin.service" | sudo tee /etc/systemd/system/${SERVICE_NAME}.service > /dev/null

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"
echo "  → Servicio $SERVICE_NAME activo."

# 7. Instalar configuración Nginx
echo "[7/7] Configurando Nginx..."
sudo cp "$APP_DIR/nginx/$NGINX_CONF" "/etc/nginx/sites-available/$NGINX_CONF"
sudo ln -sf "/etc/nginx/sites-available/$NGINX_CONF" "/etc/nginx/sites-enabled/$NGINX_CONF"
sudo nginx -t
sudo systemctl reload nginx

echo ""
echo "======================================================"
echo "  ✓ Instalación completada"
echo "======================================================"
echo ""
echo "La app está disponible en: http://app.descuentosyofertas.net"
echo ""
echo "Próximo paso – Instalar certificado SSL gratuito (HTTPS):"
echo "  sudo certbot --nginx -d app.descuentosyofertas.net"
echo ""
echo "Comandos útiles:"
echo "  sudo systemctl status $SERVICE_NAME          # Ver estado"
echo "  sudo journalctl -u $SERVICE_NAME -f          # Ver logs en vivo"
echo "  sudo systemctl restart $SERVICE_NAME         # Reiniciar app"
