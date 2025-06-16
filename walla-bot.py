#!/usr/bin/env python
# walla-bot.py

import json
import os
import time
import smtplib
import requests
import pandas as pd
from urllib.parse import urlparse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.mime.image import MIMEImage
import re
from dotenv import load_dotenv
import logging
import gzip
import shutil
from logging.handlers import TimedRotatingFileHandler

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.keys import Keys

# --- CONSTANTS ---
CONFIG_FILE = 'config.json'
SEEN_ADS_FILE = 'data/seen_ads.txt'
IMAGES_DIR = "product_images"
CSV_DIR = "data/csv"
SCREENSHOTS_DIR = "data/screenshots"

# --- LOGGING SETUP ---
def setup_logger():
    os.makedirs("logs", exist_ok=True)
    os.makedirs(CSV_DIR, exist_ok=True)
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
    os.makedirs("data", exist_ok=True)
    log = logging.getLogger("wallabot")
    log.setLevel(logging.INFO)
    handler = TimedRotatingFileHandler(
        filename="logs/wallabot.log",
        when="midnight",
        interval=1,
        backupCount=10,
        encoding="utf-8",
        delay=False,
        utc=False
    )
    handler.suffix = "%Y-%m-%d"
    handler.extMatch = r"^\d{4}-\d{2}-\d{2}$"
    def namer(default_name):
        return default_name + ".gz"
    def rotator(source, dest):
        with open(source, 'rb') as f_in, gzip.open(dest, 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out)
        os.remove(source)
    handler.namer, handler.rotator = namer, rotator
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
    handler.setFormatter(fmt)
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    log.addHandler(handler)
    log.addHandler(console)
    return log

logger = setup_logger()

# --- ENV VARS ---
load_dotenv()
RECIPIENT_EMAIL = os.getenv('WALLABOT_RECIPIENT_EMAIL')
SENDER_EMAIL = os.getenv('WALLABOT_SENDER_EMAIL')
APP_PASSWORD = os.getenv('WALLABOT_APP_PASSWORD')

# --- CONFIGURATION & SETUP ---

def load_configuration():
    """Loads settings from config.json."""
    print("Loading configuration...")
    if not os.path.exists(CONFIG_FILE):
        print(f"Error: The file '{CONFIG_FILE}' does not exist.")
        sample_config = {
            "search_term": "mountain bike",
            "min_price": 200,
            "max_price": 750,
            "location": "madrid",
            "radius_km": 50,
            "headless_browser": True,
            "save_images": True,
            "max_results": 40
        }
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(sample_config, f, indent=4)
        print(f"A sample '{CONFIG_FILE}' has been created. Please edit it.")
        return None
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def load_seen_ads():
    """Loads seen ad IDs from the file."""
    if not os.path.exists(SEEN_ADS_FILE):
        return set()
    with open(SEEN_ADS_FILE, 'r', encoding='utf-8') as f:
        return set(line.strip() for line in f)

def save_seen_ad(item_id):
    """Saves a new ad ID to the file."""
    with open(SEEN_ADS_FILE, 'a', encoding='utf-8') as f:
        f.write(f"{item_id}\n")

# --- BROWSER AUTOMATION ---

def initialize_driver(config):
    """Sets up and returns the Selenium WebDriver."""
    print("Setting up Chrome browser...")
    options = Options()
    if config.get('headless_browser', True):
        options.add_argument('--headless=new')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920x1080')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
    
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)

def click_load_more(driver):
    """Trata de hacer click en el botón 'load more' por ID o por fallback a walla-button con shadow DOM."""
    try:
        load_more_button_host = driver.find_element(By.CSS_SELECTOR, "#btn-load-more")
        driver.execute_script('arguments[0].shadowRoot.querySelector("button").click()', load_more_button_host)
        print("Clicked the 'load more' button by ID.")
        return True
    except NoSuchElementException:
        walla_buttons = driver.find_elements(By.CSS_SELECTOR, "walla-button")
        button_texts = ["Cargar más", "Ver más productos", "Ver más", "Ver más resultados"]
        for walla_btn in walla_buttons:
            try:
                btn_text = walla_btn.get_attribute("text")
                if btn_text and any(txt in btn_text for txt in button_texts):
                    driver.execute_script('arguments[0].shadowRoot.querySelector("button").click()', walla_btn)
                    print(f"Clicked fallback walla-button: {btn_text}")
                    return True
            except Exception:
                continue
        return False
    except Exception as e:
        print(f"An error occurred while trying to click 'load more': {e}")
        return False

def load_all_results(driver, max_results):
    """Haz scroll y pulsa 'load more' hasta que llegues a max_results o no salgan más."""
    last_count = 0
    attempts_without_growth = 0
    while True:
        # 1) si hay botón → clic
        clicked = click_load_more(driver)
        if clicked:
            time.sleep(2)
        # 2) scroll suave hasta el final de la página
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        # 3) cuántas tarjetas tenemos ahora
        cards = driver.find_elements(By.CSS_SELECTOR, "a.ItemCardList__item")
        current = len(cards)
        print(f"Current number of product cards: {current}")
        # 4) ¿hemos llegado al tope?
        if current >= max_results:
            print(f"Reached {current} results (>= {max_results}).")
            break
        # 5) si no crece en dos iteraciones, salimos
        if current == last_count:
            attempts_without_growth += 1
            if attempts_without_growth >= 2:
                print("No more results after scrolling.")
                break
        else:
            attempts_without_growth = 0
        last_count = current

def extract_new_ads(driver, seen_ads, config):
    """Extracts all product data from the page and returns only the new ones."""
    new_ads = []
    max_results = config.get('max_results', 40)
    product_cards = driver.find_elements(By.CSS_SELECTOR, "a.ItemCardList__item")
    extracted_at = time.strftime('%Y-%m-%d %H:%M:%S')
    for card in product_cards[:max_results]:
        try:
            href = card.get_attribute("href")
            if not href:
                continue
            item_id = href.split('/')[-1]
            if item_id in seen_ads:
                continue
            title = card.get_attribute("title")
            if not title:
                try:
                    title = card.find_element(By.CSS_SELECTOR, '.ItemCard__title').text
                except NoSuchElementException:
                    continue
            price_element = card.find_element(By.CSS_SELECTOR, ".ItemCard__price")
            price_text = price_element.text
            price = (price_text.replace('€','').replace('.','').replace(',','.').strip()).replace('\u00A0','')
            try:
                price = float(price)
            except Exception:
                continue
            ad_details = {"id": item_id, "title": title, "price": price, "link": href, "extracted_at_date": extracted_at}
            if config.get('save_images', False):
                try:
                    img_element = card.find_element(By.CSS_SELECTOR, "img")
                    ad_details["image_url"] = img_element.get_attribute("src")
                except NoSuchElementException:
                    logger.warning(f"Image not found for item: {title}")
            new_ads.append(ad_details)
            logger.info(f"NEW AD: {title} - {price}€")
        except Exception as e:
            logger.error(f"Error processing a product card: {e}")
    return new_ads

# --- DATA HANDLING & NOTIFICATION ---

def download_images(new_ads):
    """Downloads images for the new ads."""
    print("Downloading images for new ads...")
    if not os.path.exists(IMAGES_DIR):
        os.makedirs(IMAGES_DIR)
    for ad in new_ads:
        if "image_url" in ad:
            try:
                response = requests.get(ad["image_url"], timeout=10)
                response.raise_for_status()
                safe_title = "".join(c for c in ad['title'] if c.isalnum() or c in (' ', '_')).rstrip()
                image_filename = f"{ad['id']}_{safe_title[:30]}.jpg"
                image_path = os.path.join(IMAGES_DIR, image_filename)
                with open(image_path, 'wb') as f:
                    f.write(response.content)
                ad["image_path"] = image_path
            except requests.RequestException as e:
                print(f"Failed to download image for {ad['title']}: {e}")

def send_email_alert(new_ads, config, csv_file_path=None, screenshot_path=None):
    """Sends an email with the new ads and optional attachments."""
    if not new_ads:
        logger.info("No new ads found. No email will be sent.")
        return
    recipient = RECIPIENT_EMAIL
    sender = SENDER_EMAIL
    password = APP_PASSWORD
    now_str = time.strftime('%Y-%m-%d %H:%M')
    msg = MIMEMultipart('related')
    msg['Subject'] = f"Wallapop Alert: {now_str} - {len(new_ads)} new ad(s) for '{', '.join([ad['title'] for ad in new_ads])}'"
    msg['From'] = f"Walla-Bot <{sender}>"
    msg['To'] = recipient
    alt_part = MIMEMultipart('alternative')
    msg.attach(alt_part)
    html_body = f"<h1>New deals found</h1>"
    for ad in new_ads:
        html_body += f"<div style='border: 1px solid #ddd; padding: 15px; margin-bottom: 15px; border-radius: 8px;'><a href='{ad['link']}'><h3>{ad['title']}</h3></a><p><strong>Price: {ad['price']}€</strong></p></div>"
    alt_part.attach(MIMEText(html_body, 'html'))
    if csv_file_path and os.path.exists(csv_file_path):
        with open(csv_file_path, 'rb') as f:
            part = MIMEApplication(f.read(), Name=os.path.basename(csv_file_path))
            part['Content-Disposition'] = f'attachment; filename="{os.path.basename(csv_file_path)}"'
            msg.attach(part)
            logger.info(f"Attached CSV: {csv_file_path}")
    if screenshot_path and os.path.exists(screenshot_path):
        with open(screenshot_path, 'rb') as img_file:
            img = MIMEImage(img_file.read(), name=os.path.basename(screenshot_path))
            img.add_header('Content-Disposition', 'attachment', filename=os.path.basename(screenshot_path))
            msg.attach(img)
            logger.info(f"Attached screenshot: {screenshot_path}")
    try:
        logger.info(f"Connecting to SMTP server to send email to {recipient}...")
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(sender, password)
            server.send_message(msg)
        logger.info("Alert email sent successfully.")
    except Exception as e:
        logger.error(f"Error sending email: {e}")

# --- MAIN ORCHESTRATOR ---

def main():
    """Main function to run the Wallapop scraper."""
    config = load_configuration()
    if not config:
        logger.error('No config loaded. Exiting.')
        return
    # Support multiple keywords
    search_terms = config.get('search_terms')
    if not search_terms:
        search_terms = [config.get('search_term')]
    all_new_ads = []
    driver = initialize_driver(config)
    screenshot_path = None
    try:
        for search_term in search_terms:
            logger.info(f"Searching for: {search_term}")
            search_term_url = search_term.replace(' ', '+')
            url = (f"https://es.wallapop.com/app/search?keywords={search_term_url}"
                   f"&min_sale_price={config['min_price']}&max_sale_price={config['max_price']}")
            if 'location' in config and config['location']:
                locations = {
                    "madrid": "latitude=40.4168&longitude=-3.7038",
                    "barcelona": "latitude=41.3851&longitude=2.1734"
                }
                loc_str = locations.get(config['location'].lower())
                if loc_str:
                    radius_m = config.get('radius_km', 50) * 1000
                    url += f"&{loc_str}&distance={radius_m}"
            url += "&order_by=newest"
            logger.info(f"Navigating to: {url}")
            driver.get(url)
            try:
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "onetrust-accept-btn-handler"))).click()
                logger.info("Accepted cookies.")
            except TimeoutException:
                logger.info("No cookies banner found (maybe already accepted). Continuing...")
            time.sleep(2)
            load_all_results(driver, config.get('max_results', 40))
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            clean_keyword = re.sub(r'[^a-zA-Z0-9]+', '_', search_term)
            screenshot_path = os.path.join(SCREENSHOTS_DIR, f"wallapop_search_{clean_keyword}_{timestamp}_screenshot.png")
            driver.save_screenshot(screenshot_path)
            logger.info(f"Screenshot saved to {screenshot_path}")
            seen_ads = load_seen_ads()
            new_ads = extract_new_ads(driver, seen_ads, config)
            if not new_ads:
                logger.info(f"No new ads found for search term: {search_term}")
                continue
            logger.info(f"Found a total of {len(new_ads)} new ads for '{search_term}'.")
            if config.get('save_images'):
                download_images(new_ads)
            # --- Dynamic CSV columns ---
            # Only include columns present in the data
            all_keys = set()
            for ad in new_ads:
                all_keys.update(ad.keys())
            columns = list(all_keys)
            df = pd.DataFrame(new_ads, columns=columns)
            if 'price' in df.columns:
                df['price'] = pd.to_numeric(df['price'], errors='coerce')
            csv_file_path = os.path.join(CSV_DIR, f"wallapop_results_{timestamp}.csv")
            df.to_csv(csv_file_path, index=False)
            logger.info(f"Results saved to {csv_file_path}")
            if config.get('send_email', True):
                send_email_alert(new_ads, config, csv_file_path, screenshot_path)
            else:
                logger.info("send_email is False: Skipping email sending for this run.")
            for ad in new_ads:
                save_seen_ad(ad['id'])
            logger.info(f"Updated seen_ads.txt with {len(new_ads)} new ad IDs.")
            all_new_ads.extend(new_ads)
        # Remove duplicates by ad id
        unique_ads = {ad['id']: ad for ad in all_new_ads}.values()
        unique_ads = list(unique_ads)
        logger.info(f"Total unique new ads found in this run: {len(unique_ads)}")
    except TimeoutException:
        logger.error("Page took too long to load or an element was not found.")
        driver.save_screenshot("debug_screenshot.png")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        driver.save_screenshot("error_screenshot.png")
    finally:
        logger.info("Closing browser...")
        driver.quit()

if __name__ == "__main__":
    main()
