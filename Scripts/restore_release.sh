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
  echo 'Download SHA256SUMS into the same folder as the two parts.' >&2
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

verify "$name.part00"
verify "$name.part01"
cat "$name.part00" "$name.part01" > "$name.partial"
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
