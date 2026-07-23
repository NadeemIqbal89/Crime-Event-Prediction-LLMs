"""
Playwright Cloudflare bypass — async worker with fast fetch + single-pass search.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import threading
from concurrent.futures import Future
from dataclasses import dataclass
from urllib.parse import parse_qsl, quote, urlparse

from scrapy.exceptions import NotConfigured
from scrapy.http import HtmlResponse, Request

from FYP_Scraper.content_utils import is_valid_urdupoint_article_url, normalize_urdupoint_article_url

logger = logging.getLogger(__name__)

CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

STEALTH_INIT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.chrome = { runtime: {} };
"""

GRAB_CSE_LINKS_JS = """
() => {
  const out = [];
  document.querySelectorAll('a.gs-title').forEach((a) => {
    let h = (a.href || '').trim();
    if (!h || !h.includes('urdupoint.com') || !h.endsWith('.html') || h.includes('search.php'))
      return;
    if (h.startsWith('http://'))
      h = 'https://' + h.slice(7);
    out.push(h);
  });
  return out;
}
"""

CSE_CURRENT_PAGE_JS = """
() => {
  const cur = document.querySelector('.gsc-cursor-current-page');
  if (!cur) return '';
  return (cur.innerText || cur.textContent || '').trim();
}
"""

URDUPOINT_SEARCH_BASE = "https://www.urdupoint.com/daily/search.php"

BLOCK_RESOURCE_TYPES = {"image", "media", "font"}
BLOCK_URL_PARTS = (
    "googletagmanager",
    "google-analytics",
    "doubleclick",
    "googlesyndication",
    "facebook.net",
    "twitter.com",
    "adservice",
    "ads.",
    "cse.google.com/ads",
)


@dataclass
class _FetchJob:
    request: Request
    referer: str
    future: Future


def _windows_event_loop_policy():
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


class _PlaywrightAsyncWorker:
    def __init__(self, headless: bool, wait_ms: int, fast_wait_ms: int):
        self.headless = headless
        self.wait_ms = wait_ms
        self.fast_wait_ms = fast_wait_ms
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._jobs: asyncio.Queue | None = None
        self._ready = threading.Event()
        self._error: BaseException | None = None
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None
        self._stop = False
        self._cf_cleared = False

    def start(self):
        self._thread = threading.Thread(target=self._thread_main, daemon=True, name="playwright-async")
        self._thread.start()
        if not self._ready.wait(timeout=120):
            raise RuntimeError("Playwright worker failed to start within 120s")
        if self._error:
            raise self._error

    def stop(self):
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._shutdown(), self._loop).result(timeout=30)
        if self._thread:
            self._thread.join(timeout=30)

    @staticmethod
    def _job_timeout(request: Request) -> int:
        custom = request.meta.get("playwright_timeout")
        if custom is not None:
            return int(custom)
        if request.meta.get("playwright_search_collect_all"):
            n = len(request.meta.get("cse_queries") or [1])
            # ~4 min per query (8 queries ≈ 32 min)
            return max(900, n * 240)
        if request.meta.get("playwright_search_collect"):
            return 600
        return 120

    def fetch(self, request: Request, referer: str, timeout: int | None = None) -> HtmlResponse:
        if not self._loop:
            raise RuntimeError("Playwright worker not started")
        job_timeout = timeout if timeout is not None else self._job_timeout(request)
        future: Future = Future()
        job = _FetchJob(request=request, referer=referer, future=future)
        asyncio.run_coroutine_threadsafe(self._jobs.put(job), self._loop).result(timeout=10)
        return future.result(timeout=job_timeout)

    def _thread_main(self):
        _windows_event_loop_policy()
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._async_main())
        except Exception as exc:
            self._error = exc
            logger.exception("Playwright worker crashed: %s", exc)
        finally:
            self._ready.set()
            self._loop.close()

    async def _route_handler(self, route):
        if route.request.resource_type in BLOCK_RESOURCE_TYPES:
            await route.abort()
            return
        url = route.request.url.lower()
        if any(p in url for p in BLOCK_URL_PARTS):
            await route.abort()
            return
        await route.continue_()

    async def _async_main(self):
        from playwright.async_api import async_playwright

        self._jobs = asyncio.Queue()
        try:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=self.headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ],
            )
            self._context = await self._browser.new_context(
                user_agent=CHROME_UA,
                locale="ur-PK",
                viewport={"width": 1280, "height": 720},
            )
            await self._context.route("**/*", self._route_handler)
            await self._context.add_init_script(STEALTH_INIT_SCRIPT)
            self._page = await self._context.new_page()
            logger.info("Playwright Chromium started (fast mode)")
            self._ready.set()

            while not self._stop:
                try:
                    job = await asyncio.wait_for(self._jobs.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                try:
                    result = await self._fetch_async(job.request, job.referer)
                    job.future.set_result(result)
                except Exception as exc:
                    job.future.set_exception(exc)
        except Exception as exc:
            self._error = exc
            self._ready.set()
            raise
        finally:
            await self._cleanup()

    async def _shutdown(self):
        self._stop = True
        await self._cleanup()

    async def _cleanup(self):
        if self._page and not self._page.is_closed():
            await self._page.close()
        self._page = None
        if self._context:
            await self._context.close()
        self._context = None
        if self._browser:
            await self._browser.close()
        self._browser = None
        if self._playwright:
            await self._playwright.stop()
        self._playwright = None

    async def _get_page(self):
        if self._page is None or self._page.is_closed():
            self._page = await self._context.new_page()
        return self._page

    async def _wait_cloudflare(self, page, short: bool = False):
        if self._cf_cleared and short:
            await page.wait_for_timeout(self.fast_wait_ms)
            return
        for _ in range(6):
            title = await page.title()
            if "Just a moment" not in (title or ""):
                self._cf_cleared = True
                break
            await page.wait_for_timeout(1500)
        await page.wait_for_timeout(self.fast_wait_ms if short else self.wait_ms)

    async def _wake_lazy_scripts(self, page):
        await page.evaluate(
            """() => {
                ['mousemove', 'keydown', 'touchstart'].forEach((e) =>
                    window.dispatchEvent(new Event(e, { bubbles: true }))
                );
            }"""
        )
        await page.wait_for_timeout(800)

    async def _find_cse_context(self, page):
        """Frame or Page that hosts CSE results and pagination (.gsc-cursor)."""
        best = page
        best_score = 0
        candidates: list = [page]
        for frame in page.frames:
            if frame not in candidates:
                candidates.append(frame)
        for ctx in candidates:
            try:
                titles = await ctx.locator("a.gs-title").count()
                cursor = await ctx.locator(".gsc-cursor-page").count()
                score = titles + (cursor * 2)
                if score > best_score:
                    best_score = score
                    best = ctx
            except Exception:
                continue
        if best_score == 0:
            logger.warning("CSE context: no gs-title/cursor found, using main page")
        return best

    async def _grab_cse_links(self, ctx, seen: set[str]) -> int:
        hrefs = await ctx.evaluate(GRAB_CSE_LINKS_JS)
        return sum(1 for h in hrefs if self._add_article_link(seen, h))

    def _add_article_link(self, seen: set[str], raw_url: str) -> bool:
        url = normalize_urdupoint_article_url(raw_url)
        if not url or url in seen:
            return False
        seen.add(url)
        return True

    async def _cse_click_next(self, ctx) -> tuple[bool, str]:
        """
        Click the next CSE page control (sibling of current, or '...').

        Google only renders a small window of page numbers (e.g. 1 2 3 4 5 …).
        You cannot jump to page 7 until you advance sequentially — direct goto fails.
        """
        pages = ctx.locator(".gsc-cursor-page")
        n = await pages.count()
        if n == 0:
            return False, "no-cursor"

        cur_idx = -1
        for i in range(n):
            cls = await pages.nth(i).get_attribute("class") or ""
            if "gsc-cursor-current-page" in cls:
                cur_idx = i
                break

        if cur_idx < 0:
            return False, "no-current"

        if cur_idx + 1 < n:
            nxt = pages.nth(cur_idx + 1)
            label = (await nxt.inner_text() or "").strip()
            try:
                await nxt.scroll_into_view_if_needed()
                await nxt.click(timeout=8000)
                return True, label
            except Exception as exc:
                logger.debug("CSE next click failed (%s): %s", label, exc)

        for i in range(n):
            label = (await pages.nth(i).inner_text() or "").strip()
            if label in ("...", "…"):
                try:
                    await pages.nth(i).click(timeout=8000)
                    return True, label
                except Exception as exc:
                    logger.debug("CSE ellipsis click failed: %s", exc)

        return False, "no-next"

    async def _wait_cse_results(self, ctx, page, prev_label: str = "") -> None:
        try:
            await ctx.wait_for_function(
                """(prev) => {
                  const cur = document.querySelector('.gsc-cursor-current-page');
                  if (!cur) return false;
                  const t = (cur.innerText || cur.textContent || '').trim();
                  if (prev && t === prev) return false;
                  return document.querySelectorAll('a.gs-title').length > 0;
                }""",
                arg=prev_label,
                timeout=12000,
            )
        except Exception:
            await page.wait_for_timeout(2000)
        else:
            await page.wait_for_timeout(600)

    async def _paginate_cse(self, ctx, page, seen: set[str], max_pages: int, query: str) -> int:
        scrape_all = not max_pages or max_pages <= 0
        # Google CSE max 10 result pages; advance one step at a time via "next"
        max_clicks = 9 if scrape_all else max(0, min(max_pages, 10) - 1)
        before_total = len(seen)

        await self._grab_cse_links(ctx, seen)

        for round_idx in range(max_clicks):
            prev = await ctx.evaluate(CSE_CURRENT_PAGE_JS)
            ok, label = await self._cse_click_next(ctx)
            if not ok:
                logger.info(
                    "CSE %r: pagination ended (%s) after %d page(s), %d links",
                    query,
                    label,
                    round_idx + 1,
                    len(seen),
                )
                break

            await self._wait_cse_results(ctx, page, prev)
            before_round = len(seen)
            added = await self._grab_cse_links(ctx, seen)
            logger.info(
                "CSE %r: page turn %r (+%d links, total %d)",
                query,
                label,
                added,
                len(seen),
            )
            if len(seen) == before_round:
                logger.info("CSE %r: no new links; stopping pagination", query)
                break

        return len(seen) - before_total

    async def _load_cse_search(self, page, search_url: str):
        await page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
        await self._wait_cloudflare(page)
        await self._wake_lazy_scripts(page)
        try:
            await page.wait_for_selector("a.gs-title, .gsc-result", timeout=25000)
        except Exception:
            logger.warning("Google CSE slow load for %s", search_url)

    async def _collect_search_links(self, page, request: Request, max_pages: int) -> HtmlResponse:
        url = request.url
        query = request.meta.get("cse_query", "")
        seen: set[str] = set()

        await self._load_cse_search(page, url)
        ctx = await self._find_cse_context(page)
        added = await self._paginate_cse(ctx, page, seen, max_pages, query)

        links = list(seen)
        logger.info("CSE query %r: %d article links (+%d this query)", query, len(links), added)
        body = json.dumps({"links": links, "query": query}, ensure_ascii=False).encode("utf-8")
        return HtmlResponse(url=url, status=200, body=body, encoding="utf-8", request=request)

    async def _collect_all_search_links(self, page, request: Request) -> HtmlResponse:
        queries = request.meta.get("cse_queries") or []
        if not queries:
            queries = [request.meta.get("cse_query", "")]
        max_pages = int(request.meta.get("cse_max_pages", 5))
        seen: set[str] = set()
        per_query: dict[str, int] = {}
        errors: dict[str, str] = {}

        for i, query in enumerate(queries):
            q = str(query)
            search_url = f"{URDUPOINT_SEARCH_BASE}?q={quote(q)}&num=10"
            try:
                logger.info("CSE collect %d/%d: %r", i + 1, len(queries), q)
                await self._load_cse_search(page, search_url)
                ctx = await self._find_cse_context(page)
                per_query[q] = await self._paginate_cse(ctx, page, seen, max_pages, q)
            except Exception as exc:
                errors[q] = f"{type(exc).__name__}: {exc}"
                per_query[q] = 0
                logger.exception("CSE collect failed for query %r", q)

        links = list(seen)
        if not links:
            msg = errors or "no links from any query"
            raise RuntimeError(f"CSE search collected 0 links: {msg}")

        logger.info(
            "All CSE queries done: %d unique links from %d queries (%s)",
            len(links),
            len(queries),
            per_query,
        )
        if errors:
            logger.warning("CSE query errors: %s", errors)

        body = json.dumps(
            {"links": links, "per_query": per_query, "errors": errors},
            ensure_ascii=False,
        ).encode("utf-8")
        return HtmlResponse(
            url=request.url,
            status=200,
            body=body,
            encoding="utf-8",
            request=request,
        )

    async def _fetch_article_page(self, page, url: str, request: Request) -> HtmlResponse:
        article_url = normalize_urdupoint_article_url(url)
        if not article_url:
            raise ValueError(f"Invalid UrduPoint article URL: {url}")

        await page.goto(article_url, wait_until="domcontentloaded", timeout=60000)
        await self._wait_cloudflare(page, short=True)
        html = await page.content()
        return HtmlResponse(
            url=article_url,
            status=200,
            body=html.encode("utf-8"),
            encoding="utf-8",
            request=request,
        )

    async def _fetch_async(self, request: Request, referer_header: str) -> HtmlResponse:
        page = await self._get_page()

        if request.meta.get("playwright_search_collect_all"):
            return await self._collect_all_search_links(page, request)

        if request.meta.get("playwright_search_collect"):
            max_pages = int(request.meta.get("cse_max_pages", 5))
            return await self._collect_search_links(page, request, max_pages)

        if request.meta.get("playwright_fast") or is_valid_urdupoint_article_url(request.url):
            return await self._fetch_article_page(page, request.url, request)

        if request.method.upper() == "POST":
            referer = referer_header or request.meta.get("referer", "")
            if referer and page.url != referer:
                await page.goto(referer, wait_until="domcontentloaded", timeout=60000)
                await self._wait_cloudflare(page)
            form = dict(parse_qsl(request.body.decode("utf-8", errors="replace")))
            result = await page.evaluate(
                """async ({ url, form, referer }) => {
                  const body = new URLSearchParams(form);
                  const resp = await fetch(url, {
                    method: 'POST', body, credentials: 'include',
                    headers: { 'X-Requested-With': 'XMLHttpRequest' },
                    referrer: referer,
                  });
                  return { status: resp.status, text: await resp.text() };
                }""",
                {"url": request.url, "form": form, "referer": referer or page.url},
            )
            return HtmlResponse(
                url=request.url,
                status=result["status"],
                body=result["text"].encode("utf-8"),
                encoding="utf-8",
                request=request,
            )

        await page.goto(request.url, wait_until="domcontentloaded", timeout=60000)
        await self._wait_cloudflare(page, short=True)
        html = await page.content()
        return HtmlResponse(
            url=page.url,
            status=200,
            body=html.encode("utf-8"),
            encoding="utf-8",
            request=request,
        )


class PlaywrightBypassMiddleware:
    def __init__(self, domains: tuple[str, ...], headless: bool, wait_ms: int, fast_wait_ms: int):
        self.domains = domains
        self.headless = headless
        self.wait_ms = wait_ms
        self.fast_wait_ms = fast_wait_ms
        self._worker: _PlaywrightAsyncWorker | None = None

    @classmethod
    def from_crawler(cls, crawler):
        if not crawler.settings.getbool("PLAYWRIGHT_BYPASS_ENABLED", False):
            raise NotConfigured("PLAYWRIGHT_BYPASS_ENABLED is False")
        try:
            from playwright.async_api import async_playwright  # noqa: F401
        except ImportError as exc:
            raise NotConfigured(
                "pip install playwright && playwright install chromium"
            ) from exc

        domains = crawler.settings.getlist("PLAYWRIGHT_BYPASS_DOMAINS") or [
            "urdupoint.com",
            "www.urdupoint.com",
        ]
        mw = cls(
            domains=tuple(domains),
            headless=crawler.settings.getbool("PLAYWRIGHT_HEADLESS", True),
            wait_ms=crawler.settings.getint("PLAYWRIGHT_WAIT_MS", 2500),
            fast_wait_ms=crawler.settings.getint("PLAYWRIGHT_FAST_WAIT_MS", 300),
        )
        from scrapy import signals

        crawler.signals.connect(mw.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(mw.spider_closed, signal=signals.spider_closed)
        return mw

    def spider_opened(self, spider):
        self._worker = _PlaywrightAsyncWorker(self.headless, self.wait_ms, self.fast_wait_ms)
        self._worker.start()
        spider.logger.info("Playwright async worker ready (fast mode)")

    def spider_closed(self, spider):
        if self._worker:
            self._worker.stop()
            self._worker = None

    def _domain_match(self, url: str) -> bool:
        host = urlparse(url).hostname or ""
        return any(host == d or host.endswith("." + d) for d in self.domains)

    def _should_bypass(self, request: Request, spider) -> bool:
        if request.meta.get("dont_playwright"):
            return False
        if not spider.settings.getbool("PLAYWRIGHT_BYPASS_ENABLED", False):
            if not getattr(spider, "playwright_bypass", False):
                return False
        return self._domain_match(request.url)

    def _header_get(self, request: Request, name: str) -> str:
        val = request.headers.get(name) or request.headers.get(name.encode())
        if not val:
            return ""
        raw = val[0] if isinstance(val, list) else val
        return raw.decode() if isinstance(raw, bytes) else str(raw)

    def _do_fetch(self, request: Request) -> HtmlResponse:
        if not self._worker:
            raise RuntimeError("Playwright worker not started")
        return self._worker.fetch(request, self._header_get(request, "Referer"))

    def process_request(self, request, spider):
        if not self._should_bypass(request, spider):
            return None
        if request.meta.get("playwright_fast") or request.meta.get(
            "playwright_search_collect"
        ) or request.meta.get("playwright_search_collect_all"):
            article_url = normalize_urdupoint_article_url(
                request.meta.get("url") or request.url
            )
            if request.meta.get("playwright_fast") and not article_url:
                spider.logger.warning(f"Skip invalid article URL: {request.url}")
                return HtmlResponse(
                    url=request.url,
                    status=404,
                    body=b"",
                    encoding="utf-8",
                    request=request,
                )

        if not request.meta.get("playwright_fast") and not request.meta.get(
            "playwright_search_collect"
        ) and not request.meta.get("playwright_search_collect_all"):
            spider.logger.debug(f"Playwright: {request.method} {request.url}")
        try:
            response = self._do_fetch(request)
            response.flags.append("playwright")
            return response
        except Exception as exc:
            spider.logger.error(
                "Playwright failed: %s — %s: %s",
                request.url,
                type(exc).__name__,
                exc or "(no message)",
                exc_info=exc,
            )
            if request.meta.get("playwright_search_collect_all"):
                body = json.dumps(
                    {"links": [], "per_query": {}, "errors": {"_fatal": str(exc)}},
                    ensure_ascii=False,
                ).encode("utf-8")
                return HtmlResponse(
                    url=request.url,
                    status=200,
                    body=body,
                    encoding="utf-8",
                    request=request,
                )
            return HtmlResponse(
                url=request.url,
                status=502,
                body=b"",
                encoding="utf-8",
                request=request,
            )

    def process_response(self, request, response, spider):
        if response.flags and "playwright" in response.flags:
            return response
        if response.status not in (403, 503) or not self._should_bypass(request, spider):
            return response
        request.meta["playwright_fast"] = True
        try:
            pw_response = self._do_fetch(request)
            pw_response.flags.append("playwright")
            return pw_response
        except Exception as exc:
            spider.logger.error(f"Playwright retry failed: {exc}")
            return response
