#!/usr/bin/env bash
# VideoMiner 品牌图标一键切换。
#   bash frontend/brand-icons/switch.sh <变体名>   切换并重新构建到 backend/static
#   bash frontend/brand-icons/switch.sh            查看当前变体和可用变体
# 每个变体是本目录下的一个子目录，必须有 favicon.svg favicon.ico apple-touch-icon.png logo.css。
# 说明见 backend/CLAUDE.md 的 Brand Icon 一节。
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONT="$(dirname "$HERE")"
ACTIVE_CSS="$FRONT/src/assets/brand-logo.css"
FILES=(favicon.svg favicon.ico apple-touch-icon.png logo.css)

current() { sed -n 's#.*brand-icon: *\([A-Za-z0-9_-]*\).*#\1#p' "$ACTIVE_CSS" 2>/dev/null | head -1; }
variants() { for d in "$HERE"/*/; do basename "$d"; done | tr '\n' ' '; }

if [ $# -eq 0 ]; then
  echo "当前变体: $(current || true)"
  echo "可用变体: $(variants)"
  exit 0
fi

V="$1"
SRC="$HERE/$V"
[ -d "$SRC" ] || { echo "没有这个变体: $V（可用: $(variants)）" >&2; exit 1; }
for f in "${FILES[@]}"; do
  [ -f "$SRC/$f" ] || { echo "变体 $V 缺文件: $f" >&2; exit 1; }
done

cp "$SRC/favicon.svg" "$SRC/favicon.ico" "$SRC/apple-touch-icon.png" "$FRONT/public/"
cp "$SRC/logo.css" "$ACTIVE_CSS"
# 图标链接带上变体名，浏览器才会重新拉取；否则标签页可能继续显示缓存里的旧图标
sed -i -E "s#(href=\"/(static/)?(favicon\.ico|favicon\.svg|apple-touch-icon\.png))(\?v=[A-Za-z0-9_-]*)?\"#\1?v=$V\"#g" "$FRONT/index.html"

cd "$FRONT"
npx vite build
echo "已切换到 $V。刷新页面即可看到侧栏图标；标签页图标没变的话，关掉标签页重新打开。"
