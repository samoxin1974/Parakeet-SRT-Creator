# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from pathlib import Path

project_dir = Path(SPECPATH)
sys.path.insert(0, str(project_dir))

import torch
from torch_compat import install_torch_attention_namespace

install_torch_attention_namespace(torch)


def collect_python_modules(package_name, package_dir):
    """Collect modules without importing each package in an isolated process."""
    modules = {package_name}
    for source_path in package_dir.rglob("*.py"):
        relative = source_path.relative_to(package_dir)
        parts = list(relative.with_suffix("").parts)
        if parts[-1] == "__init__":
            parts.pop()
        if parts:
            modules.add(package_name + "." + ".".join(parts))
    return sorted(modules)

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_submodules,
    copy_metadata,
)


model_path = (
    project_dir
    / "vendor"
    / "parakeet-tdt-0.6b-v2.nemo"
)
target_arch = os.environ.get("PARAKEET_TARGET_ARCH", "arm64")
ffmpeg_path = project_dir / "vendor" / f"ffmpeg-{target_arch}"
if target_arch == "arm64" and not ffmpeg_path.exists():
    # Preserve compatibility with the original Apple Silicon checkout.
    ffmpeg_path = project_dir / "vendor" / "ffmpeg"

datas = [
    (str(project_dir / "icon.png"), "."),
    (str(model_path), "models"),
    (str(project_dir / "THIRD_PARTY_NOTICES.md"), "."),
]
# TorchScript compiles several NeMo helper functions during import and needs
# their original source, not only PyInstaller's archived bytecode.
datas += collect_data_files("nemo", include_py_files=True)
datas += collect_data_files("lhotse")
datas += collect_data_files("librosa", include_py_files=True)
datas += collect_data_files("lightning")
datas += collect_data_files("lightning_fabric")
datas += collect_data_files("pytorch_lightning")
datas += copy_metadata("nemo_toolkit")
datas += copy_metadata("huggingface_hub")
datas += copy_metadata("lightning")
datas += copy_metadata("torch")
datas += copy_metadata("torchaudio")
datas += copy_metadata("transformers")

hiddenimports = []
hiddenimports += collect_python_modules(
    "nemo.collections.asr",
    Path(torch.__file__).parent.parent / "nemo" / "collections" / "asr",
)
hiddenimports += collect_submodules("nemo.core")
hiddenimports += collect_submodules("nemo.utils")
hiddenimports += collect_submodules("lhotse")

a = Analysis(
    ["Parakeet-SRT-creator.py"],
    pathex=[str(project_dir)],
    binaries=[(str(ffmpeg_path), "bin")],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "jupyter",
        "matplotlib.tests",
        "pandas.tests",
        "pyarrow.tests",
        "scipy.tests",
        "sklearn.tests",
    ],
    # Librosa uses Numba decorators with cache=True. Keeping these modules on
    # disk gives Numba a real source-file locator inside the frozen app.
    module_collection_mode={"librosa": "py"},
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Parakeet SRT Creator",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    argv_emulation=False,
    target_arch=target_arch,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Parakeet SRT Creator",
)

app = BUNDLE(
    coll,
    name="Parakeet SRT Creator.app",
    icon="icon.png",
    bundle_identifier="com.local.parakeetsrtcreator",
    version="1.0.0",
    info_plist={
        "CFBundleDisplayName": "Parakeet SRT Creator",
        "CFBundleName": "Parakeet SRT Creator",
        "LSMinimumSystemVersion": "13.0",
        "NSHighResolutionCapable": True,
    },
)
