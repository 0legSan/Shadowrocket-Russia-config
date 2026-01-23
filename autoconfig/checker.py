"""Проверка доступности доменов через TCP connect + HTTP check."""

import asyncio
import socket
import ssl
import urllib.request
import urllib.error
from config import CHECK_TIMEOUT, CHECK_PORT, MAX_CONCURRENT_CHECKS


_semaphore = asyncio.Semaphore(MAX_CONCURRENT_CHECKS)

# Паттерны в теле ответа, указывающие на геоблокировку
BLOCK_INDICATORS = [
    # Cloudflare / WAF
    'you have been blocked',
    'access denied',
    'blocked by',
    # Геоблокировка
    'not available in your country',
    'not available in your region',
    'geo restriction',
    'this content is not available',
    'unavailable in your location',
    # Санкционные блокировки
    'sanctioned countries',
    'restricted countries',
    'access from your country',
    'your region is restricted',
    'service is not available in your',
    'restricted in your country',
    'not supported in your country',
    'blocked in your region',
    'embargo',
]


def _http_check_blocked(domain: str) -> bool:
    """
    HTTP-проверка: запрос к домену и анализ ответа.
    Возвращает True если сайт блокирует по геолокации.
    """
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(
        f'https://{domain}/',
        method='GET',
        headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'},
    )

    try:
        with urllib.request.urlopen(req, timeout=CHECK_TIMEOUT, context=ctx) as resp:
            if resp.status in (403, 451):
                body = resp.read(4096).decode('utf-8', errors='ignore').lower()
                return any(ind in body for ind in BLOCK_INDICATORS)
            return False  # 200/301/302 — доступен
    except urllib.error.HTTPError as e:
        if e.code == 451:
            return True  # Unavailable For Legal Reasons — санкции
        if e.code == 403:
            body = e.read(4096).decode('utf-8', errors='ignore').lower()
            return any(ind in body for ind in BLOCK_INDICATORS)
        return False  # Другие HTTP ошибки — не геоблокировка
    except (urllib.error.URLError, OSError, socket.timeout):
        return False  # Сетевая ошибка — обработана в TCP-проверке


async def is_domain_blocked(domain: str) -> bool:
    """
    Проверяет, заблокирован ли домен.

    Этап 1: TCP connect к :443
    - Timeout → заблокирован
    - RST → заблокирован

    Этап 2: HTTP GET (если TCP ok)
    - 403 + "blocked" в теле → заблокирован (Cloudflare/гео)
    """
    async with _semaphore:
        # Этап 1: TCP connect
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(domain, CHECK_PORT),
                timeout=CHECK_TIMEOUT,
            )
            writer.close()
            await writer.wait_closed()
        except asyncio.TimeoutError:
            return True  # Timeout → заблокирован
        except ConnectionResetError:
            return True  # RST → заблокирован DPI
        except (socket.gaierror, ConnectionRefusedError, OSError):
            return False  # DNS error / другое — не блокировка

        # Этап 2: HTTP-проверка на геоблокировку
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _http_check_blocked, domain)
