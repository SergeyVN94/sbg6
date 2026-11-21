#!/usr/bin/env bash
# Устанавливает ярлык, иконку, правило udev и systemd-юнит восстановления профиля.
# Само приложение работает прямо из этой папки — копирования не требуется.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${HOME}/.local/bin"
DATA_DIR="${XDG_DATA_HOME:-${HOME}/.local/share}"
APPS_DIR="${DATA_DIR}/applications"
ICONS_DIR="${DATA_DIR}/icons/hicolor/scalable/apps"
UNIT_DIR="${XDG_CONFIG_HOME:-${HOME}/.config}/systemd/user"
RULE_SRC="${ROOT}/packaging/70-sbg6.rules"
RULE_DST="/etc/udev/rules.d/70-sbg6.rules"

INSTALL_UDEV=1
for arg in "$@"; do
    case "${arg}" in
        --no-udev) INSTALL_UDEV=0 ;;
        -h|--help)
            echo "Использование: $0 [--no-udev]"
            exit 0
            ;;
    esac
done

mkdir -p "${BIN_DIR}" "${APPS_DIR}" "${ICONS_DIR}" "${UNIT_DIR}"
chmod +x "${ROOT}/bin/g6"
ln -sf "${ROOT}/bin/g6" "${BIN_DIR}/g6"

sed "s|@ROOT@|${ROOT}|g" "${ROOT}/assets/sbg6.desktop" > "${APPS_DIR}/sbg6.desktop"
cp "${ROOT}/assets/sbg6.svg" "${ICONS_DIR}/sbg6.svg"

sed "s|@ROOT@|${ROOT}|g" "${ROOT}/systemd/sbg6-restore.service" > "${UNIT_DIR}/sbg6-restore.service"

if [[ "${INSTALL_UDEV}" -eq 1 ]]; then
    if ! cmp -s "${RULE_SRC}" "${RULE_DST}" 2>/dev/null; then
        echo "Устанавливаю правило udev (потребуется пароль sudo)…"
        sudo install -m 644 "${RULE_SRC}" "${RULE_DST}"
        sudo udevadm control --reload-rules
        sudo udevadm trigger --subsystem-match=hidraw --action=change
    fi
fi

systemctl --user daemon-reload 2>/dev/null || true
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "${APPS_DIR}" 2>/dev/null || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q -t "${DATA_DIR}/icons/hicolor" 2>/dev/null || true

cat <<EOF

Установлено:
  ${BIN_DIR}/g6
  ${APPS_DIR}/sbg6.desktop
  ${ICONS_DIR}/sbg6.svg
  ${UNIT_DIR}/sbg6-restore.service
  ${RULE_DST}

Запуск окна:       g6 gui
Проверка:          g6 status
Автовосстановление профиля при входе:
  systemctl --user enable sbg6-restore.service

Если ~/.local/bin отсутствует в PATH, добавьте его в ~/.zshrc или ~/.bashrc.
EOF
