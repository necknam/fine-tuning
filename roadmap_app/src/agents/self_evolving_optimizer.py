"""Compatibility entrypoint. Implementation: src.roadmap.agents.self_evolving_optimizer."""
import importlib as _importlib
import sys as _sys
from pathlib import Path as _Path
if __package__ in (None, ""):
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
if __name__ == "__main__":
    _module = _importlib.import_module("src.roadmap.agents.self_evolving_optimizer")
    if not hasattr(_module, "main"):
        raise SystemExit("This module is an import compatibility entrypoint; use the documented CLI.")
    raise SystemExit(_module.main())
else:
    _sys.modules[__name__] = _importlib.import_module("src.roadmap.agents.self_evolving_optimizer")
