import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

class FacebookMarketplaceScraper:
    def __init__(self, profile_url, headless=True, driver_path=None):
        self.profile_url = profile_url
        chrome_options = Options()
        if headless:
            chrome_options.add_argument('--headless')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        self.driver = webdriver.Chrome(executable_path=driver_path, options=chrome_options) if driver_path else webdriver.Chrome(options=chrome_options)

    def scrape_products(self):
        self.driver.get(self.profile_url)
        time.sleep(3)
        last_height = self.driver.execute_script("return document.body.scrollHeight")
        while True:
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            new_height = self.driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height
        products = []
        items = self.driver.find_elements(By.XPATH, '//div[contains(@aria-label, "Marketplace Listing")]')
        for item in items:
            try:
                title = item.find_element(By.XPATH, './/span[contains(@dir, "auto")]').text
                price = item.find_element(By.XPATH, './/span[contains(text(), "$") or contains(text(), "₡") or contains(text(), "€") or contains(text(), "₲") or contains(text(), "₱") or contains(text(), "₦") or contains(text(), "R$") or contains(text(), "S/") or contains(text(), "Q") or contains(text(), "RD$") or contains(text(), "Bs.") or contains(text(), "L") or contains(text(), "C$") or contains(text(), "₡") or contains(text(), "₲") or contains(text(), "₱") or contains(text(), "₦") or contains(text(), "R$") or contains(text(), "S/") or contains(text(), "Q") or contains(text(), "RD$") or contains(text(), "Bs.") or contains(text(), "L") or contains(text(), "C$")]').text
                products.append({'title': title, 'price': price})
            except Exception:
                continue
        return products

    def close(self):
        self.driver.quit()
