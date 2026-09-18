"""Midway-authenticated Builder adapter for internal website reads."""
from __future__ import annotations

import os

import httpx

from ..models import PageReadFailure, PageReadSuccess

_COOKIE_PATH = os.path.expanduser("~/.midway/cookie")


def _read_midway_cookie() -> str:
    cookie = os.environ.get("MIDWAY_COOKIE")
    if cookie:
        return cookie
    path = os.environ.get("MIDWAY_COOKIE_PATH", _COOKIE_PATH)
    try:
        with open(path) as file:
            return file.read().strip()
    except FileNotFoundError:
        raise RuntimeError(f"Midway cookie not found at {path}. Run 'mwinit'.") from None


def _build_cookie_jar(cookie_str: str) -> httpx.Cookies:
    jar = httpx.Cookies()
    for line in cookie_str.splitlines():
        line = line.strip()
        if line.startswith("#HttpOnly_"):
            line = line[len("#HttpOnly_"):]
        elif not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 7:
            domain, _flag, path, _secure, _expiry, name, value = parts[:7]
            jar.set(name, value, domain=domain, path=path)
    return jar


class MidwayBuilderAdapter:
    """BuilderPort via direct HTTP with Midway authentication."""

    def __init__(self) -> None:
        self._client: httpx.Client | None = None

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                headers={"User-Agent": "builder-brick/1.0"},
                cookies=_build_cookie_jar(_read_midway_cookie()),
                follow_redirects=True, timeout=30.0,
            )
        return self._client

    async def read_url(self, url: str) -> PageReadSuccess | PageReadFailure:
        """Read a page while retaining safe HTTP outcome metadata."""
        try:
            response = self._get_client().get(url)
            response.raise_for_status()
            return PageReadSuccess(url=url, content=response.text[:50000], status=response.status_code)
        except httpx.HTTPStatusError as error:
            return PageReadFailure(url=url, status=error.response.status_code, error_code="http_error")
        except Exception:
            return PageReadFailure(url=url, error_code="request_failed")

    async def search_code(self, query: str, search_type: str = "code", page: int = 1):
        return await self.read_url(f"https://code.amazon.com/search?q={query}&type={search_type}&p={page}")

    async def get_pipeline_details(self, pipeline_name: str):
        return await self.read_url(f"https://pipelines.amazon.com/pipelines/{pipeline_name}")

    async def read_package_file(self, package_name: str, file_path: str, branch: str = "mainline"):
        return await self.read_url(
            f"https://code.amazon.com/packages/{package_name}/blobs/{branch}/--/{file_path}"
        )

    async def list_package_files(self, package_name: str, path: str = "", branch: str = "mainline"):
        url = f"https://code.amazon.com/packages/{package_name}/trees/{branch}"
        return await self.read_url(f"{url}/--/{path}" if path else url)

    def health_check(self) -> dict[str, object]:
        try:
            _read_midway_cookie()
            return {"healthy": True, "adapter": "midway"}
        except Exception:
            return {"healthy": False, "adapter": "midway"}
