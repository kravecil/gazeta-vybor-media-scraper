import argparse
import asyncio
import os

DEFAULT_DIR = "downloaded_images"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download images from a list of URLs.")
    parser.add_argument("url", nargs=None, help="URL to download images from.")
    parser.add_argument(
        "--dir", default=DEFAULT_DIR, help="Directory to save downloaded images."
    )
    return parser.parse_args()


def ensure_dir_exists(dir: str) -> None:
    if not os.path.exists(dir):
        os.makedirs(dir)


async def main():
    args = parse_args()

    ensure_dir_exists(args.dir)


if __name__ == "__main__":
    asyncio.run(main())
