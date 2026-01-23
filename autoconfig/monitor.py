#!/usr/bin/env python3
"""
Shadowrocket AutoConfig Monitor.

Фоновый демон, который:
1. Мониторит DNS-запросы через tcpdump
2. Определяет заблокированные домены (TCP timeout)
3. Предлагает добавить их в конфиг Shadowrocket
4. Пушит изменения в GitHub
"""

import asyncio
import sys
import os
import time

# Добавляем путь к модулям
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    DIRECT_TLDS, SYSTEM_DOMAINS, IGNORED_SUFFIXES,
    MIN_DOMAIN_LENGTH, DEDUP_TTL,
)
from dns_parser import stream_dns_domains
from checker import is_domain_blocked
from notifier import ask_user_add_domain
from config_updater import (
    load_config_domains, load_ignored_domains,
    save_ignored_domain, add_domain_to_config, git_push,
)


class DomainMonitor:
    def __init__(self):
        self.config_domains: set[str] = set()
        self.ignored_domains: set[str] = set()
        self.seen: dict[str, float] = {}  # domain -> timestamp
        self._reload_config()

    def _reload_config(self):
        """Перечитывает конфиг и ignored-список."""
        self.config_domains = load_config_domains()
        self.ignored_domains = load_ignored_domains()
        print(f"[config] Loaded {len(self.config_domains)} domains from config, "
              f"{len(self.ignored_domains)} ignored")

    def should_check(self, domain: str) -> bool:
        """Определяет, нужно ли проверять домен."""
        if len(domain) < MIN_DOMAIN_LENGTH:
            return False

        # Игнорировать локальные/служебные
        for suffix in IGNORED_SUFFIXES:
            if domain.endswith(suffix):
                return False

        # Игнорировать российские TLD
        for tld in DIRECT_TLDS:
            if domain.endswith(tld):
                return False

        # Игнорировать системные домены Apple
        for sys_domain in SYSTEM_DOMAINS:
            if domain == sys_domain or domain.endswith('.' + sys_domain):
                return False

        # Уже в конфиге
        if domain in self.config_domains:
            return False
        # Проверяем суффиксы из конфига
        for cfg_domain in self.config_domains:
            if domain.endswith('.' + cfg_domain):
                return False

        # Отклонён пользователем
        if domain in self.ignored_domains:
            return False

        # Дедупликация по времени
        now = time.time()
        if domain in self.seen and (now - self.seen[domain]) < DEDUP_TTL:
            return False
        self.seen[domain] = now

        return True

    async def handle_domain(self, domain: str):
        """Проверяет домен и предлагает добавить если заблокирован."""
        blocked = await is_domain_blocked(domain)
        if not blocked:
            return

        print(f"[blocked] {domain} — недоступен, спрашиваю пользователя...")

        accepted = await ask_user_add_domain(domain)
        if accepted:
            add_domain_to_config(domain)
            print(f"[added] {domain} добавлен в конфиг")
            pushed = await git_push(domain)
            if pushed:
                print(f"[pushed] Изменения отправлены в GitHub")
            else:
                print(f"[warn] Не удалось отправить в GitHub")
            self.config_domains.add(domain)
        else:
            save_ignored_domain(domain)
            self.ignored_domains.add(domain)
            print(f"[ignored] {domain} добавлен в список игнорируемых")

    async def run(self):
        """Основной цикл мониторинга."""
        print("[start] Shadowrocket AutoConfig Monitor запущен")
        print(f"[info] Мониторинг DNS-запросов через tcpdump...")

        async for domain in stream_dns_domains():
            if self.should_check(domain):
                # Запускаем проверку в фоне, не блокируя мониторинг
                asyncio.create_task(self.handle_domain(domain))


async def main():
    monitor = DomainMonitor()
    try:
        await monitor.run()
    except KeyboardInterrupt:
        print("\n[stop] Остановлен пользователем")


if __name__ == '__main__':
    asyncio.run(main())
