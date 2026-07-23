import scrapy
from datetime import datetime
from ..items import NewsArticleItem


class NawaiwaqtSpider(scrapy.Spider):
    name = "nawaiwaqt"
    allowed_domains = ["www.nawaiwaqt.com.pk"]
    start_urls = ["https://www.nawaiwaqt.com.pk"]

    def __init__(self):
        super().__init__()
        self.seen_urls = set()
        self.cutoff_date = datetime(2015, 1, 1)
        self.should_stop = False
        self.ajax_url = 'https://www.nawaiwaqt.com.pk/ajax_post_pagination'

    def start_requests(self):  
        formdata = {
            'post_per_page': '28',
            'post_listing_limit_offset': '0',
            'directory_name': 'categories_pages',
            'template_name': 'lazy_loading',
            'category_name': 'crime-court',
            'show_authors': '1'
        }
        
        yield scrapy.FormRequest(
            url=self.ajax_url,
            formdata=formdata,
            callback=self.parse_ajax,
            meta={'offset': 28}
        ) 
    

    def parse_ajax(self, response):
        articles = response.css('article')
        
        for article in articles:
            url = article.css('a::attr(href)').get()
            
            if url and url not in self.seen_urls:
                self.seen_urls.add(url)
                yield response.follow(url, callback=self.parse_article)
        
        current_offset = response.meta.get('offset', 0)
        next_offset = current_offset + 28  
        if len(articles) == 28:  
            formdata = {
                'post_per_page': '28',
                'post_listing_limit_offset': str(next_offset),  
                'directory_name': 'categories_pages',
                'template_name': 'lazy_loading',
                'category_name': 'crime-court',
                'show_authors': '1'
            }
            
            yield scrapy.FormRequest(
                url=self.ajax_url,
                formdata=formdata,
                callback=self.parse_ajax, 
                meta={'offset': next_offset} 
            )

    def parse_date(self, date_str):
        """Convert date string to datetime object"""
        try:
            return datetime.strptime(date_str.strip(), "%b %d, %Y")
        except Exception as e:
            self.logger.error(f"Error parsing date {date_str}: {str(e)}")
            return None
        
    
    def parse_article(self, response):
        date_str = response.css('div.jeg_meta_date::text').get().split('|')[0].strip()
        article_date = self.parse_date(date_str)
        
        if article_date and article_date < self.cutoff_date:
            self.logger.info(f"Found article from {date_str}, stopping spider")
            self.should_stop = True
            return

        item = NewsArticleItem()
        title = response.css('h1.detail-page-main-title::text').get()
        content = response.css('div.news-detail-content-class p::text').getall()
        url = response.url
        
        item['title'] = title
        item['content'] = "\n".join(content)
        item['url'] = url
        item['date'] = date_str
        item['source'] = 'nawaiwaqt'
        item['category'] = 'N/A'
        item['reported_time'] =  "N/A"
        
        # self.logger.info(f"Scraped article from {date_str}: {title}")
        yield item
