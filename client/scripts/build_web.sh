#!/usr/bin/env bash
# Build the Flutter web bundle for manual / Phase-B verification.
# Phase A: out of CI; run locally before tagging a release.
set -euo pipefail
cd "$(dirname "$0")/.."
flutter build web --release
echo "Built client/build/web/ — serve with:"
echo "  cd client/build/web && python -m http.server 8080"