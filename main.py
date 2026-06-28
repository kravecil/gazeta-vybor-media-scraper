import argparse
import asyncio
import base64
import logging
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import ElementHandle, Page, async_playwright

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)


logger = logging.getLogger(__name__)


DEFAULT_DIR = "downloaded_images"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download images from a list of URLs.")
    parser.add_argument("url", nargs=None, help="URL to download images from.")
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


async def fetch_images(
    page: Page, urls: list[str], dir: str, concurrent_limit: int = 10
) -> int:
    semaphore = asyncio.Semaphore(concurrent_limit)

    async def _limited_fetch(url: str) -> bool:
        async with semaphore:
            return await download_image(page, url, dir)

    tasks = [_limited_fetch(url) for url in urls]
    results = await asyncio.gather(*tasks)

    return sum(results)


async def download_image(page: Page, url: str, dir: str) -> bool:
    try:
        result = await page.evaluate(
            """
            async (url) => {
                try {
                    const response = await fetch(url, { credentials: 'include' });
                    if (!response.ok) return null;

                    const blob = await response.blob();
                    const arrayBuffer = await blob.arrayBuffer();
                    const bytes = new Uint8Array(arrayBuffer);

                    // Convert to base64 for transfer to Python
                    let binary = '';
                    for (let i = 0; i < bytes.byteLength; i++) {
                        binary += String.fromCharCode(bytes[i]);
                    }
                    return btoa(binary);
                } catch (e) {
                    console.error('Fetch error:', url, e);
                    return null;
                }
            }
        """,
            url,
        )

        if not result:
            logger.warning(f"⚠️ Failed or blocked fetch for {url}")
            return False

        image_data = base64.b64decode(result)

        path = urlparse(url).path
        original_name = Path(path).name or "img"

        filepath = os.path.join(dir, original_name)

        with open(filepath, "wb") as f:
            f.write(image_data)

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
            src_handle = await locator.get_property("src")

            if not src_handle:
                continue
            src = await src_handle.json_value()
            if not src:
                continue

            image_urls.append(src)

        logger.info(f"Found {len(image_urls)} images.")

        logger.info("Fetching images...")
        success_fetch_count = await fetch_images(page, image_urls, args.dir)

        logger.info(f"Successful fetched {success_fetch_count} images.")

        await browser.close()

    logger.info("Done.")


if __name__ == "__main__":
    asyncio.run(main())
