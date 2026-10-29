"""Small compatibility helpers for the final macOS Intel PyTorch release."""

import contextlib
import sys
import types


def install_torch_attention_namespace(torch):
    """Provide NeMo's optional torch.nn.attention import on PyTorch 2.2.

    NeMo 2.4 imports this PyTorch 2.3 namespace unconditionally, although the
    bundled model does not enable its SDPA backend-selection feature. The shim
    keeps that import working and maps the context manager to PyTorch 2.2's
    equivalent when it is available.
    """
    if hasattr(torch.nn, "attention"):
        return

    attention = types.ModuleType("torch.nn.attention")
    attention.SDPBackend = getattr(torch.backends.cuda, "SDPBackend", object)

    @contextlib.contextmanager
    def sdpa_kernel(_backends):
        yield

    attention.sdpa_kernel = sdpa_kernel
    torch.nn.attention = attention
    sys.modules[attention.__name__] = attention
