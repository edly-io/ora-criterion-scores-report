"""
Test bootstrap.

The pipeline module imports ``xmodule.modulestore.django``, which only exists
inside edx-platform. When it's absent (running the suite standalone), install a
minimal stub so the pipeline module imports and its logic can be exercised with
monkeypatched dependencies. In the platform test environment the real module is
present and this stub is never used.
"""

import sys
import types


def _install_xmodule_stub():
    try:
        import xmodule.modulestore.django  # noqa: F401  pylint: disable=unused-import
        return
    except Exception:  # pylint: disable=broad-except
        pass

    xmodule = sys.modules.setdefault("xmodule", types.ModuleType("xmodule"))
    modulestore_pkg = sys.modules.setdefault(
        "xmodule.modulestore", types.ModuleType("xmodule.modulestore")
    )
    django_mod = types.ModuleType("xmodule.modulestore.django")
    django_mod.modulestore = lambda: None  # overridden per-test via monkeypatch
    sys.modules["xmodule.modulestore.django"] = django_mod
    modulestore_pkg.django = django_mod
    xmodule.modulestore = modulestore_pkg


_install_xmodule_stub()
