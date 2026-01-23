"""Парсинг DNS-запросов из вывода tcpdump."""

import re
import asyncio
from typing import AsyncIterator


# Regex для извлечения домена из tcpdump DNS query
# Формат: "12345+ A? example.com. (30)" или "AAAA? example.com."
DNS_QUERY_RE = re.compile(r'(?:A|AAAA)\?\s+(\S+?)\.\s')


async def stream_dns_domains() -> AsyncIterator[str]:
    """Запускает tcpdump и стримит DNS-домены по мере поступления."""
    proc = await asyncio.create_subprocess_exec(
        '/usr/sbin/tcpdump', '-i', 'any', '-l', 'port', '53',
        '--immediate-mode', '-n',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )

    stdout = proc.stdout
    if stdout is None:
        return

    try:
        async for line in stdout:
            decoded = line.decode('utf-8', errors='ignore')
            match = DNS_QUERY_RE.search(decoded)
            if match:
                domain = match.group(1).lower()
                yield domain
    finally:
        proc.terminate()
        await proc.wait()


def parse_domain_from_line(line: str) -> str | None:
    """Извлекает домен из одной строки вывода tcpdump."""
    match = DNS_QUERY_RE.search(line)
    if match:
        return match.group(1).lower()
    return None
