import requests
from bs4 import BeautifulSoup
import csv
import os

input_csv = "the_news_2023_new.csv"
output_csv = "the_news_articles_2023.csv"
headers = {
    "User-Agent": "Mozilla/5.0"
}

# Load already processed URLs
processed_urls = set()
if os.path.exists(output_csv):
    with open(output_csv, newline='', encoding="utf-8") as out_file:
        reader = csv.DictReader(out_file)
        for row in reader:
            processed_urls.add(row["URL"])

# Open input and output files
with open(input_csv, newline='', encoding="utf-8") as infile, \
     open(output_csv, mode="a", newline='', encoding="utf-8") as outfile:

    reader = csv.DictReader(infile)
    writer = csv.writer(outfile)

    # Write header if output file is empty
    if os.stat(output_csv).st_size == 0:
        writer.writerow(["Date", "Title", "URL", "City", "Article"])

    for row in reader:
        url = row["URL"]
        date = row["Date"]
        title = row["Title"]

        if url in processed_urls:
            print(f"Date Skipped: {date}")
            continue  # Skip already processed

        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code != 200:
                continue

            soup = BeautifulSoup(response.content, "html.parser")

            content_div = soup.find("div", class_="story-detail")
            paragraphs = content_div.find_all("p") if content_div else []

            article_paragraphs = [p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)]
            article = "\n".join(article_paragraphs)

            if not article_paragraphs:
                continue

            # Extract city from the first paragraph (e.g., "ISLAMABAD: ...")
            first_para = article_paragraphs[0]
            city = ""
            if ":" in first_para:
                city = first_para.split(":")[0].strip()
                if len(city.split()) > 3 or not city.isupper():  # Heuristic check
                    city = ""

            writer.writerow([date, title, url, city, article])
            processed_urls.add(url)
            print(f"Date Saved: {date}")

        except Exception:
            continue

print(f"\n📁 All available articles saved to '{output_csv}'")
