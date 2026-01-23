"""Обновление конфига Shadowrocket и push в GitHub."""

import asyncio
from config import CONFIG_FILE, REPO_PATH, IGNORED_DOMAINS_FILE


def load_config_domains() -> set[str]:
    """Загружает все домены из текущего конфига (PROXY и DIRECT)."""
    domains = set()
    if not CONFIG_FILE.exists():
        return domains

    for line in CONFIG_FILE.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if line.startswith('DOMAIN-SUFFIX,') or line.startswith('DOMAIN-KEYWORD,'):
            parts = line.split(',')
            if len(parts) >= 2:
                domain = parts[1].strip().lstrip('.')
                if domain:
                    domains.add(domain.lower())
    return domains


def load_ignored_domains() -> set[str]:
    """Загружает домены, отклонённые пользователем."""
    if not IGNORED_DOMAINS_FILE.exists():
        return set()
    return {
        line.strip().lower()
        for line in IGNORED_DOMAINS_FILE.read_text(encoding='utf-8').splitlines()
        if line.strip()
    }


def save_ignored_domain(domain: str) -> None:
    """Добавляет домен в список игнорируемых."""
    with open(IGNORED_DOMAINS_FILE, 'a', encoding='utf-8') as f:
        f.write(domain + '\n')


def add_domain_to_config(domain: str) -> None:
    """Добавляет DOMAIN-SUFFIX правило в конфиг перед строкой '// Proxy'."""
    content = CONFIG_FILE.read_text(encoding='utf-8')
    new_rule = f'DOMAIN-SUFFIX,{domain},PROXY\n'

    # Вставляем перед "// Proxy" если есть, иначе перед FINAL
    if '// Proxy' in content:
        content = content.replace('// Proxy\n', new_rule + '// Proxy\n')
    elif 'FINAL,' in content:
        content = content.replace('FINAL,', new_rule + 'FINAL,')
    else:
        # Добавляем в конец секции [Rule]
        content = content.replace('[Host]', new_rule + '\n[Host]')

    CONFIG_FILE.write_text(content, encoding='utf-8')


async def git_push(domain: str) -> bool:
    """Коммитит и пушит изменения в GitHub."""
    commands = [
        ['git', '-C', str(REPO_PATH), 'add', str(CONFIG_FILE.name)],
        ['git', '-C', str(REPO_PATH), 'commit', '-m', f'Add {domain} to proxy'],
        ['git', '-C', str(REPO_PATH), 'push'],
    ]

    for cmd in commands:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            print(f"[git error] {' '.join(cmd)}: {stderr.decode()}")
            return False
    return True
