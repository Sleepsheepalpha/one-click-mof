#!/usr/bin/env bash
# Install One-Click MOF as a desktop application and add it to GNOME favorites.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
APP_NAME="one-click-mof"
APP_LABEL="One-Click MOF"
ICON_SRC="$HERE/static/icon.png"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
APPS="$DATA_HOME/applications"
ICON_DIR="$DATA_HOME/icons/hicolor/512x512/apps"
DESKTOP_FILE="$APPS/$APP_NAME.desktop"

mkdir -p "$APPS" "$ICON_DIR"
cp "$ICON_SRC" "$ICON_DIR/$APP_NAME.png"
chmod +x "$HERE/start.sh"

cat >"$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=$APP_LABEL
Name[zh_CN]=One-Click MOF
GenericName=MOF adsorption workbench
Comment=Local browser workbench for MOF adsorption calculations
Comment[zh_CN]=本地 MOF 吸附计算网页工作台
Exec=$HERE/start.sh
TryExec=$HERE/start.sh
Path=$ROOT
Icon=$APP_NAME
Terminal=false
Categories=Science;Chemistry;
Keywords=MOF;adsorption;QE;MACE;ASE;
StartupNotify=true
EOF
chmod +x "$DESKTOP_FILE"

# Desktop shortcut (Ubuntu uses the localized Desktop directory).
DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
[ -n "$DESKTOP_DIR" ] || DESKTOP_DIR="$HOME/Desktop"
mkdir -p "$DESKTOP_DIR"
cp "$DESKTOP_FILE" "$DESKTOP_DIR/$APP_LABEL.desktop"
chmod +x "$DESKTOP_DIR/$APP_LABEL.desktop"
if command -v gio >/dev/null 2>&1; then
  gio set "$DESKTOP_DIR/$APP_LABEL.desktop" metadata::trusted true 2>/dev/null || true
fi

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$APPS" >/dev/null 2>&1 || true
fi

# Add to GNOME favorites (dock) if available.
if command -v gsettings >/dev/null 2>&1; then
  python3 - <<'PY'
import ast
import subprocess
import sys

key = ["org.gnome.shell", "favorite-apps"]
app = "one-click-mof.desktop"
try:
    cur = subprocess.check_output(["gsettings", "get", *key], text=True).strip()
    apps = ast.literal_eval(cur)
    if not isinstance(apps, list):
        apps = []
    if app not in apps:
        apps.append(app)
        subprocess.run(["gsettings", "set", *key, repr(apps)], check=False)
except Exception as exc:
    print("无法自动加入 GNOME 收藏夹：", exc, file=sys.stderr)
PY
fi

echo "已安装：$DESKTOP_FILE"
echo "桌面快捷方式：$DESKTOP_DIR/$APP_LABEL.desktop"
echo "图标：$ICON_DIR/$APP_NAME.png"
echo "如果任务栏没有立即出现，注销/重新登录一次，或右键桌面图标选择“允许启动”。"
