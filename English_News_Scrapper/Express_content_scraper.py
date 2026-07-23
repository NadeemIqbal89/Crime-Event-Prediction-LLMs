import requests
from bs4 import BeautifulSoup
import csv
import time
import os

# Input CSV file
input_file = "express_tribune_news_url_2015.csv"

# Output CSV file
output_file = "express_tribune_full_articles_2015.csv"

# Step 1: Load already processed URLs (if output file exists)
processed_urls = set()
if os.path.exists(output_file):
    with open(output_file, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            processed_urls.add(row["URL"])

# Step 2: Open output CSV in append mode and start scraping
with open(output_file, mode="a", newline="", encoding="utf-8") as out_csv:
    writer = csv.writer(out_csv)

    # Write header only if file was empty or newly created
    if os.stat(output_file).st_size == 0:
        writer.writerow(["Date", "Title", "URL", "Location", "Short News", "Full Article"])

    with open(input_file, mode="r", encoding="utf-8") as in_csv:
        reader = csv.DictReader(in_csv)
        for row in reader:
            date = row["Date"]
            title = row["Title"]
            url = row["URL"]

            if url in processed_urls:
                print(f"⏭ Skipped (already processed): {url}")
                continue

            location = ""
            short_news = ""
            full_article = ""

            try:
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, "html.parser")

                    # Extract location
                    loc_tag = soup.find("strong", class_="location-names")
                    if loc_tag:
                        location = loc_tag.get_text(strip=True).replace(":", "")

                    # Extract story container
                    story_span = soup.find("span", class_="story-text")
                    if story_span:
                        # First paragraph = short news
                        first_p = story_span.find("p")
                        if first_p:
                            short_news = first_p.get_text(strip=True)

                        # All paragraphs = full article
                        all_paragraphs = story_span.find_all("p")
                        full_article = "\n\n".join(
                            p.get_text(strip=True) for p in all_paragraphs if p.get_text(strip=True)
                        )

                    # Save to CSV
                    writer.writerow([date, title, url, location, short_news, full_article])
                    out_csv.flush()  # Ensure data is written in case of shutdown
                    print(f"✅ Saved: {date} | {location} | {title}")

                else:
                    print(f"❌ Failed: {url} (Status {response.status_code})")

            except Exception as e:
                print(f"⚠ Error scraping {url}: {e}")

            # Be polite to the server
            time.sleep(0.2)

print(f"\n🎉 All full articles saved in: {output_file}")
