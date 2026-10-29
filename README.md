# Parakeet SRT Creator

A desktop app that turns English audio and video into **SRT subtitles, WebVTT captions, or timestamped JSON**, using NVIDIA's Parakeet TDT 0.6B v2 model locally on your computer.

## Download and install on macOS

Get the Apple Silicon build from [Releases](https://github.com/samoxin1974/Parakeet-SRT-Creator/releases/latest). The app includes the model, Python runtime, dependencies, and FFmpeg, so transcription works offline after installation.

GitHub limits each release asset to under 2 GiB. The installer is provided in two parts:

1. Download both `Parakeet-SRT-Creator-Apple-Silicon.dmg.part*` files, `SHA256SUMS`, and `Restore-Installer.command` into the same folder.
2. Open Terminal, change to that folder, and run `bash Restore-Installer.command`. The script checks the downloads, joins them into a DMG, verifies the complete file, and opens it on macOS.
3. Drag **Parakeet SRT Creator** into **Applications**.

With the GitHub CLI:

```bash
gh release download v1.0.0 --repo samoxin1974/Parakeet-SRT-Creator \
  --pattern 'Parakeet-SRT-Creator-Apple-Silicon.dmg.part*' \
  --pattern 'SHA256SUMS' --pattern 'Restore-Installer.command'
bash Restore-Installer.command
```

This build targets Apple Silicon Macs with macOS 14 or newer. It is ad-hoc signed, but is not Developer ID signed or notarized. If macOS blocks the app, use **System Settings → Privacy & Security → Open Anyway** for an app you trust.

The released bundle passed code-signature verification and a real transcription test through the app's worker thread. The test returned the expected sentence with timestamps on CPU. The DMG passed `hdiutil verify`.

## Use the app

1. Select an audio or video file with **Browse…**.
2. Select `.srt`, `.vtt`, `.json`, or a combination of formats.
3. Choose the output folder and click **Generate**.

The model supports **English only**. Transcription runs locally. Apple Silicon selects PyTorch MPS when available, with CPU fallback for unsupported operations. CUDA is selected on supported NVIDIA systems; other systems use CPU.

## Run from source

Use Python 3.12 and FFmpeg. On macOS, FFmpeg can be installed with `brew install ffmpeg`.

```bash
git clone https://github.com/samoxin1974/Parakeet-SRT-Creator.git
cd Parakeet-SRT-Creator
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python Parakeet-SRT-creator.py
```

The first source-run transcription downloads the approximately 2.5 GB [NVIDIA model](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v2) into `.cache/huggingface`; subsequent runs reuse it. Allow additional disk space for dependencies and temporary audio.

`requirements-apple-silicon.lock.txt` records the package versions used for the tested Apple Silicon build. To reproduce that environment, install it instead of `requirements.txt`.

## Build a self-contained Apple Silicon DMG

The `vendor` folder needs the model and architecture-specific FFmpeg executables. These large files are provided as a separate archive in the release.

From the repository root:

```bash
gh release download v1.0.0 --repo samoxin1974/Parakeet-SRT-Creator \
  --pattern 'Parakeet-SRT-Creator-vendor.tar.part*' \
  --pattern 'SHA256SUMS' --pattern 'Restore-Vendor.command'
bash Restore-Vendor.command
source .venv/bin/activate
python -m pip install pyinstaller
Scripts/build_dmg.sh
```

The build signs the app, transcribes a short generated speech sample through its worker thread, creates the DMG, and verifies the disk image. Output: `dist/Parakeet-SRT-Creator-Apple-Silicon.dmg`.

To use your own speech sample for build validation:

```bash
PARAKEET_TEST_AUDIO=/absolute/path/to/speech.wav Scripts/build_dmg.sh
```

## Intel build support

An Intel build script and dependency list are included; an Intel installer is not included in this release. Build on macOS with Rosetta and a universal Python 3.12 installation:

```bash
arch -x86_64 /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 \
  -m venv .venv-intel
arch -x86_64 .venv-intel/bin/python -m pip install -r requirements-intel.txt
arch -x86_64 .venv-intel/bin/python -m pip install pyinstaller
PARAKEET_TARGET_ARCH=x86_64 Scripts/build_dmg.sh
```

Intel uses separate x86_64 dependencies and FFmpeg, and transcribes on CPU. The Intel build targets macOS 13 or newer.

## Project files

| Path | Purpose |
| --- | --- |
| `Parakeet-SRT-creator.py` | PyQt5 interface, transcription worker, and subtitle exporters |
| `torch_compat.py` | Compatibility helper for Intel PyTorch |
| `Parakeet-SRT-Creator.spec` | PyInstaller bundle configuration |
| `Scripts/build_dmg.sh` | Build, sign, test, and package the macOS app |
| `Scripts/restore_release.sh` | Verify and restore split release downloads |
| `requirements*.txt` | Source, Intel, and tested Apple Silicon dependencies |
| `vendor/` | Documentation for the large model and FFmpeg release assets |
| `icon.png` | Application icon |
| Root `*.srt`, `*.vtt`, `*.json` files | Existing transcription output examples |

Local virtual environments, caches, bytecode, and temporary build output are excluded from Git. The release contains the built installer and complete vendor binaries and model. GitHub also provides a source archive for each release.

## Third-party software

The model is NVIDIA Parakeet TDT 0.6B v2, distributed under CC BY 4.0. FFmpeg and the Python dependencies retain their respective licenses. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and the upstream projects for details.
