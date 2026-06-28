import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import aiohttp
from playwright.async_api import ElementHandle, async_playwright

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)


logger = logging.getLogger(__name__)


DEFAULT_DIR = "downloaded_images"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download images from a list of URLs.")
    parser.add_argument(
        "url",
        # TODO @me remove constant url
        default="https://gazetavibor.ru/news/novosti/2026-06-26/v-salavate-otmetili-vypusknoy-bally-bal-2026-4732758",
        nargs=None,
        help="URL to download images from.",
    )
    parser.add_argument(
        "--dir", default=DEFAULT_DIR, help="Directory to save downloaded images."
    )
    parser.add_argument(
        "--concurrent", default=10, type=int, help="Number of concurrent downloads."
    )
    return parser.parse_args()


def ensure_dir_exists(dir: str) -> None:
    if not os.path.exists(dir):
        os.makedirs(dir)


async def scroll_to_bottom(
    container: ElementHandle,
    scroll_delay_sec: float = 1.0,
    max_attempts: int = 10,
) -> None:
    previous_height = await container.evaluate("el => el.scrollHeight")

    for _ in range(max_attempts):
        await container.evaluate("el => el.scrollTop = el.scrollHeight")
        await asyncio.sleep(scroll_delay_sec)

        new_height = await container.evaluate("el => el.scrollHeight")
        if new_height == previous_height:
            break

        previous_height = new_height
    else:
        logger.warning(
            f"⚠️ Scroll reached max attempts ({max_attempts}) — container may still have content."
        )


async def fetch_images(urls: list[str], dir: str, concurrent_limit: int = 10) -> int:
    connector = aiohttp.TCPConnector(limit=concurrent_limit)
    timeout = aiohttp.ClientTimeout(total=30)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        tasks = [download_image(session, url, dir) for url in urls]
        results = await asyncio.gather(*tasks)

        return sum(results)


async def download_image(session: aiohttp.ClientSession, url: str, dir: str) -> bool:
    try:
        async with session.get(url) as response:
            path = urlparse(url).path
            original_name = Path(path).name or "img"

            filepath = os.path.join(dir, original_name)

            with open(filepath, "wb") as f:
                f.write(await response.read())

            return True
    except Exception as e:
        logger.error(f"Failed to download image from {url}: {e}")
        return False


async def main():
    logger.info("Starting...")

    args = parse_args()

    logger.info("Ensuring download dirrectory exist...")
    ensure_dir_exists(args.dir)

    async with async_playwright() as p:
        logger.info("Launching browser...")
        browser = await p.chromium.launch(
            headless=True,
        )

        logger.info(f"Navigating to URL {args.url}...")
        page = await browser.new_page(
            extra_http_headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
        )
        await page.goto(args.url, wait_until="domcontentloaded")

        logger.info("Waiting for page to load...")
        await page.wait_for_load_state("load")
        await page.wait_for_selector("div.container.mt-4", timeout=10_000)

        logger.info("Scrolling to bottom...")
        container = await page.query_selector("div.container.mt-4")
        if not container:
            raise RuntimeError("❌ Could not find div.container.mt-4")
        await scroll_to_bottom(container)

        logger.info("Getting image locators from article container...")
        images_locator = await container.query_selector_all(
            "div.swiper-container-thumbs div.swiper-slide img"
        )

        image_urls: list[str] = []
        for locator in images_locator:
            src = await locator.get_attribute("src")

            if src is None:
                continue

            image_urls.append(src)

        await browser.close()

    image_urls = image_urls[:5]  # TODO @me: remove, for testing only

    logger.info(f"Found {len(image_urls)} images.")

    logger.info("Fetching images...")
    success_fetch_count = await fetch_images(image_urls, args.dir, args.concurrent)

    logger.info(f"Successful fetched {success_fetch_count} images.")

    logger.info("Done.")


if __name__ == "__main__":
    asyncio.run(main())
