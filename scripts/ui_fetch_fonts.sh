#!/usr/bin/env bash
# scripts/ui_fetch_fonts.sh
#
# Self-host the 6 woff2 files referenced by tokens.css:
#   Inter Display 4.x — weights 400 / 500 / 700
#   JetBrains Mono 2.304 — weights 400 / 500 / 700
#
# Both fonts are SIL OFL 1.1. The license texts are mirrored under
# src/karasu/ui/static/assets/fonts/ alongside the binaries so the
# repo is self-contained for an audit.
#
# Idempotent: skips a file if it already exists with non-zero size.
# Usage:
#     bash scripts/ui_fetch_fonts.sh
#
# Requires curl. Run from repo root.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${REPO_ROOT}/src/karasu/ui/static/fonts"
mkdir -p "${DEST}"

# Format: url|destination_filename
FILES=(
    "https://rsms.me/inter/font-files/InterDisplay-Regular.woff2|inter-display-400.woff2"
    "https://rsms.me/inter/font-files/InterDisplay-Medium.woff2|inter-display-500.woff2"
    "https://rsms.me/inter/font-files/InterDisplay-Bold.woff2|inter-display-700.woff2"
    "https://raw.githubusercontent.com/JetBrains/JetBrainsMono/v2.304/fonts/webfonts/JetBrainsMono-Regular.woff2|jetbrains-mono-400.woff2"
    "https://raw.githubusercontent.com/JetBrains/JetBrainsMono/v2.304/fonts/webfonts/JetBrainsMono-Medium.woff2|jetbrains-mono-500.woff2"
    "https://raw.githubusercontent.com/JetBrains/JetBrainsMono/v2.304/fonts/webfonts/JetBrainsMono-Bold.woff2|jetbrains-mono-700.woff2"
)

LICENSES=(
    "https://raw.githubusercontent.com/rsms/inter/v4.0/LICENSE.txt|LICENSE-Inter.txt"
    "https://raw.githubusercontent.com/JetBrains/JetBrainsMono/v2.304/OFL.txt|LICENSE-JetBrainsMono.txt"
)

fetch() {
    local url="$1" name="$2" target="${DEST}/$2"
    if [[ -s "${target}" ]]; then
        printf '  skip   %s (already present)\n' "${name}"
        return 0
    fi
    printf '  fetch  %s\n' "${name}"
    curl --fail --location --silent --show-error --output "${target}" "${url}"
    if [[ ! -s "${target}" ]]; then
        printf 'error: empty download %s\n' "${name}" >&2
        rm -f "${target}"
        return 1
    fi
}

printf 'fonts → %s\n' "${DEST}"
for entry in "${FILES[@]}"; do
    IFS='|' read -r url name <<<"${entry}"
    fetch "${url}" "${name}"
done

printf 'licenses → %s\n' "${DEST}"
for entry in "${LICENSES[@]}"; do
    IFS='|' read -r url name <<<"${entry}"
    fetch "${url}" "${name}"
done

# Sanity check: every binary must be a real woff2 (magic bytes "wOF2").
for entry in "${FILES[@]}"; do
    IFS='|' read -r _ name <<<"${entry}"
    target="${DEST}/${name}"
    magic="$(head -c 4 "${target}" | od -An -c | tr -d ' \n')"
    if [[ "${magic}" != "wOF2" ]]; then
        printf 'error: %s is not a woff2 file (magic=%q)\n' "${name}" "${magic}" >&2
        exit 1
    fi
done

printf 'done. %d woff2 + %d licenses under %s\n' \
    "${#FILES[@]}" "${#LICENSES[@]}" "${DEST}"
