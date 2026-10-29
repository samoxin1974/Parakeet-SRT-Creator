#!/bin/zsh
set -euo pipefail

SCRIPT_DIR=${0:A:h}
PROJECT_DIR=${SCRIPT_DIR:h}
APP_NAME="Parakeet SRT Creator"
TARGET_ARCH=${PARAKEET_TARGET_ARCH:-arm64}
if [[ "${TARGET_ARCH}" != "arm64" && "${TARGET_ARCH}" != "x86_64" ]]; then
  print -u2 "PARAKEET_TARGET_ARCH must be arm64 or x86_64."
  exit 1
fi
if [[ "${TARGET_ARCH}" == "x86_64" ]]; then
  ARCH_LABEL="Intel"
  VENV_DIR=${PARAKEET_VENV_DIR:-.venv-intel}
  ARCH_RUN=(arch -x86_64)
else
  ARCH_LABEL="Apple-Silicon"
  VENV_DIR=${PARAKEET_VENV_DIR:-.venv}
  ARCH_RUN=()
fi
DIST_DIR="${PROJECT_DIR}/dist"
BUILD_DIR="${PROJECT_DIR}/build"
STAGING_DIR="${BUILD_DIR}/dmg-root"
APP_PATH="${DIST_DIR}/${APP_NAME}.app"
DMG_PATH="${DIST_DIR}/Parakeet-SRT-Creator-${ARCH_LABEL}.dmg"

cd "${PROJECT_DIR}"
export PYINSTALLER_CONFIG_DIR="${PROJECT_DIR}/.pyinstaller"
export MPLCONFIGDIR="${PROJECT_DIR}/.cache/matplotlib"
export XDG_CACHE_HOME="${PROJECT_DIR}/.cache"

if [[ ! -x "${VENV_DIR}/bin/pyinstaller" ]]; then
  print -u2 "PyInstaller is not installed in ${VENV_DIR}."
  exit 1
fi

if [[ ! -f "vendor/parakeet-tdt-0.6b-v2.nemo" ]]; then
  print -u2 "The bundled Parakeet model is missing."
  exit 1
fi

FFMPEG_PATH="vendor/ffmpeg-${TARGET_ARCH}"
if [[ "${TARGET_ARCH}" == "arm64" && ! -e "${FFMPEG_PATH}" ]]; then
  FFMPEG_PATH="vendor/ffmpeg"
fi
if [[ ! -x "${FFMPEG_PATH}" ]]; then
  print -u2 "The bundled ${TARGET_ARCH} FFmpeg executable is missing."
  exit 1
fi
if ! file "${FFMPEG_PATH}" | grep -q "${TARGET_ARCH}"; then
  print -u2 "${FFMPEG_PATH} is not a ${TARGET_ARCH} executable."
  exit 1
fi

if [[ "${PARAKEET_INCREMENTAL_BUILD:-0}" == "1" ]]; then
  rm -rf \
    "${STAGING_DIR}" \
    "${BUILD_DIR}/package-test" \
    "${APP_PATH}" \
    "${DMG_PATH}"
  CLEAN_ARG=()
else
  rm -rf \
    "${BUILD_DIR}" \
    "${APP_PATH}" \
    "${DIST_DIR}/${APP_NAME}" \
    "${DMG_PATH}"
  CLEAN_ARG=(--clean)
fi
mkdir -p "${STAGING_DIR}" "${DIST_DIR}"

PARAKEET_TARGET_ARCH="${TARGET_ARCH}" "${ARCH_RUN[@]}" "${VENV_DIR}/bin/pyinstaller" \
  --noconfirm \
  "${CLEAN_ARG[@]}" \
  --distpath "${DIST_DIR}" \
  --workpath "${BUILD_DIR}/pyinstaller" \
  "Parakeet-SRT-Creator.spec"

codesign --force --deep --sign - "${APP_PATH}"
codesign --verify --deep --strict "${APP_PATH}"

# COLLECT and the binary-processing cache duplicate most of the finished app.
# They are no longer needed once BUNDLE and code signing have succeeded.
rm -rf "${DIST_DIR}/${APP_NAME}" "${BUILD_DIR}/pyinstaller" "${PROJECT_DIR}/.pyinstaller"

TEST_DIR="${BUILD_DIR}/package-test"
TEST_AUDIO="${TEST_DIR}/speech.aiff"
TEST_RESULT="${TEST_DIR}/result.json"
mkdir -p "${TEST_DIR}"
if [[ -n "${PARAKEET_TEST_AUDIO:-}" ]]; then
  if [[ ! -s "${PARAKEET_TEST_AUDIO}" ]]; then
    print -u2 "PARAKEET_TEST_AUDIO does not point to a non-empty audio file."
    exit 1
  fi
  cp "${PARAKEET_TEST_AUDIO}" "${TEST_AUDIO}"
else
  /usr/bin/say \
    -v Samantha \
    -o "${TEST_AUDIO}" \
    "The quick brown fox jumps over the lazy dog."
fi
"${ARCH_RUN[@]}" "${APP_PATH}/Contents/MacOS/${APP_NAME}" \
  --worker-self-test \
  "${TEST_AUDIO}" \
  "${TEST_RESULT}"
"${ARCH_RUN[@]}" "${VENV_DIR}/bin/python" -c \
  'import json, sys; result=json.load(open(sys.argv[1])); assert result["segments"]; assert result["segments"][0]["end"] > result["segments"][0]["start"]' \
  "${TEST_RESULT}"

cp -R "${APP_PATH}" "${STAGING_DIR}/"
rm -rf "${APP_PATH}"
ln -s /Applications "${STAGING_DIR}/Applications"
cp "README.md" "${STAGING_DIR}/Read Me.md"
cp "THIRD_PARTY_NOTICES.md" "${STAGING_DIR}/Third-Party Notices.md"

hdiutil create \
  -volname "${APP_NAME}" \
  -srcfolder "${STAGING_DIR}" \
  -format UDZO \
  -imagekey zlib-level=9 \
  -ov \
  "${DMG_PATH}"

hdiutil verify "${DMG_PATH}"
rm -rf "${BUILD_DIR}" "${APP_PATH}" "${DIST_DIR}/${APP_NAME}"

print "Created ${DMG_PATH}"
