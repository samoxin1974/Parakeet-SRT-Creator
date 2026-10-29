# Bundled assets

Large runtime assets are available in the [v1.0.0 release](https://github.com/samoxin1974/Parakeet-SRT-Creator/releases/tag/v1.0.0):

- `ffmpeg`: Apple Silicon executable.
- `ffmpeg-x86_64`: Intel executable.
- `parakeet-tdt-0.6b-v2.nemo`: NVIDIA's English Parakeet TDT 0.6B v2 model.

Download all `Parakeet-SRT-Creator-vendor.tar.part*` files, `SHA256SUMS`, and `Restore-Vendor.command` into the repository root. Run:

```bash
bash Restore-Vendor.command
```

The script verifies the parts and complete archive before extracting these three files into `vendor/`. See the repository README and third-party notices for setup and attribution.
