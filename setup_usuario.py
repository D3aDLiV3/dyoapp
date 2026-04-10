"""
setup_usuario.py — Crear o actualizar un usuario en config.json.

Uso:
    python setup_usuario.py

Se pedirá el nombre de usuario y la contraseña de forma interactiva.
El hash se guarda en config.json bajo la clave "usuarios".
"""
import getpass
import hashlib
import json
import os
import secrets
import sys

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")


def hash_password(password: str) -> str:
    """Genera pbkdf2:sha256:260000$<hex_salt>$<hex_hash>"""
    salt = secrets.token_bytes(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 260000)
    return f"pbkdf2:sha256:260000${salt.hex()}${h.hex()}"


def main():
    print("=== Configurar usuario WooAdmin ===\n")

    if not os.path.exists(CONFIG_PATH):
        print(f"ERROR: No se encontró {CONFIG_PATH}")
        sys.exit(1)

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)

    usuarios_existentes = list(config.get("usuarios", {}).keys())
    if usuarios_existentes:
        print(f"Usuarios actuales: {', '.join(usuarios_existentes)}")
    else:
        print("No hay usuarios configurados aún.")

    print()
    usuario = input("Nombre de usuario: ").strip()
    if not usuario:
        print("ERROR: El nombre de usuario no puede estar vacío.")
        sys.exit(1)

    pwd = getpass.getpass("Contraseña (no se muestra al escribir): ")
    if len(pwd) < 8:
        print("ERROR: La contraseña debe tener al menos 8 caracteres.")
        sys.exit(1)

    pwd2 = getpass.getpass("Confirmar contraseña: ")
    if pwd != pwd2:
        print("ERROR: Las contraseñas no coinciden.")
        sys.exit(1)

    hashed = hash_password(pwd)

    if "usuarios" not in config:
        config["usuarios"] = {}

    accion = "actualizado" if usuario in config["usuarios"] else "creado"
    config["usuarios"][usuario] = {"hash": hashed}

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)

    print(f"\n✅ Usuario '{usuario}' {accion} correctamente.")
    print("Reinicia la app (pm2 restart wooposadmin) para que surta efecto.")


if __name__ == "__main__":
    main()
