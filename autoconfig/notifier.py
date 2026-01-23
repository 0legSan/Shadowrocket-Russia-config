"""macOS уведомления через osascript."""

import asyncio


async def ask_user_add_domain(domain: str) -> bool:
    """
    Показывает macOS диалог с вопросом о добавлении домена в прокси.
    Возвращает True если пользователь нажал "Добавить".
    """
    script = (
        f'display dialog "Домен {domain} недоступен напрямую.\\n'
        f'Добавить в прокси Shadowrocket?" '
        f'with title "Shadowrocket AutoConfig" '
        f'buttons {{"Игнорировать", "Добавить"}} '
        f'default button "Добавить" '
        f'giving up after 30'
    )

    proc = await asyncio.create_subprocess_exec(
        '/usr/bin/osascript', '-e', script,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    stdout, _ = await proc.communicate()
    result = stdout.decode('utf-8', errors='ignore')

    return 'Добавить' in result and 'gave up:true' not in result
