#!/usr/bin/env bash
# Packs NinjaDash into dist/ninjadash-<version>.tar.gz, ready to copy to the mini PC.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
VERSION=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' backend/ninjadash/__init__.py)
OUT="dist/ninjadash-$VERSION.tar.gz"
mkdir -p dist
tar --exclude='__pycache__' --exclude='*.pyc' \
    --transform "s,^,ninjadash-$VERSION/," \
    -czf "$OUT" README.md backend frontend deploy config tests docs/PLAN.md
echo "$OUT ($(du -h "$OUT" | cut -f1))"
