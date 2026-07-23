import scrapy
from urllib.parse import urljoin
from scrapy.http import Request, FormRequest
from scrapy.loader import ItemLoader
from FYP_Scraper.items import NewsArticleItem

class TwentyFourUrduNewsSpider(scrapy.Spider):
    name = "24_news"
    allowed_domains = ["www.24urdu.com"]
    start_urls = ["https://www.24urdu.com/crime-and-punishment"]
    scraped_count = 0
    skipped_count = 0
    current_offset = 0  # Start after initial 20 posts

    custom_settings = {
        'FEED_EXPORT_ENCODING': 'utf-8',
        'FEED_EXPORT_FIELDS': ['title', 'date', 'url', 'content', 'category', 'source', 'reported_time'],
        'USER_AGENT': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',
        'DOWNLOAD_DELAY': 3,
        'DUPEFILTER_DEBUG': True,
        'FEED_URI': '24News.csv',
        'FEED_FORMAT': 'csv',
        'CONCURRENT_REQUESTS_PER_DOMAIN': 1,
        'RETRY_TIMES': 3,
        'RETRY_HTTP_CODES': [500, 502, 503, 504, 522, 524, 408, 429, 403, 0],
        'RETRY_DELAY': 5,
        'DOWNLOADER_MIDDLEWARES': {
            'scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware': 590,
        },
        'COMPRESSION_ENABLED': True,
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.crawled_urls = set()

    def parse(self, response):
        self.logger.info(f"Content-Type: {response.headers.get('Content-Type')}")
        self.logger.info(f"Response body (first 100 chars): {response.body[:100]}")
        if not response.body or b'text/html' not in response.headers.get('Content-Type', b''):
            self.logger.warning(f"Non-HTML response skipped: {response.url}")
            return
        yield from self.extract_articles(response)
        yield from self.request_next_page(response)

    def request_next_page(self, response):
        formdata = {
            'post_per_page': '20',
            'post_listing_limit_offset': str(self.current_offset),
            'directory_name': 'categories_pages',
            'template_name': 'lazy_loading',
            'category_name': 'crime-and-punishment'
        }
        headers = {
            'User-Agent': self.custom_settings['USER_AGENT'],
            'Referer': response.url,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Origin': 'https://www.24urdu.com',
        }
        self.current_offset += 20  # Increment by 20 per page
        yield FormRequest(
            url="https://www.24urdu.com/ajax_post_pagination",
            formdata=formdata,
            headers=headers,
            callback=self.parse_ajax,
            meta={'offset': self.current_offset}
        )

    def parse_ajax(self, response):
        offset = response.meta.get('offset', 'unknown')
        self.logger.info(f"Content-Type (AJAX): {response.headers.get('Content-Type')}")
        self.logger.debug(f"AJAX response body (first 200 chars): {response.body[:200]}")
        if not response.body or b'text/html' not in response.headers.get('Content-Type', b''):
            self.logger.info(f"⏹️ Non-HTML response at offset {offset}. Stopping pagination.")
            return
        # Adjusted selectors based on potential AJAX structure
        links = response.css('article a::attr(href)').getall() or \
                response.css('div.col-md-6 a::attr(href)').getall() or \
                response.css('div.rp-inner a::attr(href)').getall()
        self.logger.debug(f"Found links: {links}")
        unique_links = set(urljoin(response.url, link) for link in links if link)

        if not unique_links:
            self.logger.info(f"⏹️ No more articles found at offset {offset}. Stopping pagination.")
            return

        new_links = [link for link in unique_links if link not in self.crawled_urls]
        if not new_links:
            self.logger.info(f"⏹️ All links at offset {offset} are duplicates. Stopping pagination.")
            return
        self.crawled_urls.update(unique_links)

        for link in new_links:
            yield Request(url=link, callback=self.parse_article)

        yield from self.request_next_page(response)

    def extract_articles(self, response):
        if not response.body or b'text/html' not in response.headers.get('Content-Type', b''):
            self.logger.warning(f"Non-HTML response skipped: {response.url}")
            return
        article_links = response.css('article a::attr(href)').getall() or \
                        response.css('div.col-md-6 a::attr(href)').getall() or \
                        response.css('div.rp-inner a::attr(href)').getall()
        unique_links = set(urljoin(response.url, link) for link in article_links if link)
        for link in unique_links:
            yield Request(url=link, callback=self.parse_article)

    def parse_article(self, response):
        if not response.body or b'text/html' not in response.headers.get('Content-Type', b''):
            self.logger.warning(f"Non-HTML response skipped: {response.url}")
            return
        self.logger.debug(f"Article response body (first 200 chars): {response.body[:200]}")
        loader = ItemLoader(item=NewsArticleItem(), response=response)

        # Fallback selectors for title
        title = response.css('h1::text').get()
        if not title:
            title = response.css('div.rp-inner h4::text').get()
        self.logger.debug(f"Title found: {title}")
        if not title:
            self.logger.warning(f"⏩ Skipped (no title): {response.url}")
            self.skipped_count += 1
            return

        # Extract date and time
        date_time_text = response.css('span.auth-rp-date::text').get() or response.css('span.date::text').get()
        date_value = 'N/A'
        reported_time_value = 'N/A'
        if date_time_text:
            try:
                date_value, reported_time_value = [part.strip() for part in date_time_text.split('|')]
            except Exception as e:
                self.logger.warning(f"⚠️ Failed to parse date/time: {date_time_text}, Error: {e}")

        # Fallback selectors for content
        paragraphs = response.css('div.detail_page_content p::text').getall()
        if not paragraphs:
            paragraphs = response.css('div.entry-content p::text').getall()
        content = ' '.join([p.strip() for p in paragraphs if p.strip()]) if paragraphs else 'N/A'

        if not content:
            self.logger.warning(f"⚠️ No content found: {response.url}")

        loader.add_value('date', date_value)
        loader.add_value('title', title.strip())
        loader.add_value('url', response.url)
        loader.add_value('content', content)
        loader.add_value('category', 'N/A')
        loader.add_value('source', '24_news')
        loader.add_value('reported_time', reported_time_value)

        item = loader.load_item()
        self.logger.info(f"✅ Article scraped: {response.url}, Item: {item}")
        self.scraped_count += 1
        yield item

    def closed(self, reason):
        self.logger.info("🕒 Spider closed")
        self.logger.info(f"✅ Total articles scraped: {self.scraped_count}")
        self.logger.info(f"⏩ Total skipped: {self.skipped_count}")
        self.logger.info(f"📑 Reason: {reason}")