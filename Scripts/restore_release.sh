#!/bin/bash
set -euo pipefail

# Release copies run from their download folder. The source script accepts a
# download folder as its second argument, defaulting to the current folder.
case "$(basename "$0")" in
  Restore-Vendor.command) mode=vendor; cd "$(dirname "$0")" ;;
  Restore-Installer.command) mode=installer; cd "$(dirname "$0")" ;;
  *) mode=${1:-installer}; cd "${2:-.}" ;;
esac

case "$mode" in
  installer) name=Parakeet-SRT-Creator-Apple-Silicon.dmg ;;
  vendor) name=Parakeet-SRT-Creator-vendor.tar ;;
  *) echo 'Usage: bash Scripts/restore_release.sh [installer|vendor] [download-folder]' >&2; exit 1 ;;
esac

if [[ ! -f SHA256SUMS ]]; then
  echo 'Download SHA256SUMS into the same folder as this script.' >&2
  exit 1
fi

verify() {
  local file=$1
  local expected
  expected=$(awk -v name="$file" '$2 == name {print $1}' SHA256SUMS)
  if [[ ! -f "$file" || ${#expected} -ne 64 ]]; then
    echo "Missing file or checksum: $file" >&2
    exit 1
  fi
  printf '%s  %s\n' "$expected" "$file" | shasum -a 256 -c -
}

parts=()
while read -r digest file; do
  case "$file" in
    "$name".part[0-9][0-9]) parts+=("$file") ;;
  esac
done < SHA256SUMS
if [[ ${#parts[@]} -eq 0 ]]; then
  echo "No parts listed for $name in SHA256SUMS" >&2
  exit 1
fi
for part in "${parts[@]}"; do
  if [[ ! -f "$part" ]]; then
    curl --fail --location --retry 5 --retry-all-errors --retry-delay 1 \
      --output "$part.partial" \
      "https://github.com/samoxin1974/Parakeet-SRT-Creator/releases/download/v1.0.0/$part"
    mv "$part.partial" "$part"
  fi
  verify "$part"
done
cat "${parts[@]}" > "$name.partial"
mv "$name.partial" "$name"
verify "$name"

if [[ "$mode" == vendor ]]; then
  tar -xf "$name"
  echo "Restored model and FFmpeg executables into $(pwd)/vendor"
else
  echo "Installer ready: $(pwd)/$name"
  if [[ "$(uname -s)" == Darwin ]]; then
    open "$name"
  fi
fi
