import scrapy
from datetime import datetime, timedelta
from w3lib.html import remove_tags
from FYP_Scraper.items import NewsArticleItem
from scrapy.loader import ItemLoader

class DunyaNewsSpider(scrapy.Spider):
    name = "dunya_news"
    allowed_domains = ["dunya.com.pk"]
    ajax_url = "https://dunya.com.pk/newweb/modules/ajax_news_archive.php"

    def start_requests(self):
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        current_date = end_date

        while current_date >= start_date:
            date_str = current_date.strftime("%Y-%m-%d")
            form_data = {
                "search_date": date_str,
                "cat_id": "6"  # Crime category
            }
            yield scrapy.FormRequest(
                url=self.ajax_url,
                method="POST",
                formdata=form_data,
                callback=self.parse_archive,
                meta={"date": date_str}
            )
            current_date -= timedelta(days=1)

    def parse_archive(self, response):
        for news_item in response.css("ul.mt-2.py-3 li a.one-line::attr(href)").getall():
            yield response.follow(
                news_item,
                callback=self.parse_news,
                meta={"date": response.meta["date"]}
            )

    def parse_news(self, response):
        loader = ItemLoader(item=NewsArticleItem(), response=response)

        title = response.css("h2.taza-tareen-story-title::text").get()
        loader.add_value("title", title)

        # Select <p> tags directly under <article>, or with specific class, excluding .installApp descendants
        content_elements = response.css("article > p, article p.border.p-3.text-primary.shadow-sm.my-2").getall()
        # Filter out <p> tags that are descendants of .installApp
        content_elements = [c for c in content_elements if not response.css("article .installApp p").re(response.xpath(f"//p[contains(., '{remove_tags(c)}')]").get())]
        content = " ".join(remove_tags(c).strip() for c in content_elements if c)
        loader.add_value("content", content)

        date = response.meta["date"]
        loader.add_value("date", date)

        reported_time = response.css("time.font-weight-bold.text-dark::text").get()
        reported_time = "N/A"
        loader.add_value("reported_time", reported_time)

        loader.add_value("url", response.url)
        loader.add_value("source", "dunya_news")
        loader.add_value("category", "N/A")

        yield loader.load_item()
# scrapy crawl dunya -o dunyaNews.csv --loglevel DEBUG