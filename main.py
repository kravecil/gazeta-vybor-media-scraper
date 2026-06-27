import asyncio
import os
from urllib.parse import urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

# Константы
URL = "https://gazetavibor.ru/news/novosti/2026-05-26/v-22-shkole-salavata-prozvenel-posledniy-zvonok-4700197"
DOWNLOAD_DIR = "downloaded_images"
CONCURRENT_LIMIT = 10


async def download_image(session, img_url, filename):
    """Асинхронно скачивает одно изображение."""
    try:
        async with session.get(img_url) as response:
            if response.status == 200:
                data = await response.read()
                file_path = os.path.join(DOWNLOAD_DIR, filename)
                with open(file_path, "wb") as f:
                    f.write(data)
                print(f"Скачано: {filename}")
            else:
                print(f"Ошибка {response.status} при загрузке: {img_url}")
    except Exception as e:
        print(f"Исключение при скачивании {img_url}: {e}")


async def main():
    # Создаём директорию, если её нет
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)

    html_content = None

    # Запускаем браузер через Playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(
            extra_http_headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
        )

        try:
            await page.goto(URL, wait_until="domcontentloaded")
            print("Страница загружена")

            # Ждём появления контейнера карусели
            await page.wait_for_selector("div.swiper-wrapper", timeout=15000)
            print("Карусель найдена")

            # Прокручиваем карусель, чтобы загрузить все изображения
            prev_count = 0
            max_attempts = 50

            for attempt in range(max_attempts):
                slide_count = await page.evaluate("""() => {
                    return document.querySelectorAll('div.swiper-wrapper div.swiper-slide img[src]').length;
                }""")

                print(f"[Попытка {attempt + 1}] Найдено изображений: {slide_count}")

                if slide_count == prev_count:
                    print(
                        "Изображения перестали появляться — считаем, что все загружены."
                    )
                    break

                prev_count = slide_count

                # Пытаемся нажать кнопку "вперёд"
                try:
                    await page.click(".swiper-button-next", timeout=3000)
                except Exception:
                    # Если кнопки нет — прокручиваем вручную
                    await page.evaluate(
                        "document.querySelector('.swiper-wrapper').scrollBy(300, 0)"
                    )

                await asyncio.sleep(0.7)  # Ждём загрузки изображений

            # ✅ Получаем HTML ДО закрытия браузера
            html_content = await page.content()

        except Exception as e:
            print(f"Ошибка при загрузке страницы: {e}")
        finally:
            await browser.close()  # Браузер закрывается здесь

    # ✅ Теперь парсим HTML (браузер уже закрыт, но данные сохранены)
    soup = BeautifulSoup(html_content, "html.parser")

    # Находим контейнер карусели
    swiper_wrapper = soup.find("div", class_="swiper-wrapper")
    if not swiper_wrapper:
        print("Контейнер карусели с классом 'swiper-wrapper' не найден.")
        return

    # Находим все слайды
    slides = swiper_wrapper.find_all("div", class_="swiper-slide")
    if not slides:
        print("Слайды с классом 'swiper-slide' не найдены.")
        return

    # Собираем URL изображений
    image_urls = []
    for i, slide in enumerate(slides):
        img_tag = slide.find("img")
        if img_tag:
            # Учитываем lazy loading: проверяем src, data-src, data-lazy
            img_url_attr = (
                img_tag.get("src")
                or img_tag.get("data-src")
                or img_tag.get("data-lazy")
            )
            if img_url_attr:
                img_url = urljoin(URL, img_url_attr)
                filename = os.path.basename(urlparse(img_url).path)
                if not filename or "." not in filename:
                    filename = f"image_{i + 1}.jpg"
                image_urls.append((img_url, filename))

    if not image_urls:
        print("Изображения не найдены.")
        return

    # Асинхронная загрузка изображений
    connector = aiohttp.TCPConnector(limit=CONCURRENT_LIMIT)
    timeout = aiohttp.ClientTimeout(total=30)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        tasks = [download_image(session, url, filename) for url, filename in image_urls]
        await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
