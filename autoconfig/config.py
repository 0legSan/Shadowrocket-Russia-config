"""Настройки для shadowrocket-autoconfig."""

import os
from pathlib import Path

# Путь к репозиторию с конфигом
REPO_PATH = Path(os.environ.get(
    "SR_REPO_PATH",
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
))

# Путь к конфигу Shadowrocket
CONFIG_FILE = REPO_PATH / "shadsocks_in.conf"

# Путь к файлу игнорируемых доменов
IGNORED_DOMAINS_FILE = Path(os.path.dirname(os.path.abspath(__file__))) / "ignored_domains.txt"

# TCP-проверка доступности
CHECK_TIMEOUT = 3  # секунды
CHECK_PORT = 443
MAX_CONCURRENT_CHECKS = 5

# Российские TLD — идут DIRECT, не проверяем
DIRECT_TLDS = {
    '.ru', '.su', '.xn--p1ai',  # .рф
    '.com.ru', '.net.ru', '.org.ru', '.pp.ru', '.ru.net',
}

# Системные домены macOS — игнорировать
SYSTEM_DOMAINS = {
    'apple.com', 'icloud.com', 'mzstatic.com', 'aaplimg.com',
    'cdn-apple.com', 'apple-dns.net', 'push.apple.com',
    'appleiphonecell.com', 'apple.news', 'apple-cloudkit.com',
    'gc.apple.com', 'ls.apple.com', 'swscan.apple.com',
}

# Суффиксы для игнорирования
IGNORED_SUFFIXES = {
    '.local', '.internal', '.localhost', '.arpa',
    '.lan', '.home', '.test', '.invalid',
}

# Минимальная длина домена для проверки
MIN_DOMAIN_LENGTH = 4

# Интервал дедупликации (секунды) — не проверять один домен чаще
DEDUP_TTL = 3600  # 1 час
