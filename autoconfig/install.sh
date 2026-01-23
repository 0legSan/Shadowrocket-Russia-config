#!/bin/bash
# Установка Shadowrocket AutoConfig как LaunchDaemon

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
PLIST_SRC="$REPO_DIR/com.shadowrocket.autoconfig.plist"
PLIST_DST="/Library/LaunchDaemons/com.shadowrocket.autoconfig.plist"

echo "=== Shadowrocket AutoConfig Installer ==="

# Проверяем sudo
if [ "$EUID" -ne 0 ]; then
    echo "Требуется sudo. Запустите: sudo ./install.sh"
    exit 1
fi

# Останавливаем если уже запущен
if launchctl list | grep -q com.shadowrocket.autoconfig; then
    echo "[*] Останавливаю существующий демон..."
    launchctl unload "$PLIST_DST" 2>/dev/null || true
fi

# Обновляем путь к скрипту в plist
sed "s|/Users/mac/My/2-Research/terminal-work/Shadowrocket-Russia-config|$REPO_DIR|g" \
    "$PLIST_SRC" > "$PLIST_DST"

# Устанавливаем права
chown root:wheel "$PLIST_DST"
chmod 644 "$PLIST_DST"

# Загружаем демон
launchctl load "$PLIST_DST"

echo "[+] Демон установлен и запущен"
echo "[+] Логи: /tmp/shadowrocket-autoconfig.log"
echo "[+] Ошибки: /tmp/shadowrocket-autoconfig.err"
echo ""
echo "Для остановки: sudo launchctl unload $PLIST_DST"
echo "Для удаления:  sudo rm $PLIST_DST"
