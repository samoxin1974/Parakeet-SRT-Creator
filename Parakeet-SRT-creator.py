import sys
import os
import ctypes
import inspect
import time
import json
import shutil
import subprocess
import tempfile
import multiprocessing
import platform

# PyInstaller multiprocessing children re-run the application executable.
# Handle their special command line before importing NeMo or creating Qt
# windows, otherwise a worker can accidentally open another main window.
if __name__ == "__main__":
    multiprocessing.freeze_support()

# NeMo supports Apple Silicon through MPS, but some PyTorch operations still
# need to fall back to the CPU. This must be set before importing PyTorch.
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
RESOURCE_DIR = getattr(sys, "_MEIPASS", PROJECT_DIR)
if getattr(sys, "frozen", False):
    CACHE_DIR = os.path.join(
        os.path.expanduser("~/Library/Caches"),
        "Parakeet SRT Creator",
    )
else:
    CACHE_DIR = os.path.join(PROJECT_DIR, ".cache")
os.environ.setdefault("HF_HOME", os.path.join(CACHE_DIR, "huggingface"))
os.environ.setdefault("MPLCONFIGDIR", os.path.join(CACHE_DIR, "matplotlib"))
os.environ.setdefault("XDG_CACHE_HOME", CACHE_DIR)

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QCheckBox, QFileDialog, QTextEdit, QMessageBox
)
from PyQt5.QtCore import QCoreApplication, QThread, pyqtSignal
from PyQt5.QtGui import QIcon


MODEL_NAME = "nvidia/parakeet-tdt-0.6b-v2"
MODEL_FILENAME = "parakeet-tdt-0.6b-v2.nemo"
_PARAKEET_MODEL = None
_PARAKEET_DEVICE = None


def resource_path(*parts):
    """Return a path to a source or PyInstaller-bundled resource."""
    return os.path.join(RESOURCE_DIR, *parts)

# ── Crockford Base32 ULID generator (no extra dependencies) ──────────

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def generate_ulid():
    """Return a 26-char Crockford-Base32 ULID (timestamp + random)."""
    ts_ms = int(time.time() * 1000)
    # 10-char timestamp (48-bit ms)
    t_chars = []
    for _ in range(10):
        t_chars.append(_CROCKFORD[ts_ms & 0x1F])
        ts_ms >>= 5
    t_chars.reverse()
    # 16-char randomness (80-bit)
    rand_bytes = os.urandom(10)
    rand_val = int.from_bytes(rand_bytes, "big")
    r_chars = []
    for _ in range(16):
        r_chars.append(_CROCKFORD[rand_val & 0x1F])
        rand_val >>= 5
    r_chars.reverse()
    return "".join(t_chars) + "".join(r_chars)


# ── Tokenizer — splits phrase text into text / punct ranges ──────────

def tokenize_text(value, monologue, element_counter):
    """
    Walk *value* character-by-character and produce a list of range dicts
    matching the JSON schema.  Returns (ranges_list, next_element_counter).

    Rules (derived from the reference JSON):
      • A "text" token is a run of letters, digits, mid-word apostrophes
        (e.g. I'm, don't) and mid-word hyphens (e.g. right-click, read-only).
      • Every other single character becomes its own "punct" token
        (spaces, commas, periods, colons, semicolons, …).
    """
    ranges = []
    i = 0
    n = len(value)

    while i < n:
        ch = value[i]

        if ch.isalnum():
            # Start of a word
            start = i
            i += 1
            while i < n:
                c = value[i]
                if c.isalnum():
                    i += 1
                elif c in ("'", "\u2019") and i + 1 < n and value[i + 1].isalnum():
                    # mid-word apostrophe  (I'm, don't)
                    i += 2
                elif c == "-" and i + 1 < n and value[i + 1].isalnum():
                    # mid-word hyphen  (right-click, read-only)
                    i += 2
                else:
                    break
            ranges.append({
                "type": "text",
                "start": start,
                "length": i - start,
                "source": {
                    "monologue": monologue,
                    "element": element_counter,
                    "elementId": generate_ulid(),
                },
            })
            element_counter += 1
        else:
            # Single punct / whitespace character
            ranges.append({
                "type": "punct",
                "start": i,
                "length": 1,
                "source": {
                    "monologue": monologue,
                    "element": element_counter,
                    "elementId": generate_ulid(),
                },
            })
            element_counter += 1
            i += 1

    return ranges, element_counter


# ── JSON export (matches reference schema) ───────────────────────────

def segments_to_json(segments, schema_version="1.1.3"):
    """
    Convert timestamped transcription segments into the JSON format:
      { "phrases": [ { ts, value, ranges }, … ], "schemaVersion": "…" }
    """
    phrases = []
    monologue = 0
    element_counter = 0

    for seg in segments:
        text = seg["text"].strip()
        ts = round(seg["start"], 3)

        ranges, element_counter = tokenize_text(text, monologue, element_counter)
        # skip one element between phrases (matches reference file behaviour)
        element_counter += 1

        phrases.append({
            "ts": ts,
            "value": text,
            "ranges": ranges,
        })

    return json.dumps(
        {"phrases": phrases, "schemaVersion": schema_version},
        ensure_ascii=False,
    )


# ── SRT / VTT helpers (unchanged) ───────────────────────────────────

def format_timestamp_srt(seconds):
    ms = int((seconds % 1) * 1000)
    s = int(seconds) % 60
    m = (int(seconds) // 60) % 60
    h = int(seconds) // 3600
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def format_timestamp_vtt(seconds):
    ms = int((seconds % 1) * 1000)
    s = int(seconds) % 60
    m = (int(seconds) // 60) % 60
    h = int(seconds) // 3600
    return f"{h:02}:{m:02}:{s:02}.{ms:03}"


def segments_to_srt(segments):
    lines = []
    for i, seg in enumerate(segments, 1):
        lines.append(str(i))
        lines.append(f"{format_timestamp_srt(seg['start'])} --> {format_timestamp_srt(seg['end'])}")
        lines.append(seg['text'].strip())
        lines.append("")
    return "\n".join(lines)


def segments_to_vtt(segments):
    lines = ["WEBVTT", ""]
    for seg in segments:
        lines.append(f"{format_timestamp_vtt(seg['start'])} --> {format_timestamp_vtt(seg['end'])}")
        lines.append(seg['text'].strip())
        lines.append("")
    return "\n".join(lines)


# ── Parakeet helpers / worker thread ─────────────────────────────────

def load_parakeet_model():
    """Load and cache the Parakeet model, choosing the best available device."""
    global _PARAKEET_MODEL, _PARAKEET_DEVICE

    if _PARAKEET_MODEL is not None:
        return _PARAKEET_MODEL, _PARAKEET_DEVICE

    try:
        import torch
        from torch_compat import install_torch_attention_namespace

        install_torch_attention_namespace(torch)
        import nemo.collections.asr as nemo_asr
    except ImportError as exc:
        if getattr(sys, "frozen", False):
            raise RuntimeError(
                f"The packaged transcription runtime could not load: {exc}"
            ) from exc
        raise RuntimeError(
            "Parakeet dependencies are not installed. Activate the project "
            "virtual environment and run: pip install -r requirements.txt"
        ) from exc

    if torch.cuda.is_available():
        device = torch.device("cuda")
    # MPS is an Apple Silicon backend. On newer Intel macOS releases,
    # is_available() can report true in a frozen x86_64 process even though
    # this Intel PyTorch build cannot execute/autocast MPS operations.
    elif platform.machine() == "arm64" and torch.backends.mps.is_available():
        device = torch.device("mps")
    else:
        device = torch.device("cpu")

    bundled_model = resource_path("models", MODEL_FILENAME)
    if os.path.isfile(bundled_model):
        model = nemo_asr.models.ASRModel.restore_from(bundled_model)
    else:
        model = nemo_asr.models.ASRModel.from_pretrained(MODEL_NAME)
    model = model.to(device)
    model.eval()

    _PARAKEET_MODEL = model
    _PARAKEET_DEVICE = str(device)
    return _PARAKEET_MODEL, _PARAKEET_DEVICE


def normalize_media(file_path, output_path):
    """Convert any supported media input to the 16 kHz mono WAV NeMo expects."""
    bundled_candidates = (
        resource_path("bin", "ffmpeg"),
        resource_path("bin", "ffmpeg-x86_64"),
        resource_path("bin", "ffmpeg-arm64"),
    )
    ffmpeg = next((path for path in bundled_candidates if os.path.isfile(path)), None)
    if not ffmpeg:
        ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError(
            "FFmpeg is required to read audio and video files, but it was not "
            "found on PATH."
        )

    process = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            file_path,
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            output_path,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if process.returncode != 0:
        detail = process.stderr.strip() or "Unknown FFmpeg error"
        raise RuntimeError(f"Could not prepare the media file:\n{detail}")


def hypothesis_to_segments(hypothesis):
    """Convert a NeMo hypothesis into the segment shape used by the exporters."""
    timestamps = getattr(hypothesis, "timestamp", None) or {}
    timestamp_segments = timestamps.get("segment") or []
    segments = []

    for item in timestamp_segments:
        text = str(item.get("segment", item.get("text", ""))).strip()
        if not text:
            continue
        segments.append({
            "start": float(item["start"]),
            "end": float(item["end"]),
            "text": text,
        })

    if segments:
        return segments

    # A defensive fallback for NeMo versions/configurations that only return
    # word timestamps. Group words into subtitle-sized chunks.
    words = timestamps.get("word") or []
    current = []
    for item in words:
        word = str(item.get("word", "")).strip()
        if not word:
            continue
        current.append(item)
        duration = float(item["end"]) - float(current[0]["start"])
        if len(current) >= 12 or duration >= 6 or word.endswith((".", "?", "!")):
            segments.append({
                "start": float(current[0]["start"]),
                "end": float(current[-1]["end"]),
                "text": " ".join(str(word_item["word"]).strip() for word_item in current),
            })
            current = []

    if current:
        segments.append({
            "start": float(current[0]["start"]),
            "end": float(current[-1]["end"]),
            "text": " ".join(str(word_item["word"]).strip() for word_item in current),
        })

    if not segments:
        text = str(getattr(hypothesis, "text", hypothesis)).strip()
        if text:
            raise RuntimeError(
                "Parakeet returned text without timestamps, so subtitle timing "
                "could not be generated."
            )
        raise RuntimeError("Parakeet did not return a transcription.")

    return segments


def transcribe_with_timestamps(model, wav_path):
    """Transcribe with the call shape supported by the installed NeMo."""
    kwargs = {
        "batch_size": 1,
        "num_workers": 0,
        "timestamps": True,
    }
    if "use_lhotse" in inspect.signature(model.transcribe).parameters:
        kwargs["use_lhotse"] = False
    return model.transcribe([wav_path], **kwargs)

class TranscribeWorker(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, file_path):
        super().__init__()
        self.file_path = file_path
        # Qt's default secondary-thread stack on macOS is too small for the
        # deeply nested native PyTorch/NeMo CPU inference path. A stack
        # overflow otherwise appears as EXC_BAD_ACCESS beside the thread's
        # Stack Guard instead of a catchable Python exception.
        self.setStackSize(64 * 1024 * 1024)

    def run(self):
        try:
            with tempfile.TemporaryDirectory(prefix="parakeet-srt-") as temp_dir:
                wav_path = os.path.join(temp_dir, "audio.wav")
                self.progress.emit("Preparing 16 kHz mono audio...")
                normalize_media(self.file_path, wav_path)

                if _PARAKEET_MODEL is None:
                    self.progress.emit("Loading the bundled Parakeet model...")
                else:
                    self.progress.emit("Reusing the loaded Parakeet model...")
                model, device = load_parakeet_model()
                self.progress.emit(f"Transcribing English audio on {device}...")
                hypotheses = transcribe_with_timestamps(model, wav_path)
                if not hypotheses:
                    raise RuntimeError("Parakeet did not return a transcription.")
                self.finished.emit(hypothesis_to_segments(hypotheses[0]))
        except Exception as e:
            self.error.emit(str(e))


def run_packaged_self_test(input_path, result_path):
    """Run a real transcription for build-time validation of the frozen app."""
    with tempfile.TemporaryDirectory(prefix="parakeet-self-test-") as temp_dir:
        wav_path = os.path.join(temp_dir, "audio.wav")
        normalize_media(input_path, wav_path)
        model, device = load_parakeet_model()
        hypotheses = transcribe_with_timestamps(model, wav_path)
        if not hypotheses:
            raise RuntimeError("Parakeet did not return a self-test transcription.")
        segments = hypothesis_to_segments(hypotheses[0])
        with open(result_path, "w", encoding="utf-8") as result_file:
            json.dump(
                {
                    "device": device,
                    "text": hypotheses[0].text,
                    "segments": segments,
                },
                result_file,
                ensure_ascii=False,
            )


def run_packaged_worker_self_test(input_path, result_path):
    """Validate transcription on the same QThread path used by the GUI."""
    app = QCoreApplication.instance() or QCoreApplication([])
    state = {}
    worker = TranscribeWorker(input_path)

    def handle_finished(segments):
        state["segments"] = segments
        app.quit()

    def handle_error(message):
        state["error"] = message
        app.quit()

    worker.finished.connect(handle_finished)
    worker.error.connect(handle_error)
    worker.start()
    app.exec()
    worker.wait()

    if "error" in state:
        raise RuntimeError(state["error"])
    segments = state.get("segments") or []
    if not segments:
        raise RuntimeError("The worker self-test returned no timestamped segments.")
    with open(result_path, "w", encoding="utf-8") as result_file:
        json.dump(
            {"device": _PARAKEET_DEVICE, "segments": segments},
            result_file,
            ensure_ascii=False,
        )


# ── Main window ──────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Parakeet Subtitle Generator")
        self.setMinimumWidth(600)
        self.file_path = None
        self.worker = None

        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # File selector
        file_row = QHBoxLayout()
        self.file_label = QLabel("No file selected")
        self.file_label.setWordWrap(True)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self.browse_file)
        file_row.addWidget(self.file_label, 1)
        file_row.addWidget(browse_btn)
        layout.addLayout(file_row)

        # Model information
        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("Model:"))
        model_row.addWidget(QLabel(MODEL_NAME))
        model_row.addStretch()
        layout.addLayout(model_row)

        # This Parakeet checkpoint is English-only.
        lang_row = QHBoxLayout()
        lang_row.addWidget(QLabel("Language:"))
        lang_row.addWidget(QLabel("English (this model is English-only)"))
        lang_row.addStretch()
        layout.addLayout(lang_row)

        # Output format checkboxes  ← .json added here
        fmt_row = QHBoxLayout()
        fmt_row.addWidget(QLabel("Output format:"))
        self.srt_check = QCheckBox(".srt")
        self.srt_check.setChecked(True)
        self.vtt_check = QCheckBox(".vtt")
        self.json_check = QCheckBox(".json")
        fmt_row.addWidget(self.srt_check)
        fmt_row.addWidget(self.vtt_check)
        fmt_row.addWidget(self.json_check)
        fmt_row.addStretch()
        layout.addLayout(fmt_row)

        # Output folder
        out_row = QHBoxLayout()
        self.out_label = QLabel("Output: same folder as input file")
        out_btn = QPushButton("Change...")
        out_btn.clicked.connect(self.browse_output)
        out_row.addWidget(self.out_label, 1)
        out_row.addWidget(out_btn)
        layout.addLayout(out_row)
        self.output_dir = None

        # Generate button
        self.generate_btn = QPushButton("Generate")
        self.generate_btn.setFixedHeight(40)
        self.generate_btn.clicked.connect(self.generate)
        layout.addWidget(self.generate_btn)

        # Status log
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFixedHeight(120)
        layout.addWidget(self.log)

    def browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select audio or video file", "",
            "Media files (*.mp3 *.wav *.m4a *.ogg *.flac *.mp4 *.mkv *.mov *.avi *.webm *.ts);;All files (*)"
        )
        if path:
            self.file_path = path
            self.file_label.setText(path)
            self.log.clear()

    def browse_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Select output folder")
        if folder:
            self.output_dir = folder
            self.out_label.setText(f"Output: {folder}")

    def log_msg(self, msg):
        self.log.append(msg)

    def generate(self):
        if not self.file_path:
            QMessageBox.warning(self, "No file", "Please select an audio or video file first.")
            return
        if (
            not self.srt_check.isChecked()
            and not self.vtt_check.isChecked()
            and not self.json_check.isChecked()
        ):
            QMessageBox.warning(self, "No format", "Please select at least one output format.")
            return

        self.generate_btn.setEnabled(False)
        self.log.clear()
        self.log_msg(f"File: {self.file_path}")
        self.log_msg(f"Model: {MODEL_NAME} | Language: English")

        self.worker = TranscribeWorker(self.file_path)
        self.worker.progress.connect(self.log_msg)
        self.worker.finished.connect(self.on_finished)
        self.worker.error.connect(self.on_error)
        self.worker.start()

    def on_finished(self, segments):
        out_dir = self.output_dir or os.path.dirname(self.file_path)
        base_name = os.path.splitext(os.path.basename(self.file_path))[0]
        out_base = os.path.join(out_dir, base_name)

        if self.srt_check.isChecked():
            path = out_base + ".srt"
            with open(path, "w", encoding="utf-8") as f:
                f.write(segments_to_srt(segments))
            self.log_msg(f"Saved: {path}")

        if self.vtt_check.isChecked():
            path = out_base + ".vtt"
            with open(path, "w", encoding="utf-8") as f:
                f.write(segments_to_vtt(segments))
            self.log_msg(f"Saved: {path}")

        if self.json_check.isChecked():
            path = out_base + ".json"
            with open(path, "w", encoding="utf-8") as f:
                f.write(segments_to_json(segments))
            self.log_msg(f"Saved: {path}")

        self.log_msg("Done!")
        self.generate_btn.setEnabled(True)

    def on_error(self, msg):
        self.log_msg(f"ERROR: {msg}")
        self.generate_btn.setEnabled(True)


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--self-test":
        run_packaged_self_test(sys.argv[2], sys.argv[3])
        sys.exit(0)
    if len(sys.argv) == 4 and sys.argv[1] == "--worker-self-test":
        run_packaged_worker_self_test(sys.argv[2], sys.argv[3])
        sys.exit(0)

    # Windows: set AppUserModelID so the taskbar uses our icon instead of Python's
    if sys.platform == "win32":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "whisper.subtitle.generator"
        )

    app = QApplication(sys.argv)

    # Set the icon on the application (affects taskbar + all windows)
    icon_path = resource_path("icon.png")
    app.setWindowIcon(QIcon(icon_path))

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
