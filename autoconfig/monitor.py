#!/usr/bin/env python3
"""
Shadowrocket AutoConfig Monitor + HTTP API.

1. Мониторит DNS-запросы через tcpdump, хранит историю
2. HTTP API на localhost:7890 для браузерного расширения
3. При запросе — собирает связанные домены, обновляет конфиг
"""

import asyncio
import sys
import os
import time
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import DIRECT_TLDS, SYSTEM_DOMAINS, IGNORED_SUFFIXES
from domain_utils import get_base_domain
from dns_parser import stream_dns_domains
from config_updater import (
    load_config_domains, add_domain_to_config, git_push,
)

# Настройки
API_PORT = 7890
DNS_HISTORY_TTL = 60  # секунд — хранить DNS-историю


class DomainTracker:
    """Хранит историю DNS-запросов."""

    def __init__(self):
        self.history: dict[str, float] = {}  # domain -> last_seen timestamp
        self.config_domains: set[str] = set()
        self._reload_config()

    def _reload_config(self):
        self.config_domains = load_config_domains()
        print(f"[config] Loaded {len(self.config_domains)} domains from config")

    def record(self, domain: str):
        """Записывает DNS-запрос в историю."""
        self.history[domain] = time.time()

    def cleanup(self):
        """Удаляет старые записи из истории."""
        now = time.time()
        self.history = {
            d: t for d, t in self.history.items()
            if now - t < DNS_HISTORY_TTL
        }

    def is_ignorable(self, domain: str) -> bool:
        """Проверяет, нужно ли игнорировать домен."""
        for suffix in IGNORED_SUFFIXES:
            if domain.endswith(suffix):
                return True
        for sys_domain in SYSTEM_DOMAINS:
            if domain == sys_domain or domain.endswith('.' + sys_domain):
                return True
        return False

    def get_related_domains(self, base_domain: str) -> list[str]:
        """
        Собирает все домены из DNS-истории, связанные с сайтом.
        Возвращает список base-доменов для добавления в конфиг.
        """
        now = time.time()
        related = set()

        for domain, timestamp in self.history.items():
            if now - timestamp > DNS_HISTORY_TTL:
                continue
            if self.is_ignorable(domain):
                continue

            base = get_base_domain(domain)

            # Пропускаем российские TLD
            skip = False
            for tld in DIRECT_TLDS:
                if base.endswith(tld):
                    skip = True
                    break
            if skip:
                continue

            # Пропускаем уже в конфиге
            if base in self.config_domains:
                continue

            related.add(base)

        return sorted(related)

    def add_domains(self, domains: list[str]):
        """Добавляет домены в конфиг и обновляет кеш."""
        for domain in domains:
            add_domain_to_config(domain)
            self.config_domains.add(domain)
            print(f"[added] {domain}")


# Глобальный tracker
tracker = DomainTracker()


class APIHandler(BaseHTTPRequestHandler):
    """HTTP API для браузерного расширения."""

    def do_OPTIONS(self):
        """CORS preflight."""
        self.send_response(200)
        self._cors_headers()
        self.end_headers()

    def do_POST(self):
        if self.path == '/add':
            self._handle_add()
        else:
            self.send_error(404)

    def do_GET(self):
        if self.path == '/status':
            self._handle_status()
        elif self.path.startswith('/domains'):
            self._handle_domains()
        else:
            self.send_error(404)

    def _handle_add(self):
        """Добавляет домены текущего сайта в конфиг."""
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8')

        try:
            data = json.loads(body)
            url = data.get('url', '')
        except json.JSONDecodeError:
            self.send_error(400, 'Invalid JSON')
            return

        parsed = urlparse(url)
        site_domain = parsed.hostname
        if not site_domain:
            self._json_response(400, {'error': 'No domain in URL'})
            return

        site_base = get_base_domain(site_domain)

        # Собираем все связанные домены из DNS-истории
        related = tracker.get_related_domains(site_base)

        # Добавляем и сам домен сайта если его нет
        if site_base not in tracker.config_domains:
            if site_base not in related:
                related.insert(0, site_base)

        if not related:
            self._json_response(200, {
                'message': 'Все домены уже в конфиге',
                'domains': [],
            })
            return

        # Добавляем в конфиг
        tracker.add_domains(related)

        # Git push и VPN restart в фоне
        asyncio.run_coroutine_threadsafe(
            _push_and_restart(related),
            _loop,
        )

        self._json_response(200, {
            'message': f'Добавлено {len(related)} доменов',
            'domains': related,
        })

    def _handle_status(self):
        """Статус сервиса."""
        self._json_response(200, {
            'status': 'running',
            'history_size': len(tracker.history),
            'config_domains': len(tracker.config_domains),
        })

    def _handle_domains(self):
        """Показывает текущую DNS-историю."""
        tracker.cleanup()
        now = time.time()
        domains = [
            {'domain': d, 'ago': round(now - t, 1)}
            for d, t in sorted(tracker.history.items(), key=lambda x: -x[1])
        ]
        self._json_response(200, {'domains': domains})

    def _json_response(self, code: int, data: dict):
        self.send_response(code)
        self._cors_headers()
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

    def _cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def log_message(self, format, *args):
        print(f"[api] {args[0]}")


async def _push_and_restart(domains: list[str]):
    """Git push + VPN restart параллельно."""
    push_task = asyncio.create_task(git_push(', '.join(domains)))
    vpn_task = asyncio.create_task(_restart_vpn())

    await vpn_task
    pushed = await push_task
    if pushed:
        print(f"[pushed] Изменения отправлены в GitHub")
    else:
        print(f"[warn] Не удалось отправить в GitHub")


async def _restart_vpn():
    """Переподключает VPN."""
    print("[vpn] Переподключаю VPN...")
    proc = await asyncio.create_subprocess_exec(
        '/usr/sbin/scutil', '--nc', 'stop', 'Shadowrocket',
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.wait()
    await asyncio.sleep(1)
    proc = await asyncio.create_subprocess_exec(
        '/usr/sbin/scutil', '--nc', 'start', 'Shadowrocket',
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.wait()
    print("[vpn] VPN переподключен")


async def dns_monitor():
    """Мониторинг DNS-запросов."""
    print("[dns] Мониторинг DNS-запросов...")
    cleanup_counter = 0

    async for domain in stream_dns_domains():
        tracker.record(domain)
        cleanup_counter += 1
        if cleanup_counter >= 100:
            tracker.cleanup()
            cleanup_counter = 0


def start_api_server():
    """Запускает HTTP API в отдельном потоке."""
    server = HTTPServer(('127.0.0.1', API_PORT), APIHandler)
    print(f"[api] HTTP API слушает на http://127.0.0.1:{API_PORT}")
    server.serve_forever()


_loop: asyncio.AbstractEventLoop


async def main():
    global _loop
    _loop = asyncio.get_event_loop()

    # API-сервер в отдельном потоке
    api_thread = Thread(target=start_api_server, daemon=True)
    api_thread.start()

    # DNS-мониторинг в основном цикле
    print("[start] Shadowrocket AutoConfig Monitor запущен")
    await dns_monitor()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[stop] Остановлен")
