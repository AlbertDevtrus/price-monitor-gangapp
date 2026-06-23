# Define here the models for your spider middleware
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/spider-middleware.html

import asyncio
import logging

from scrapy import signals

# useful for handling different item types with a single interface
from itemadapter import ItemAdapter

logger = logging.getLogger(__name__)


class PriceScrapersSpiderMiddleware:
    # Not all methods need to be defined. If a method is not defined,
    # scrapy acts as if the spider middleware does not modify the
    # passed objects.

    @classmethod
    def from_crawler(cls, crawler):
        # This method is used by Scrapy to create your spiders.
        s = cls()
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        return s

    def process_spider_input(self, response, spider):
        # Called for each response that goes through the spider
        # middleware and into the spider.

        # Should return None or raise an exception.
        return None

    def process_spider_output(self, response, result, spider):
        # Called with the results returned from the Spider, after
        # it has processed the response.

        # Must return an iterable of Request, or item objects.
        for i in result:
            yield i

    def process_spider_exception(self, response, exception, spider):
        # Called when a spider or process_spider_input() method
        # (from other spider middleware) raises an exception.

        # Should return either None or an iterable of Request or item objects.
        pass

    async def process_start(self, start):
        # Called with an async iterator over the spider start() method or the
        # maching method of an earlier spider middleware.
        async for item_or_request in start:
            yield item_or_request

    def spider_opened(self, spider):
        spider.logger.info("Spider opened: %s" % spider.name)


class PlaywrightStateMiddleware:
    """Downloader middleware that persists the Playwright browser context
    storage state (cookies + localStorage) after each successful playwright
    response.

    The context is still alive at this point (only the *page* has been
    closed), so calling context.storage_state() is safe.

    On Windows scrapy-playwright routes all Playwright coroutines through a
    dedicated ProactorEventLoop thread (_ThreadedLoopAdapter).  We schedule
    the save coroutine on that loop via run_coroutine_threadsafe so we don't
    stall the Scrapy/Twisted reactor.

    Enable in settings.py:
        DOWNLOADER_MIDDLEWARES = {
            "price_scrapers.middlewares.PlaywrightStateMiddleware": 900,
        }
    """

    # Per-instance set so we only save once per (context_name, path) per run.
    def __init__(self):
        self._saved: set = set()

    @classmethod
    def from_crawler(cls, crawler):
        return cls()

    def process_response(self, request, response, spider):
        if not request.meta.get("playwright"):
            return response

        context_name = request.meta.get("playwright_context", "default")
        state_path = getattr(spider, "playwright_state_path", None)
        if state_path is None:
            return response

        # Only save once per context per run to avoid hammering disk.
        key = (context_name, state_path)
        if key in self._saved:
            return response

        try:
            handler = (
                spider.crawler.engine.downloader.handlers._handlers.get(
                    "https"
                )
            )
            if handler is None:
                return response

            ctx_wrapper = getattr(handler, "context_wrappers", {}).get(
                context_name
            )
            if ctx_wrapper is None:
                return response

            from scrapy_playwright._utils import _ThreadedLoopAdapter  # noqa: PLC0415

            pw_loop: asyncio.AbstractEventLoop = _ThreadedLoopAdapter._loop
            future = asyncio.run_coroutine_threadsafe(
                ctx_wrapper.context.storage_state(path=state_path),
                pw_loop,
            )
            future.result(timeout=15)
            self._saved.add(key)
            logger.info(
                "Playwright context '%s' state saved to %s",
                context_name,
                state_path,
            )
        except AttributeError:
            # _ThreadedLoopAdapter._loop not available (non-Windows path).
            pass
        except Exception as exc:  # noqa: BLE001
            logger.debug("Could not save Playwright state: %s", exc)

        return response


class PriceScrapersDownloaderMiddleware:
    # Not all methods need to be defined. If a method is not defined,
    # scrapy acts as if the downloader middleware does not modify the
    # passed objects.

    @classmethod
    def from_crawler(cls, crawler):
        # This method is used by Scrapy to create your spiders.
        s = cls()
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        return s

    def process_request(self, request, spider):
        # Called for each request that goes through the downloader
        # middleware.

        # Must either:
        # - return None: continue processing this request
        # - or return a Response object
        # - or return a Request object
        # - or raise IgnoreRequest: process_exception() methods of
        #   installed downloader middleware will be called
        return None

    def process_response(self, request, response, spider):
        # Called with the response returned from the downloader.

        # Must either;
        # - return a Response object
        # - return a Request object
        # - or raise IgnoreRequest
        return response

    def process_exception(self, request, exception, spider):
        # Called when a download handler or a process_request()
        # (from other downloader middleware) raises an exception.

        # Must either:
        # - return None: continue processing this exception
        # - return a Response object: stops process_exception() chain
        # - return a Request object: stops process_exception() chain
        pass

    def spider_opened(self, spider):
        spider.logger.info("Spider opened: %s" % spider.name)
