"""What PyInstaller freezes, instead of `hawkvance_engine/__main__.py` directly.

PyInstaller runs whatever script it is given as a standalone top-level module named `__main__`,
with no parent package. `hawkvance_engine/__main__.py` uses relative imports like
`from .engine import LocalEngine`, which need a parent package to resolve against, so a frozen
build launched that way fails immediately with "attempted relative import with no known parent
package" — every time, on every machine, since it is a property of how the build is put together
rather than of the machine it runs on.

Importing the package properly here, then calling into it, is what `python -m hawkvance_engine`
does under the hood in development, and it is what makes the same relative imports resolve in a
frozen build too.
"""

from __future__ import annotations

from hawkvance_engine.__main__ import main

if __name__ == "__main__":
    main()
