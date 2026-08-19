"""Headless import of the original REDSEA toolkit (verbatim file).

Installs Tk/CTk stubs BEFORE importing redsea_toolkit so the desktop file is
importable on a server without a display server. The worker calls only the
pure (non-GUI) helpers from redsea_toolkit:

    covering, TcmIndexer, TASK_PATTERN, MPD_PATTERN, CHECK_RELATIONS,
    expand_check, build_check_regexes, page_to_image, ocr_page_text,
    group_contiguous, walk_pdfs_in_dir, is_pdf, safe_make_dir, unique_path

These functions are exactly the ones the user requested be preserved
unchanged.
"""
from . import tk_stub
tk_stub.install()

# noqa: E402 — import order is intentional
from . import redsea_toolkit as rt  # type: ignore  # noqa: E402

# Re-export the toolkit primitives we use in handlers.
covering = rt.covering
TcmIndexer = rt.TcmIndexer
TASK_PATTERN = rt.TASK_PATTERN
MPD_PATTERN = rt.MPD_PATTERN
CHECK_RELATIONS = rt.CHECK_RELATIONS
expand_check = rt.expand_check
build_check_regexes = rt.build_check_regexes
page_to_image = rt.page_to_image
ocr_page_text = rt.ocr_page_text
group_contiguous = rt.group_contiguous
walk_pdfs_in_dir = rt.walk_pdfs_in_dir
is_pdf = rt.is_pdf
safe_make_dir = rt.safe_make_dir
unique_path = rt.unique_path


def normalize_check_code(value) -> str:
    """Expose App2's check-code normalizer as a plain function.

    ``RedseaApp._normalize_check_code`` (redsea_toolkit.py L3123) never touches
    ``self``, so it is called unbound. Transcribing its transformation table
    here instead would create a second copy of a business rule that must not
    diverge -- exactly the drift pattern that produced the Heavy divergence.
    """

    return rt.RedseaApp._normalize_check_code(None, value)


__all__ = [
    "covering", "TcmIndexer", "TASK_PATTERN", "MPD_PATTERN", "CHECK_RELATIONS",
    "expand_check", "build_check_regexes", "page_to_image", "ocr_page_text",
    "group_contiguous", "walk_pdfs_in_dir", "is_pdf", "safe_make_dir",
    "unique_path", "normalize_check_code",
]
