#!/usr/bin/env bash
# Builds a Debian package into build/dist/ without dpkg-deb (ar + tar only).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "${ROOT}/g6app/__init__.py")"
ARCH="${ARCH:-all}"
WORK="${ROOT}/build/deb"
PKG="sbg6_${VERSION}_${ARCH}.deb"
OUT="${ROOT}/build/dist"

rm -rf "${WORK}"
mkdir -p "${WORK}/data/usr/bin" \
         "${WORK}/data/usr/lib/sbg6" \
         "${WORK}/data/usr/share/applications" \
         "${WORK}/data/usr/share/icons/hicolor/scalable/apps" \
         "${WORK}/data/usr/lib/udev/rules.d" \
         "${WORK}/data/usr/lib/systemd/user" \
         "${WORK}/data/usr/share/doc/sbg6" \
         "${WORK}/control" "${OUT}"

# application payload
cp -a "${ROOT}/g6app" "${WORK}/data/usr/lib/sbg6/"
find "${WORK}/data/usr/lib/sbg6" -name '__pycache__' -type d -prune -exec rm -rf {} +
cp -a "${ROOT}/assets" "${WORK}/data/usr/lib/sbg6/assets"
install -m 755 "${ROOT}/bin/g6" "${WORK}/data/usr/bin/g6"
install -m 644 "${ROOT}/packaging/70-sbg6.rules" "${WORK}/data/usr/lib/udev/rules.d/70-sbg6.rules"
install -m 644 "${ROOT}/assets/sbg6.svg" \
    "${WORK}/data/usr/share/icons/hicolor/scalable/apps/sbg6.svg"
install -m 644 "${ROOT}/README.md" "${WORK}/data/usr/share/doc/sbg6/README.md"
install -m 644 "${ROOT}/README.en.md" "${WORK}/data/usr/share/doc/sbg6/README.en.md"
install -m 644 "${ROOT}/LICENSE" "${WORK}/data/usr/share/doc/sbg6/copyright"

sed -e 's|@EXEC@|g6 gui|g' "${ROOT}/assets/sbg6.desktop" \
    > "${WORK}/data/usr/share/applications/sbg6.desktop"
sed -e "s|@ROOT@||g" "${ROOT}/systemd/sbg6-restore.service" \
    | sed -e 's|/bin/g6|/usr/bin/g6|g' \
    > "${WORK}/data/usr/lib/systemd/user/sbg6-restore.service"

# control metadata
cat > "${WORK}/control/control" <<EOF
Package: sbg6
Version: ${VERSION}
Section: sound
Priority: optional
Architecture: ${ARCH}
Maintainer: Sergey <blakdgak@yandex.ru>
Homepage: https://github.com/SergeyVN94/sbg6
Depends: python3 (>= 3.10), python3-pyside6.qtwidgets, libasound2 | libasound2t64
Description: Sound BlasterX G6 control app for Linux
 SBX effects, 10-band equalizer, Scout Mode, Direct Mode, microphone
 processing, mixer, DAC filter and RGB lighting for the Creative
 Sound BlasterX G6 (041e:3256). Works through hidraw without a USB reset.
EOF

cat > "${WORK}/control/postinst" <<'EOF'
#!/bin/sh
set -e
if command -v udevadm >/dev/null 2>&1; then
    udevadm control --reload-rules || true
    udevadm trigger --subsystem-match=hidraw --action=change || true
fi
if [ -d /run/systemd/system ]; then
    systemctl --global daemon-reload 2>/dev/null || true
fi
exit 0
EOF

cat > "${WORK}/control/postrm" <<'EOF'
#!/bin/sh
set -e
if command -v udevadm >/dev/null 2>&1; then
    udevadm control --reload-rules || true
fi
exit 0
EOF
chmod 755 "${WORK}/control/postinst" "${WORK}/control/postrm"

( cd "${WORK}/data" && find . -type f ! -path './DEBIAN/*' -print0 \
    | xargs -0 md5sum > "${WORK}/control/md5sums" )
sed -i 's|  \./|  |' "${WORK}/control/md5sums"

echo "2.0" > "${WORK}/debian-binary"
( cd "${WORK}/control" && tar --owner=0 --group=0 --numeric-owner -cJf "${WORK}/control.tar.xz" . )
( cd "${WORK}/data" && tar --owner=0 --group=0 --numeric-owner -cJf "${WORK}/data.tar.xz" . )
( cd "${WORK}" && ar rcs "${OUT}/${PKG}" debian-binary control.tar.xz data.tar.xz )

echo "${OUT}/${PKG}"
