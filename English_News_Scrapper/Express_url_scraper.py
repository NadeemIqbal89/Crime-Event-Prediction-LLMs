import requests
from bs4 import BeautifulSoup
import csv
from datetime import datetime, timedelta
import os

# Base URL with pagination
base_url_template = "https://tribune.com.pk/listing/web-archive/{date}?page={page}"

# Year to scrape
year = 2015

# CSV file to save results
output_file = "express_tribune_news_url_2015.csv"

# Load already scraped dates (if file exists)
scraped_dates = set()
if os.path.isfile(output_file):
    with open(output_file, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            scraped_dates.add(row["Date"])

# Open the file in append mode
with open(output_file, mode="a", newline="", encoding="utf-8") as csv_file:
    writer = csv.writer(csv_file)

    # If file is new, write header
    if not scraped_dates:
        writer.writerow(["Date", "Title", "URL"])

    # Start date
    start_date = datetime(year, 11, 19)
    end_date = datetime(year, 12, 31)
    current_date = start_date

    while current_date <= end_date:
        formatted_date = current_date.strftime("%Y-%m-%d")

        if formatted_date in scraped_dates:
            print(f"⏭️ Skipped: {formatted_date}")
            current_date += timedelta(days=1)
            continue

        page = 1
        found_any = False

        while True:
            url = base_url_template.format(date=formatted_date, page=page)
            try:
                response = requests.get(url, timeout=10)
                if response.status_code != 200:
                    print(f"❌ Failed: {url} (Status {response.status_code})")
                    break

                soup = BeautifulSoup(response.content, 'html.parser')
                news_list = soup.find('ul', class_='tedit-shortnews listing-page')

                if not news_list:
                    if page == 1:
                        print(f"📭 No articles on {formatted_date}")
                    break

                news_items = news_list.find_all('a', href=True)
                new_articles_found = False

                for item in news_items:
                    news_url = item['href']
                    title_tag = item.find('h2', class_='title-heading')

                    if title_tag and 'tribune.com.pk/story/' in news_url:
                        title = title_tag.get_text(strip=True)
                        writer.writerow([formatted_date, title, news_url])
                        print(f"✅ Saved: {formatted_date} | {news_url}")
                        new_articles_found = True
                        found_any = True

                if not new_articles_found:
                    break

                page += 1

            except Exception as e:
                print(f"⚠️ Error on {url}: {e}")
                break

        if found_any:
            scraped_dates.add(formatted_date)

        current_date += timedelta(days=1)

print(f"\n🎉 Done! All new results appended to '{output_file}'")
