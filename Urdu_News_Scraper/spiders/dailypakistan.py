import scrapy
from urllib.parse import urljoin
from scrapy.http import FormRequest
from scrapy.loader import ItemLoader
from datetime import datetime
import re
from FYP_Scraper.items import NewsArticleItem

class DailyPakistanSpider(scrapy.Spider):
    name = "daily_Pakistan"
    allowed_domains = ["dailypakistan.com.pk"]
    start_urls = ["https://dailypakistan.com.pk/crime-and-justice"]
    scraped_count = 0
    skipped_count = 0 
    custom_settings = {
        'FEED_EXPORT_ENCODING': 'utf-8',
        'FEED_EXPORT_FIELDS': ['title', 'date', 'url', 'content', 'category', 'source', 'reported_time'],
        'USER_AGENT': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'DOWNLOAD_DELAY': 2,
        'DUPEFILTER_DEBUG': True,
    }

    def parse(self, response):
        yield from self.extract_articles(response)

        self.current_page = 1
        yield from self.request_next_page()

    def request_next_page(self):
        offset = self.current_page * 36
        payload = {
            "post_per_page": "36",
            "post_listing_limit_offset": str(offset),
            "directory_name": "categories_pages",
            "template_name": "lazy_loading",
            "category_name": "crime-and-justice"
        }
        headers = {
            'User-Agent': self.custom_settings['USER_AGENT'],
            'Referer': 'https://dailypakistan.com.pk/crime-and-justice',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
        }
        self.logger.debug(f"Requesting AJAX page {self.current_page + 1} with offset {offset}")
        yield FormRequest(
            url="https://dailypakistan.com.pk/ajax_post_pagination",
            formdata=payload,
            headers=headers,
            callback=self.parse_ajax,
            meta={'page': self.current_page + 1}
        )

    def parse_ajax(self, response):
        page = response.meta.get('page', 'unknown')
        links = response.css('div.post-title.prr-post-1-tt-div a::attr(href)').getall()
        self.logger.debug(f"Page {page}: Found {len(links)} links")
        
        if not links:
            self.logger.info(f"📌 No more articles found on page {page}. Stopping pagination.")
            return

        for link in links:
            full_url = urljoin(response.url, link)
            self.logger.debug(f"Found AJAX URL: {full_url}")
            match = re.search(r'/(\d{2})-([A-Za-z]{3})-(\d{4})/\d+$', full_url)
            if match:
                year = int(match.group(3))
                if 2015 <= year <= 2025:
                    yield scrapy.Request(url=full_url, callback=self.parse_article)

        self.current_page += 1
        yield from self.request_next_page()

    def extract_articles(self, response):
        article_links = response.css('div.post-title.prr-post-1-tt-div a::attr(href)').getall()
        self.logger.debug(f"Initial page: Found {len(article_links)} links")
        for link in article_links:
            full_url = urljoin(response.url, link)
            self.logger.debug(f"Found URL: {full_url}")
            match = re.search(r'/(\d{2})-([A-Za-z]{3})-(\d{4})/\d+$', full_url)
            if match:
                year = int(match.group(3))
                if 2015 <= year <= 2025:
                    yield scrapy.Request(url=full_url, callback=self.parse_article)

    def parse_article(self, response):
        loader = ItemLoader(item=NewsArticleItem(), response=response)

        title = response.css('h1::text').get()
        paragraphs = response.css('div.news-detail-content-class p:not(:empty)::text').getall()
        content = ' '.join([p.strip() for p in paragraphs if p.strip()])
        date_text = response.css('div.large-post-meta span::text').get()

        date_value = 'N/A'
        reported_time_value = 'N/A'
        if date_text:
            try:
                parts = date_text.split('|')
                if len(parts) == 2:
                    date_value = parts[0].strip()
                    reported_time_value = parts[1].strip()
                else:
                    date_value = date_text.strip()
            except Exception as e:
                self.logger.warning(f"⚠️ Failed to parse date: {date_text}, Error: {e}")

        if not title:
            self.logger.warning(f"⚠️ Skipped (no title): {response.url}")
            self.skipped_count += 1
            return

        if not content:
            self.logger.warning(f"⚠️ No content found: {response.url}, Paragraphs: {paragraphs}")

        loader.add_value('date', date_value)
        loader.add_value('title', title)
        loader.add_value('url', response.url)
        loader.add_value('content', content or 'N/A')
        loader.add_value('category', 'N/A')
        loader.add_value('source', 'daily_pakistan')
        loader.add_value('reported_time', reported_time_value)

        self.logger.info(f"✅ Article scraped: {response.url}")
        self.scraped_count += 1
        yield loader.load_item()

    def closed(self, reason):
        self.logger.info("📦 Spider closed")
        self.logger.info(f"✅ Total articles scraped: {self.scraped_count}")
        self.logger.info(f"⏩ Total skipped: {self.skipped_count}")
        self.logger.info(f"📁 Reason: {reason}")