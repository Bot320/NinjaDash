#!/usr/bin/env bash
# Downloads NinjaDash from GitHub and installs or updates it. Short enough to type by hand:
#
#   curl -fsSL https://raw.githubusercontent.com/Bot320/NinjaDash/main/get.sh | bash
#
# Options go after `bash -s --`:
#   ... | bash -s -- --home-assistant          any install.sh option (first install)
#   ... | bash -s -- --branch fix/something    test a branch instead of main
#   ... | bash -s -- --no-install              only download to ~/ninjadash-src
set -euo pipefail

BRANCH=main
INSTALL=1
ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --branch) BRANCH="${2:?--branch needs a name}"; shift ;;
    --no-install) INSTALL=0 ;;
    *) ARGS+=("$1") ;;
  esac
  shift
done

DIR="$HOME/ninjadash-src"
URL="https://github.com/Bot320/NinjaDash/archive/refs/heads/$BRANCH.tar.gz"
echo "==> Downloading NinjaDash ($BRANCH)"
rm -rf "$DIR.new" && mkdir -p "$DIR.new"
curl -fsSL "$URL" | tar xz -C "$DIR.new" --strip-components=1 \
  || { echo "Download failed: $URL"; rm -rf "$DIR.new"; exit 1; }
rm -rf "$DIR" && mv "$DIR.new" "$DIR"
echo "    $(sed -n 's/^__version__ = "\(.*\)"/version \1/p' "$DIR/backend/ninjadash/__init__.py") in $DIR"

if [[ $INSTALL == 1 ]]; then
  cd "$DIR"
  # Read answers from the keyboard, not from the pipe this script came through.
  sudo bash deploy/install.sh "${ARGS[@]}" < /dev/tty
fi
