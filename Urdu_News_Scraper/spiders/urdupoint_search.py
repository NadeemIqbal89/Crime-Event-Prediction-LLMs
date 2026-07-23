"""
UrduPoint search scraper — Google CSE on search.php.

Collects up to 100 results per search query (Google limit). Use multiple
QUERIES (pipe-separated) to cover more than 100 articles total.
"""

from __future__ import annotations

import json
import re
from urllib.parse import quote

import scrapy
from scrapy.http import Request

from FYP_Scraper.content_utils import (
    extract_urdupoint_body,
    normalize_urdupoint_article_url,
    parse_urdupoint_date,
)
from FYP_Scraper.items import NewsArticleItem

# Extra queries to pull more than 100 articles (100 max per query from Google CSE)
ZIYADATI_QUERY_VARIANTS = (
    "زیادتی",
    "زیادتی کی خبر",
    "زیادتی کی خبریں",
    "زیادتی کیس",
    "زیادتی پر",
    "زیادتی پر کیس",
    "عورت زیادتی",
    "بچوں سے زیادتی",
)


class UrduPointSearchSpider(scrapy.Spider):
    name = "urdupoint_search"
    allowed_domains = ["urdupoint.com", "www.urdupoint.com"]
    search_base = "https://www.urdupoint.com/daily/search.php"
    playwright_bypass = True

    custom_settings = {
        "PLAYWRIGHT_BYPASS_ENABLED": True,
        "PLAYWRIGHT_WAIT_MS": 2500,
        "PLAYWRIGHT_FAST_WAIT_MS": 300,
        "COOKIES_ENABLED": True,
        "CONCURRENT_REQUESTS": 4,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 4,
        "DOWNLOAD_DELAY": 0,
        "RETRY_TIMES": 1,
        "RETRY_HTTP_CODES": [500, 502, 503, 504, 408, 429],
        "DOWNLOADER_MIDDLEWARES": {
            "scrapy.downloadermiddlewares.useragent.UserAgentMiddleware": None,
            "scrapy.downloadermiddlewares.retry.RetryMiddleware": 500,
            "scrapy.downloadermiddlewares.httpproxy.HttpProxyMiddleware": None,
            "FYP_Scraper.middlewares.RandomProxyMiddleware": None,
            "FYP_Scraper.playwright_bypass.PlaywrightBypassMiddleware": 580,
            "FYP_Scraper.middlewares.RandomUserAgentMiddleware": None,
        },
    }

    def __init__(
        self,
        query: str = "زیادتی",
        queries: str | None = None,
        max_pages: str = "all",
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        mp = str(max_pages).strip().lower()
        self.max_pages = 0 if mp in ("all", "0", "") else int(max_pages)
        self.seen_urls: set[str] = set()
        self.queries = self._parse_queries(queries, query)

    def _parse_queries(self, queries: str | None, query: str) -> list[str]:
        if queries and str(queries).strip():
            parts = re.split(r"[|,]", str(queries))
            return [q.strip() for q in parts if q.strip()]
        q = str(query).strip()
        if q == "زیادتی":
            return list(ZIYADATI_QUERY_VARIANTS)
        return [q]

    def start_requests(self):
        # One Playwright pass: all queries × up to 10 CSE pages, then queue articles
        first = self.queries[0]
        yield Request(
            url=f"{self.search_base}?q={quote(first)}&num=10",
            callback=self.parse_search_collected,
            meta={
                "dont_proxy": True,
                "playwright_search_collect_all": True,
                "cse_queries": self.queries,
                "cse_max_pages": self.max_pages,
            },
            priority=100,
            dont_filter=True,
        )

    def parse_search_collected(self, response):
        if response.status >= 500 or not (response.text or "").strip():
            self.logger.error(
                "Search collection failed (HTTP %s). Check Playwright / Cloudflare.",
                response.status,
            )
            return

        if "Just a moment" in response.text:
            self.logger.warning("Search blocked by Cloudflare")
            return

        try:
            data = json.loads(response.text)
            links = data.get("links", [])
            per_query = data.get("per_query", {})
            errors = data.get("errors", {})
        except json.JSONDecodeError:
            links = response.css("a.gs-title::attr(href)").getall()
            per_query = {}
            errors = {}

        if errors:
            self.logger.warning("CSE errors: %s", errors)
        if per_query:
            self.logger.info("Links per query: %s", per_query)

        if not links:
            self.logger.error("No article links collected from Google CSE.")
            return

        count = 0
        skipped = 0
        for href in links:
            url = normalize_urdupoint_article_url(
                response.urljoin(href.strip()) if isinstance(href, str) else str(href)
            )
            if not url:
                skipped += 1
                continue
            if url in self.seen_urls:
                continue
            self.seen_urls.add(url)
            count += 1
            yield Request(
                url=url,
                callback=self.parse_article,
                meta={
                    "url": url,
                    "date": "N/A",
                    "reported_time": "N/A",
                    "category": "ziyadati",
                    "dont_proxy": True,
                    "playwright_fast": True,
                },
                dont_filter=True,
            )

        pages_label = "all" if self.max_pages == 0 else str(self.max_pages)
        self.logger.info(
            "%d queries, %d raw links, +%d articles queued (%d skipped invalid, "
            "%d unique total; max %s CSE pages/query)",
            len(self.queries),
            len(links),
            count,
            skipped,
            len(self.seen_urls),
            pages_label,
        )

    def parse_article(self, response):
        if response.status in (403, 503, 404, 502) or "Just a moment" in response.text:
            self.logger.warning(f"Blocked or failed article: {response.meta['url']}")
            return

        url = response.meta["url"]
        title = (response.css("h1.urdu::text").get() or "N/A").strip()
        content = extract_urdupoint_body(response)

        if not content or len(content) < 50:
            if "livenews" in url and not response.meta.get("playwright_full_retry"):
                self.logger.info(f"Retrying livenews with full page load: {url}")
                yield Request(
                    url=url,
                    callback=self.parse_article,
                    meta={
                        **response.meta,
                        "dont_proxy": True,
                        "playwright_fast": False,
                        "playwright_full_retry": True,
                    },
                    dont_filter=True,
                )
                return
            self.logger.warning(f"Short/empty content: {url}")
            return

        date, reported_time = parse_urdupoint_date(response, url=url)

        item = NewsArticleItem()
        item["url"] = url
        item["date"] = date
        item["title"] = title
        item["content"] = content
        item["source"] = "urdupoint"
        item["reported_time"] = reported_time
        item["category"] = response.meta["category"]
        yield item
