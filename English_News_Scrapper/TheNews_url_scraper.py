
import requests
from bs4 import BeautifulSoup
import csv
from datetime import datetime, timedelta
import os

# Constants
url = "https://www.thenews.com.pk/todaypaper-archive"
output_file = "the_news_2023_new.csv"

# Setup session
session = requests.Session()
headers = {
    "User-Agent": "Mozilla/5.0",
    "Referer": url
}

# Load already saved URLs to avoid duplicates
existing_urls = set()
if os.path.exists(output_file):
    with open(output_file, newline="", encoding="utf-8") as existing_file:
        reader = csv.DictReader(existing_file)
        for row in reader:
            existing_urls.add(row["URL"])

# Open CSV in append mode
with open(output_file, mode="a", newline="", encoding="utf-8") as csvfile:
    writer = csv.writer(csvfile)

    # Write header if file is empty
    if os.stat(output_file).st_size == 0:
        writer.writerow(["Date", "Title", "URL", "City"])

    start_date = datetime(2023, 1, 1)
    end_date = datetime(2023, 1, 6)
    current_date = start_date

    while current_date <= end_date:
        date_str = current_date.strftime("%Y-%m-%d")
        print(f"\n🔎 Checking for articles on: {date_str}")

        payload = {
            "filter_archive_date": date_str,
            "submit_archive": "Submit"
        }

        try:
            response = session.post(url, headers=headers, data=payload, timeout=10)
            if response.status_code != 200:
                print(f"❌ Failed to fetch for {date_str} (Status {response.status_code})")
                current_date += timedelta(days=1)
                continue

            soup = BeautifulSoup(response.content, "html.parser")
            found = False

            # 🟢 1. Fetch general /print/ article links
            all_links = soup.find_all("a", href=True)
            for link in all_links:
                href = link["href"]
                title = link.get("title", "").strip()
                if not title:
                    title = link.get_text(strip=True)

                if "/print/" in href and title:
                    full_url = f"https://www.thenews.com.pk{href}" if href.startswith("/") else href
                    if full_url in existing_urls:
                        print(f"⏭️ Skipped: {date_str} | {full_url}")
                        continue
                    writer.writerow([date_str, title, full_url, ""])  # No city for general links
                    existing_urls.add(full_url)
                    print(f"✅ Saved: {date_str} | {full_url}")
                    found = True

            # 🟢 2. Fetch article links under city headings
            for section in soup.find_all("div", class_="print-top-story"):
                heading_tag = section.find("a", class_="title_text")
                city = heading_tag.get("title", "").capitalize() if heading_tag else ""

                for article_link in section.find_all("a", href=True):
                    href = article_link["href"]
                    if "/print/" not in href:
                        continue

                    title = article_link.get("title", "").strip()
                    if not title:
                        title = article_link.get_text(strip=True)

                    if not title:
                        continue

                    full_url = f"https://www.thenews.com.pk{href}" if href.startswith("/") else href
                    if full_url in existing_urls:
                        continue

                    writer.writerow([date_str, title, full_url, city])
                    existing_urls.add(full_url)
                    print(f"✅ Saved: {date_str} | {full_url} | City: {city}")
                    found = True

            if not found:
                print(f"📭 No new articles found for {date_str}")

        except Exception as e:
            print(f"⚠️ Error on {date_str}: {e}")

        current_date += timedelta(days=1)

print(f"\n🎉 Done! New results added to '{output_file}'")
