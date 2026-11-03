"""One polite HTTP session for every source, plus a disk-cached file downloader."""
from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

from ..config import FILES_DIR, MAX_PDF_MB

log = logging.getLogger("finn.http")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")

_session = requests.Session()
_session.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})


class FetchError(RuntimeError):
    pass


def _referer_for(url: str) -> dict[str, str]:
    host = urlparse(url).netloc
    if "bseindia.com" in host:
        return {"Referer": "https://www.bseindia.com/", "Origin": "https://www.bseindia.com"}
    if "screener.in" in host:
        return {"Referer": "https://www.screener.in/"}
    return {}


def _public_host(url: str) -> None:
    """Refuse URLs that resolve to private, loopback or link-local addresses (server-side request forgery)."""
    import ipaddress
    import socket
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise FetchError(f"Refusing non-http URL: {url}")
    try:
        infos = socket.getaddrinfo(p.hostname, None)
    except socket.gaierror as e:
        raise FetchError(f"DNS failed for {p.hostname}: {e}") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise FetchError(f"Refusing internal address for {p.hostname}")


def _get_checked(url: str, *, timeout: int, headers: dict, **kw) -> requests.Response:
    for _ in range(5):
        _public_host(url)
        r = _session.get(url, timeout=timeout, headers=headers, allow_redirects=False, **kw)
        if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("Location"):
            from urllib.parse import urljoin
            url = urljoin(url, r.headers["Location"])
            continue
        return r
    raise FetchError(f"Too many redirects: {url}")


def get(url: str, *, timeout: int = 30, retries: int = 3, **kw) -> requests.Response:
    headers = {**_referer_for(url), **kw.pop("headers", {})}
    last: Exception | None = None
    for attempt in range(retries):
        try:
            r = _get_checked(url, timeout=timeout, headers=headers, **kw)
            if r.status_code in (429, 500, 502, 503, 504):
                raise FetchError(f"HTTP {r.status_code}")
            if r.status_code >= 400:
                raise FetchError(f"HTTP {r.status_code} for {url}")
            return r
        except (requests.RequestException, FetchError) as e:
            last = e
            if isinstance(e, FetchError) and (("HTTP 4" in str(e) and "429" not in str(e)) or "Refusing" in str(e)):
                break  # a 403/404 or a refused target will not fix itself
            time.sleep(1.5 * (attempt + 1))
    raise FetchError(f"GET failed for {url}: {last}")


def cached_path(url: str, suffix: str = ".pdf") -> Path:
    return FILES_DIR / (hashlib.sha1(url.encode()).hexdigest()[:20] + suffix)


def download(url: str, *, suffix: str = ".pdf", max_mb: int = MAX_PDF_MB) -> Path:
    """Download once, keep forever. Raises FetchError on failure or oversize files."""
    path = cached_path(url, suffix)
    if path.exists() and path.stat().st_size > 0:
        return path
    r = get(url, timeout=90, stream=True)
    limit = max_mb * 1024 * 1024
    size = 0
    tmp = path.with_suffix(path.suffix + ".part")
    with open(tmp, "wb") as f:
        for chunk in r.iter_content(65536):
            size += len(chunk)
            if size > limit:
                f.close()
                tmp.unlink(missing_ok=True)
                raise FetchError(f"File larger than {max_mb} MB: {url}")
            f.write(chunk)
    head = tmp.read_bytes()[:5]
    if suffix == ".pdf" and head != b"%PDF-":
        tmp.unlink(missing_ok=True)
        raise FetchError(f"Not a PDF (blocked or moved?): {url}")
    tmp.rename(path)
    return path
