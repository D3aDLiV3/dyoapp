#!/bin/bash
# =============================================================================
# deploy_vps.sh — Script de instalación de WooPosAdmin en VPS Ubuntu/Debian
# Uso: bash deploy_vps.sh
# =============================================================================
set -e

APP_DIR="/opt/wooposadmin"
REPO_URL="https://github.com/TU_USUARIO/TU_REPO.git"   # <-- Cambia esto
APP_NAME="wooposadmin"
NGINX_CONF="app.descuentosyofertas.net.conf"

echo "======================================================"
echo "  WooPosAdmin — Instalación en VPS"
echo "======================================================"

# 1. Dependencias del sistema
echo "[1/7] Instalando dependencias del sistema..."
sudo apt-get update -q
sudo apt-get install -y python3 python3-venv python3-pip nginx certbot python3-certbot-nginx git nodejs npm
# Instalar PM2 globalmente
sudo npm install -g pm2

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

# 6. Arrancar con PM2
echo "[6/7] Configurando PM2..."
sudo mkdir -p /var/log/wooposadmin

# Ajustar rutas en ecosystem.config.js al directorio real de instalación
sed -i "s|/opt/wooposadmin|$APP_DIR|g" "$APP_DIR/ecosystem.config.js"

cd "$APP_DIR"
pm2 delete "$APP_NAME" 2>/dev/null || true
pm2 start ecosystem.config.js
echo "  → App '$APP_NAME' arrancada con PM2."
echo ""
echo "  ⚠  IMPORTANTE (PM2 compartido con otras apps):"
echo "     NO se ejecutó 'pm2 save' automáticamente para no pisar"
echo "     la lista guardada de tus otras apps."
echo "     Cuando tengas TODAS tus apps corriendo, ejecuta manualmente:"
echo "       pm2 save"
echo ""
echo "     Si PM2 todavía no está configurado para arrancar al reiniciar:"
echo "       pm2 startup"
echo "     → copia y pega el comando sudo que aparezca, y luego:"
echo "       pm2 save"

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
echo "Comandos útiles de PM2:"
echo "  pm2 status                  # Ver estado de todas las apps"
echo "  pm2 logs wooposadmin        # Ver logs en vivo"
echo "  pm2 restart wooposadmin     # Reiniciar app"
echo "  pm2 stop wooposadmin        # Detener app"
echo "  pm2 monit                   # Monitor interactivo"
