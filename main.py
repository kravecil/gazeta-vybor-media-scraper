import argparse
import asyncio

DEFAULT_DIR = "downloaded_images"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download images from a list of URLs.")
    parser.add_argument("url", nargs=None, help="List of URLs to download images from.")
    parser.add_argument(
        "--dir", default=DEFAULT_DIR, help="Directory to save downloaded images."
    )
    return parser.parse_args()


async def main():
    args = parse_args()

    print(args)  # TODO: Implement the download logic here


if __name__ == "__main__":
    asyncio.run(main())
