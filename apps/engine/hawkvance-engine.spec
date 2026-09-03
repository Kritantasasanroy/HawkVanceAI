# PyInstaller spec for the HawkVance local engine sidecar.
#
# Produces a single-folder distribution rather than a one-file bundle: one-file extracts to a temp
# directory on every launch, which for a ~400MB scientific stack means several seconds of start-up
# and a large temp footprint on exactly the low-spec machines this product targets.

from PyInstaller.utils.hooks import collect_all, collect_data_files

datas = []
binaries = []
hiddenimports = ["hawkvance_engine"]

# Packages that load resources by path at runtime, so their data files have to travel with them.
#
# docling_parse is here rather than in the lighter pass below because collecting only `docling`
# misses it: the PDF backend lives in that separate distribution, and it refuses to start without
# its `pdf_resources` tree of fonts, encodings, cmaps and glyphs. Left out, every PDF fails with
# "no existing pdf_resources_dir" while plain text files carry on working, so the gap only shows
# up on the format people are most likely to try first.
for package in (
    "presidio_analyzer",
    "presidio_anonymizer",
    "en_core_web_sm",
    "spacy",
    "thinc",
    "docling",
    "docling_parse",
    "docling_core",
    "docling_ibm_models",
):
    try:
        package_datas, package_binaries, package_imports = collect_all(package)
        datas += package_datas
        binaries += package_binaries
        hiddenimports += package_imports
    except Exception:
        # Optional components. A build without GLiNER or PaddleOCR still ships a working engine
        # that degrades to pattern detection, which is better than refusing to build.
        pass

for optional in ("gliner", "paddleocr", "onnxruntime", "tokenizers", "rapidocr"):
    try:
        datas += collect_data_files(optional)
        hiddenimports.append(optional)
    except Exception:
        pass

a = Analysis(
    # Not hawkvance_engine/__main__.py directly: PyInstaller runs whatever it is pointed at as a
    # standalone module with no parent package, which breaks every relative import inside the
    # package the moment the frozen exe is launched. entrypoint.py imports the package properly
    # first, which is what makes those imports resolve. See entrypoint.py for the full story.
    ["entrypoint.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "pytest", "IPython", "notebook"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="hawkvance-engine",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="hawkvance-engine",
)
