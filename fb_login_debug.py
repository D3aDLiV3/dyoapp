import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

# Configura tus credenciales aquí
EMAIL = "TU_CORREO"
PASSWORD = "TU_PASSWORD"

# Opcional: para guardar screenshots en cada paso
def save_step(driver, step):
    driver.save_screenshot(f"step_{step}.png")
    with open(f"step_{step}.html", "w", encoding="utf-8") as f:
        f.write(driver.page_source)

def main():
    chrome_options = Options()
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    # chrome_options.add_argument('--headless')  # Quita esto para ver el navegador

    driver = webdriver.Chrome(options=chrome_options)
    driver.get("https://www.facebook.com/login")
    time.sleep(2)
    save_step(driver, "login_page")

    # Login básico
    driver.find_element(By.ID, "email").send_keys(EMAIL)
    driver.find_element(By.ID, "pass").send_keys(PASSWORD)
    save_step(driver, "credentials_filled")
    driver.find_element(By.NAME, "login").click()
    time.sleep(5)
    save_step(driver, "after_login")

    # Detectar 2FA
    if "login/approvals" in driver.current_url or "two-factor" in driver.current_url:
        print("Se requiere código de verificación 2FA.")
        # Espera a que el usuario ingrese el código manualmente
        input("Ingresa el código 2FA en el navegador y presiona Enter aquí para continuar...")
        save_step(driver, "after_2fa")

    # Detectar captcha
    if "captcha" in driver.page_source.lower():
        print("¡Captcha detectado! Resuélvelo manualmente en el navegador.")
        input("Resuelve el captcha y presiona Enter aquí para continuar...")
        save_step(driver, "after_captcha")

    print("Login completado. Puedes continuar con el scraping.")
    driver.quit()

if __name__ == "__main__":
    main()
