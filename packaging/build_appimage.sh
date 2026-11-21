#!/usr/bin/env bash
# Builds a self-contained AppImage into build/dist/.
#
# Requirements: PyInstaller with PySide6 visible to the interpreter, rsvg-convert,
# appimagetool (downloaded automatically into build/tools).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "${ROOT}/g6app/__init__.py")"
WORK="${ROOT}/build/appimage"
DIST="${ROOT}/build/dist"
TOOLS="${ROOT}/build/tools"
APPDIR="${WORK}/AppDir"
PYTHON="${PYTHON:-/usr/bin/python3}"
PYINSTALLER_MODULE="${PYINSTALLER_MODULE:-PyInstaller}"
TOOL_URL="https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"

mkdir -p "${WORK}" "${DIST}" "${TOOLS}"

echo "== PyInstaller"
env -u APPIMAGE -u APPDIR -u OWD PYTHONPATH="${PYTHONPATH:-}" "${PYTHON}" -m "${PYINSTALLER_MODULE}" \
    --noconfirm --clean --windowed --name sbg6 \
    --add-data "${ROOT}/assets/sbg6.svg:assets" \
    --paths "${ROOT}" \
    --hidden-import PySide6.QtWidgets --hidden-import PySide6.QtGui \
    --hidden-import PySide6.QtCore --hidden-import PySide6.QtSvg \
    --distpath "${WORK}/dist" --workpath "${WORK}/build" --specpath "${WORK}" \
    "${ROOT}/packaging/appimage_entry.py"

echo "== AppDir"
rm -rf "${APPDIR}"
mkdir -p "${APPDIR}/usr/bin"
cp -a "${WORK}/dist/sbg6/." "${APPDIR}/usr/bin/"

cat > "${APPDIR}/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/sbg6" "$@"
EOF
chmod +x "${APPDIR}/AppRun"

sed -e 's|@EXEC@|sbg6|g' "${ROOT}/assets/sbg6.desktop" > "${APPDIR}/sbg6.desktop"
rsvg-convert -w 256 -h 256 "${ROOT}/assets/sbg6.svg" -o "${APPDIR}/sbg6.png"
cp "${APPDIR}/sbg6.png" "${APPDIR}/.DirIcon"
cp "${ROOT}/assets/sbg6.svg" "${APPDIR}/sbg6.svg"

echo "== appimagetool"
TOOL="${TOOLS}/appimagetool-x86_64.AppImage"
if [ ! -x "${TOOL}" ]; then
    curl -L --fail -o "${TOOL}" "${TOOL_URL}"
    chmod +x "${TOOL}"
fi

OUT="${DIST}/sbg6-${VERSION}-x86_64.AppImage"
ARCH=x86_64 "${TOOL}" --appimage-extract-and-run --no-appstream "${APPDIR}" "${OUT}" \
    || ARCH=x86_64 "${TOOL}" --no-appstream "${APPDIR}" "${OUT}"

chmod +x "${OUT}"
echo "${OUT}"
