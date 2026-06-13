#!/bin/env python

"""
    Module that search sounds in www.myinstants.com
    Author: Luiz Francisco Rodrigues da Silva <luizfrdasilva@gmail.com>
"""

import asyncio
import os
import sys
from urllib.parse import urljoin

import aiohttp
import aiofiles
import parsel
from aiohttp import FormData
from user_agent import generate_user_agent

SEARCH_URL = "https://www.myinstants.com/en/search/?name={}"
MEDIA_URL = "https://www.myinstants.com{}"
UPLOAD_URL = "https://www.myinstants.com/en/new/"
LOGIN_URL = "https://www.myinstants.com/accounts/login/"

DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=15)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class MyInstantsApiException(Exception):
    """General exception for myinstants api"""


class HTTPErrorException(MyInstantsApiException):
    """HTTP error exception for myinstants api"""


class NameAlreadyExistsException(MyInstantsApiException):
    """Exception thrown when an instant name already exists"""


class FileSizeException(MyInstantsApiException):
    """Exception thrown when the instant file size exceeds the limit"""


class LoginErrorException(MyInstantsApiException):
    """Exception thrown when login fails"""


class InvalidPageErrorException(MyInstantsApiException):
    """Exception thrown when an invalid page is downloaded"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_headers(extra: dict | None = None) -> dict:
    headers = {"User-Agent": generate_user_agent()}
    if extra:
        headers.update(extra)
    return headers


def _parse_csrf(html: str) -> str:
    token = parsel.Selector(html).css(
        "input[name=csrfmiddlewaretoken]::attr(value)"
    ).get()
    if not token:
        raise InvalidPageErrorException("CSRF token not found in page")
    return token


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

async def search_instants(query: str | list[str]) -> list[dict]:
    """Search instants by name.

    Args:
        query: Search string or list of words.

    Returns:
        List of dicts with ``text`` and ``url`` keys.

    Raises:
        HTTPErrorException: On non-200 responses.
    """
    query_string = (
        "+".join(query) if isinstance(query, list) else query.replace(" ", "+")
    )

    async with aiohttp.ClientSession(timeout=DEFAULT_TIMEOUT) as session:
        async with session.get(
            SEARCH_URL.format(query_string), headers=_build_headers()
        ) as response:
            if response.status != 200:
                raise HTTPErrorException(
                    f"Search failed with HTTP {response.status}"
                )
            data = await response.text()

    sel = parsel.Selector(data)
    names = sel.css(".instant .instant-link::text").getall()
    links = sel.css(
        ".instant .small-button::attr(onclick),"
        ".instant .small-button::attr(onmousedown)"
    ).re(r"play\('(.*?)',")

    return [
        {"text": text, "url": MEDIA_URL.format(url)}
        for text, url in zip(names, links)
    ]


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

async def upload_instant(name: str, filepath: str) -> str:
    """Upload a sound file to MyInstants (async).

    Args:
        name:     Display name for the instant.
        filepath: Local path to the MP3 file.

    Returns:
        URL of the uploaded instant.

    Raises:
        LoginErrorException:      If credentials are wrong or login fails.
        NameAlreadyExistsException: If the name is already taken.
        FileSizeException:        If the file exceeds the 300 KB limit.
        HTTPErrorException:       On unexpected HTTP errors.
        InvalidPageErrorException: If a CSRF token cannot be found.
    """
    username = os.environ["MYINSTANTS_USERNAME"]
    password = os.environ["MYINSTANTS_PASSWORD"]

    async with aiohttp.ClientSession(timeout=DEFAULT_TIMEOUT) as session:
        # Step 1 — fetch login page for CSRF token
        async with session.get(LOGIN_URL, headers=_build_headers()) as resp:
            resp.raise_for_status()
            token = _parse_csrf(await resp.text())

        # Step 2 — log in
        login_data = aiohttp.FormData()
        login_data.add_field("csrfmiddlewaretoken", token)
        login_data.add_field("login", username)
        login_data.add_field("password", password)
        login_data.add_field("next", "/en/new/")

        async with session.post(
            LOGIN_URL,
            data=login_data,
            headers=_build_headers({"Referer": LOGIN_URL}),
        ) as resp:
            if resp.status != 200:
                raise LoginErrorException(f"Login returned HTTP {resp.status}")
            login_html = await resp.text()

        # Confirm we got the upload page after redirect
        upload_token = _parse_csrf(login_html)

        # Step 3 — upload sound
        async with aiofiles.open(filepath, "rb") as f:
            file_bytes = await f.read()

        filename = os.path.basename(filepath)
        upload_data = FormData()
        upload_data.add_field("csrfmiddlewaretoken", upload_token)
        upload_data.add_field("name", name)
        upload_data.add_field(
            "sound",
            file_bytes,
            filename=filename,
            content_type="audio/mpeg",
        )
        upload_data.add_field("image", b"", filename="", content_type="")
        upload_data.add_field("color", "00FF00")
        upload_data.add_field("category", "")
        upload_data.add_field("description", "")
        upload_data.add_field("tags", "")
        upload_data.add_field("accept_terms", "on")

        async with session.post(
            UPLOAD_URL,
            data=upload_data,
            headers=_build_headers({"Referer": UPLOAD_URL}),
        ) as resp:
            if resp.status != 200:
                raise HTTPErrorException(f"Upload returned HTTP {resp.status}")
            upload_html = await resp.text()
            final_url = str(resp.url)

    sel = parsel.Selector(upload_html)
    errors = "\n".join(sel.css("ul.errorlist").getall())
    if "instant with this name already exists." in errors:
        raise NameAlreadyExistsException(name)
    if "please keep filesize under 300.0 kb" in errors:
        raise FileSizeException(filepath)

    link = sel.xpath(
        "//a[contains(@class, 'instant-link') and text()=$name]/@href", name=name
    ).get()

    return urljoin(final_url, link) if link else final_url


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

async def _main():
    if not sys.argv[1:]:
        print("Usage: myinstants.py <search terms>")
        sys.exit(1)
    try:
        results = await search_instants(sys.argv[1:])
        for item in results:
            print(f"{item['text']}\n  {item['url']}\n")
    except HTTPErrorException as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except TimeoutError:
        print("Request timed out.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(_main())
