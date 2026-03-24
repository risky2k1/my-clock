#!/bin/sh
# Build custom-clock_*.deb using only dpkg-deb (no debhelper required).
set -e
ROOT=$(dirname "$0")/..
ROOT=$(cd "$ROOT" && pwd)
VER=0.1.0
DEB_REV=1
PKG=custom-clock
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT

mkdir -p "$STAGE/DEBIAN"
mkdir -p "$STAGE/usr/share/custom-clock/locales"
mkdir -p "$STAGE/usr/share/custom-clock/assets"
mkdir -p "$STAGE/usr/bin"
mkdir -p "$STAGE/usr/share/applications"

cat >"$STAGE/DEBIAN/control" <<EOF
Package: $PKG
Version: $VER-$DEB_REV
Section: utils
Priority: optional
Architecture: all
Maintainer: Custom Clock <none@localhost>
Depends: python3:any, python3-pyqt6
Description: desktop alarm clock for Linux
 PyQt6-based alarm clock with optional login autostart via settings.
EOF

install -m 644 "$ROOT/main.py" "$STAGE/usr/share/custom-clock/"
install -m 644 "$ROOT/requirements.txt" "$STAGE/usr/share/custom-clock/"
install -m 644 "$ROOT/locales/vi.json" "$ROOT/locales/en.json" \
  "$STAGE/usr/share/custom-clock/locales/"
install -m 644 "$ROOT/assets/trash.png" "$ROOT/assets/trash-solid.png" \
  "$STAGE/usr/share/custom-clock/assets/"
install -m 755 "$ROOT/bin/custom-clock" "$STAGE/usr/bin/custom-clock"
install -m 644 "$ROOT/debian/custom-clock.desktop" "$STAGE/usr/share/applications/"

OUT="$ROOT/${PKG}_${VER}-${DEB_REV}_all.deb"
dpkg-deb --root-owner-group -Zxz -b "$STAGE" "$OUT"
echo "Built: $OUT"
echo "Install: sudo apt install -y ./$(basename "$OUT")"
