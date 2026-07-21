import time
import os
import random
import csv
import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options

# ----------------- User config -----------------
INPUT_FILE = "2020_All_URLs.csv"
OUTPUT_FILE = "2020_All_News_Content.csv"
PROCESSED_FILE = "2020_Processed_URLs.txt"

# Small/large random delays between requests to appear human
DELAY_MIN = 0.8
DELAY_MAX = 2.0



# Optional: run with headless=False if you want to watch the browser
HEADLESS = False
# ------------------------------------------------

def init_driver(headless=HEADLESS):
    opts = Options()

    if headless:
        opts.add_argument("--headless=new")  # modern headless
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option('useAutomationExtension', False)

    ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    opts.add_argument(f"--user-agent={ua}")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=opts)

    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
window.chrome = { runtime: {} };
Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
Object.defineProperty(navigator, 'languages', {get: () => ['en-US','en']});
"""
        })
    except Exception:
        pass

    return driver

def extract_article_text(html):
    sp = BeautifulSoup(html, "html.parser")
    outDiv = sp.find('div', class_='template__main')
    story = outDiv.find('div', class_='story__content') if outDiv else None

    text = ""
    if story:
        for p_tag in story.find_all('p'):
            text += " " + p_tag.get_text()
    return text.strip()

def main():
    if not os.path.exists(INPUT_FILE):
        print(f"Input file not found: {INPUT_FILE}")
        return

    df = pd.read_csv(INPUT_FILE)

    # Load processed IDs
    processed_ids = set()
    if os.path.exists(PROCESSED_FILE):
        with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
            processed_ids = set(line.strip() for line in f if line.strip())
        print(f"🔄 Resuming... {len(processed_ids)} URLs already processed")

    # Ensure output CSV exists with correct header
    if not os.path.exists(OUTPUT_FILE) or os.path.getsize(OUTPUT_FILE) == 0:
        with open(OUTPUT_FILE, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["ID", "date", "URL", "title", "content"])  # header

    driver = init_driver()

    try:
        for idx, row in df.iterrows():
            NewsId = str(row["ID"])
            if NewsId in processed_ids:
                print(f"⏭️ Skipping already processed News ID {NewsId}")
                continue

            date = row["date"]
            url = row["URL"]
            title = row["title"]

            print(f"Fetching News ID {NewsId} → {url}")
            time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

            try:
                driver.get(url)
                time.sleep(random.uniform(1.0, 2.5))  # wait for JS
                html = driver.page_source
                text = extract_article_text(html)

                if not text:
                    sp = BeautifulSoup(html, "html.parser")
                    paragraphs = sp.find_all("p")
                    text = " ".join(p.get_text() for p in paragraphs)[:20000]

            except Exception as ex:
                print(f"⚠️ Failed for {url}: {ex}")
                text = f"ERROR: {ex}"

            # ✅ Append row immediately (atomic write)
            with open(OUTPUT_FILE, "a", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([NewsId, date, url, title, text])

            # ✅ Mark processed after successful save
            with open(PROCESSED_FILE, "a", encoding="utf-8") as f:
                f.write(NewsId + "\n")
            processed_ids.add(NewsId)

            print(f"✅ Saved News ID {NewsId} (content length: {len(text)})")

            # Optional backup every 100 articles
            if len(processed_ids) % 100 == 0:
                import shutil
                backup_name = f"{OUTPUT_FILE}.bak_{len(processed_ids)}"
                shutil.copy(OUTPUT_FILE, backup_name)
                print(f"💾 Backup saved: {backup_name}")

    finally:
        driver.quit()

    print("🎉 All done — results saved to:", OUTPUT_FILE)

if __name__ == "__main__":
    main()
