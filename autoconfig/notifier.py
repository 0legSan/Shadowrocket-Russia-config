"""macOS уведомления через osascript."""

import asyncio
import os


def _get_gui_user() -> str:
    """Определяет пользователя текущей GUI-сессии."""
    return os.popen("stat -f%Su /dev/console").read().strip() or "mac"


async def ask_user_add_domains(domains: list[str]) -> list[str]:
    """
    Показывает macOS диалог со списком заблокированных доменов.
    Возвращает список доменов, которые пользователь согласился добавить.
    """
    if not domains:
        return []

    domain_list = '\\n'.join(f'  • {d}' for d in domains)
    count = len(domains)
    word = _plural(count)

    script = (
        f'display dialog "Обнаружен{_ending(count)} {count} заблокированн{word} домен{_suffix(count)}:\\n'
        f'{domain_list}\\n\\n'
        f'Добавить в прокси Shadowrocket?" '
        f'with title "Shadowrocket AutoConfig" '
        f'buttons {{"Игнорировать", "Добавить все"}} '
        f'default button "Добавить все" '
        f'giving up after 60'
    )

    gui_user = _get_gui_user()

    if os.geteuid() == 0 and gui_user != 'root':
        cmd = ['/usr/bin/sudo', '-u', gui_user, '/usr/bin/osascript', '-e', script]
    else:
        cmd = ['/usr/bin/osascript', '-e', script]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    stdout, _ = await proc.communicate()
    result = stdout.decode('utf-8', errors='ignore')

    if 'Добавить' in result and 'gave up:true' not in result:
        return domains
    return []


def _plural(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return 'ый'
    return 'ых'


def _ending(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return ''
    return 'о'


def _suffix(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return ''
    if 2 <= n % 10 <= 4 and not (12 <= n % 100 <= 14):
        return 'а'
    return 'ов'
