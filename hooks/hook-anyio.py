"""Custom PyInstaller hook for anyio.

Phase 4.4 (2026-09-05): anyio 4.x uses ``_lazyimport`` to make
submodules appear on attribute access, not on package import.
PyInstaller's static analysis can't follow this — listing them in
``hiddenimports`` (e.g. ``"anyio.abc"``) triggers the analyzer to try
``import anyio.abc``, which works in regular Python but PyInstaller
can't resolve the lazy proxy, so the module is NOT added to the
bundle. The fix is to walk the package directory directly and emit
one hiddenimport per .py file. PyInstaller then bundles each one
because the file actually exists on disk.

The hook is referenced from ``omniscribe_server.spec`` via
``hookspath``. PyInstaller's hook system reads the module-level
``hiddenimports`` and merges it into the Analysis.
"""

import os

from PyInstaller.utils.hooks import get_package_paths

# ``get_package_paths`` returns (package_dir, package_namespace) for
# the installed distribution. We walk the directory tree and emit
# one hiddenimport per .py file (with the right module name).
pkg_dir, _ = get_package_paths("anyio")
hiddenimports = []
for root, dirs, files in os.walk(pkg_dir):
    # Sort for deterministic build output.
    dirs.sort()
    files.sort()
    for f in files:
        if not f.endswith(".py"):
            continue
        rel = os.path.relpath(os.path.join(root, f), pkg_dir)
        # Convert "abc/__init__.py" -> "anyio.abc", "abc/socket.py" -> "anyio.abc.socket"
        rel_no_ext = rel.removesuffix(".py").removesuffix(os.sep + "__init__")
        if not rel_no_ext:
            hiddenimports.append("anyio")
        else:
            hiddenimports.append("anyio." + rel_no_ext.replace(os.sep, "."))
