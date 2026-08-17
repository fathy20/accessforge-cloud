"""Governed local storage helpers for upload and output artifacts."""

from __future__ import annotations

import codecs
import hashlib
import logging
import mimetypes
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path, PureWindowsPath
from typing import Any
from urllib.parse import unquote


logger = logging.getLogger(__name__)


def _storage_root() -> Path:
    """Anchor artifact storage to a stable location, never the process cwd.

    A cwd-relative root means a server started from any other directory
    silently orphans every artifact recorded in the database. Default is
    <project root>/local_storage — identical to the old behavior when the
    server was launched from the project root — overridable for deployments
    via ARTIFACT_STORAGE_DIR.
    """

    configured = os.getenv("ARTIFACT_STORAGE_DIR")
    if configured and configured.strip():
        return Path(configured.strip()).expanduser().resolve()
    return Path(__file__).resolve().parents[1] / "local_storage"


STORAGE_ROOT = _storage_root()
UPLOAD_DIR = STORAGE_ROOT / "uploads"
OUTPUT_DIR = STORAGE_ROOT / "outputs"
CHUNK_SIZE = 1024 * 1024
MAX_ORIGINAL_NAME_LENGTH = 512
_MAGIC_PREFIX_LENGTH = 16


class StorageError(RuntimeError):
    """Base class for governed storage failures."""


class PathSecurityError(StorageError):
    """Raised when a path is outside its configured storage root."""


class StorageConflictError(StorageError):
    """Raised when an artifact target already exists."""


class UploadTooLargeError(StorageError):
    """Raised as soon as a streamed upload crosses its size limit."""


class UnsupportedArtifactError(StorageError):
    """Raised when an upload's extension, MIME, or content is not allowed."""


@dataclass(frozen=True)
class ArtifactType:
    extension: str
    kind: str
    mime: str
    declared_mimes: frozenset[str]
    magic_prefixes: tuple[bytes, ...] = ()
    is_text: bool = False


@dataclass(frozen=True)
class StoredArtifact:
    path: Path
    storage_name: str
    original_name: str
    kind: str
    mime: str
    size_bytes: int
    sha256: str
    scan_state: str = "not_scanned"


_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_ZIP_MAGIC = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")
_ARTIFACT_TYPES: dict[str, ArtifactType] = {
    ".pdf": ArtifactType(
        ".pdf",
        "pdf",
        "application/pdf",
        frozenset({"application/pdf"}),
        (b"%PDF-",),
    ),
    ".xlsx": ArtifactType(
        ".xlsx",
        "excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        frozenset({"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}),
        _ZIP_MAGIC,
    ),
    ".xls": ArtifactType(
        ".xls",
        "excel",
        "application/vnd.ms-excel",
        frozenset({"application/vnd.ms-excel"}),
        (_OLE_MAGIC,),
    ),
    ".csv": ArtifactType(
        ".csv",
        "csv",
        "text/csv",
        frozenset({"text/csv", "application/csv", "text/plain"}),
        is_text=True,
    ),
    ".docx": ArtifactType(
        ".docx",
        "docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        frozenset({"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}),
        _ZIP_MAGIC,
    ),
    ".doc": ArtifactType(
        ".doc",
        "docx",
        "application/msword",
        frozenset({"application/msword"}),
        (_OLE_MAGIC,),
    ),
    ".png": ArtifactType(
        ".png",
        "image",
        "image/png",
        frozenset({"image/png"}),
        (b"\x89PNG\r\n\x1a\n",),
    ),
    ".jpg": ArtifactType(
        ".jpg",
        "image",
        "image/jpeg",
        frozenset({"image/jpeg"}),
        (b"\xff\xd8\xff",),
    ),
    ".jpeg": ArtifactType(
        ".jpeg",
        "image",
        "image/jpeg",
        frozenset({"image/jpeg"}),
        (b"\xff\xd8\xff",),
    ),
}


def _decoded_path_text(value: str | Path) -> str:
    decoded = str(value)
    for _ in range(2):
        next_value = unquote(decoded)
        if next_value == decoded:
            break
        decoded = next_value
    return decoded.replace("\\", "/")


def storage_basename(value: str | Path) -> str:
    """Return a URL/path basename without treating it as a filesystem target."""

    return Path(_decoded_path_text(value)).name


def resolve_contained_path(
    root: Path,
    candidate: str | Path,
    *,
    relative_to_root: bool = False,
) -> Path:
    """Resolve a candidate and require the configured root to contain it."""

    root_path = Path(root).resolve(strict=False)
    candidate_text = _decoded_path_text(candidate)
    candidate_path = Path(candidate_text)
    windows_absolute = PureWindowsPath(candidate_text).is_absolute()

    if relative_to_root and (candidate_path.is_absolute() or windows_absolute):
        raise PathSecurityError("Storage path must be relative to its root.")
    if not relative_to_root and windows_absolute and not candidate_path.is_absolute():
        raise PathSecurityError("Storage path is not contained by its root.")

    joined = root_path / candidate_path if relative_to_root else candidate_path
    resolved = joined.resolve(strict=False)
    try:
        resolved.relative_to(root_path)
    except ValueError as exc:
        raise PathSecurityError("Storage path is not contained by its root.") from exc
    if resolved == root_path:
        raise PathSecurityError("Storage root is not a file target.")
    return resolved


def existing_artifact_path(
    root: Path,
    candidate: str | Path,
    *,
    relative_to_root: bool = False,
) -> Path:
    """Resolve a contained path and verify it is a regular file."""

    resolved = resolve_contained_path(
        root,
        candidate,
        relative_to_root=relative_to_root,
    )
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    return resolved


def sanitize_original_name(filename: str | None) -> str:
    """Keep a bounded display name without directory or control characters."""

    basename = storage_basename(filename or "")
    sanitized = "".join(
        character
        for character in basename
        if ord(character) >= 0x20 and ord(character) != 0x7F
    )
    sanitized = sanitized.lstrip(".")[:MAX_ORIGINAL_NAME_LENGTH]
    return sanitized or "unnamed"


def _extension(filename: str | None) -> str:
    basename = storage_basename(filename or "")
    return Path(basename).suffix.casefold()


def validate_upload_type(
    filename: str | None,
    declared_mime: str | None,
) -> ArtifactType:
    """Validate the extension and claimed MIME before any file is written."""

    extension = _extension(filename)
    artifact_type = _ARTIFACT_TYPES.get(extension)
    if artifact_type is None:
        raise UnsupportedArtifactError("Unsupported file type.")

    normalized_mime = (declared_mime or "").split(";", 1)[0].strip().casefold()
    if normalized_mime not in artifact_type.declared_mimes:
        raise UnsupportedArtifactError("File extension and declared MIME do not agree.")
    return artifact_type


def _validate_magic(
    artifact_type: ArtifactType,
    first_bytes: bytes,
    *,
    text_valid: bool,
) -> None:
    if artifact_type.is_text:
        if not text_valid:
            raise UnsupportedArtifactError("CSV content is not valid UTF-8 text.")
        return
    if not any(first_bytes.startswith(prefix) for prefix in artifact_type.magic_prefixes):
        raise UnsupportedArtifactError("File content does not match its extension and MIME.")


def _classify_bytes(
    original_name: str,
    first_bytes: bytes,
    *,
    text_valid: bool = False,
) -> tuple[str, str]:
    """Return server-derived kind and MIME for an already-read artifact prefix."""

    artifact_type = _ARTIFACT_TYPES.get(_extension(original_name))
    if artifact_type is not None:
        if artifact_type.is_text and text_valid:
            return artifact_type.kind, artifact_type.mime
        if not artifact_type.is_text and any(
            first_bytes.startswith(prefix) for prefix in artifact_type.magic_prefixes
        ):
            return artifact_type.kind, artifact_type.mime

    guessed_mime, _ = mimetypes.guess_type(original_name)
    return "other", guessed_mime or "application/octet-stream"


def _new_storage_path(root: Path, extension: str) -> Path:
    Path(root).mkdir(parents=True, exist_ok=True)
    storage_name = f"{uuid.uuid4().hex}{extension}"
    return resolve_contained_path(root, storage_name, relative_to_root=True)


async def store_upload(
    stream: Any,
    root: Path,
    max_size: int,
) -> StoredArtifact:
    """Stream one upload to an exclusive target while enforcing size and hash."""

    artifact_type = validate_upload_type(
        getattr(stream, "filename", None),
        getattr(stream, "content_type", None),
    )
    original_name = sanitize_original_name(getattr(stream, "filename", None))
    target = _new_storage_path(root, artifact_type.extension)
    size = 0
    digest = hashlib.sha256()
    first_bytes = bytearray()
    text_decoder = (
        codecs.getincrementaldecoder("utf-8")("strict")
        if artifact_type.is_text
        else None
    )

    try:
        with target.open("xb") as destination:
            while True:
                chunk = await stream.read(CHUNK_SIZE)
                if not chunk:
                    break

                size += len(chunk)
                if size > max_size:
                    raise UploadTooLargeError(
                        f"Upload exceeds the maximum size of {max_size} bytes."
                    )

                if len(first_bytes) < _MAGIC_PREFIX_LENGTH:
                    first_bytes.extend(chunk[: _MAGIC_PREFIX_LENGTH - len(first_bytes)])
                digest.update(chunk)
                destination.write(chunk)
                if text_decoder is not None:
                    text_decoder.decode(chunk, final=False)

            if text_decoder is not None:
                text_decoder.decode(b"", final=True)
    except UnicodeDecodeError as exc:
        try:
            target.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            logger.exception("Could not remove an invalid CSV partial.")
        raise UnsupportedArtifactError("CSV content is not valid UTF-8 text.") from exc
    except FileExistsError as exc:
        raise StorageConflictError("Generated storage target already exists.") from exc
    except Exception:
        try:
            target.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            logger.exception("Could not remove a failed upload partial.")
        raise

    try:
        _validate_magic(artifact_type, bytes(first_bytes), text_valid=True)
    except Exception:
        try:
            target.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            logger.exception("Could not remove an invalid upload partial.")
        raise

    return StoredArtifact(
        path=target,
        storage_name=target.name,
        original_name=original_name,
        kind=artifact_type.kind,
        mime=artifact_type.mime,
        size_bytes=size,
        sha256=digest.hexdigest(),
    )


def scan_artifact(path: Path) -> str:
    """Quarantine seam: scanning is deliberately not implemented in this slice."""

    del path
    return "not_scanned"


def retention_expires_at(now: datetime | None = None) -> datetime | None:
    """Return the configured expiry, or None when retention is keep-forever."""

    configured = os.getenv("ARTIFACT_RETENTION_DAYS")
    if configured is None:
        configured = os.getenv("UPLOAD_RETENTION_DAYS")
    if configured is None or not configured.strip():
        return None

    try:
        days = int(configured)
    except ValueError:
        logger.warning("Ignoring invalid artifact retention period.")
        return None
    if days < 0:
        logger.warning("Ignoring negative artifact retention period.")
        return None

    reference = now or datetime.now(timezone.utc)
    return reference + timedelta(days=days)


def delete_artifact_file(root: Path, storage_path: str | Path) -> Path:
    """Delete one contained artifact and surface every filesystem failure."""

    resolved = resolve_contained_path(root, storage_path)
    resolved.unlink()
    return resolved


def _safe_output_suffix(original_name: str) -> str:
    suffix = Path(original_name).suffix.casefold()
    return suffix if re.fullmatch(r"\.[a-z0-9]{1,16}", suffix) else ""


def _read_file_stream(path: Path) -> tuple[int, str, bytes, bool]:
    size = 0
    digest = hashlib.sha256()
    first_bytes = bytearray()
    text_decoder = codecs.getincrementaldecoder("utf-8")("strict")
    text_valid = True
    with path.open("rb") as source:
        while True:
            chunk = source.read(CHUNK_SIZE)
            if not chunk:
                break
            size += len(chunk)
            digest.update(chunk)
            if len(first_bytes) < _MAGIC_PREFIX_LENGTH:
                first_bytes.extend(chunk[: _MAGIC_PREFIX_LENGTH - len(first_bytes)])
            try:
                text_decoder.decode(chunk, final=False)
            except UnicodeDecodeError:
                text_valid = False
        if text_valid:
            try:
                text_decoder.decode(b"", final=True)
            except UnicodeDecodeError:
                text_valid = False
    return size, digest.hexdigest(), bytes(first_bytes), text_valid


def describe_artifact(path: Path, original_name: str | None = None) -> StoredArtifact:
    """Describe an existing file using a bounded-prefix classification and hash."""

    display_name = sanitize_original_name(original_name or path.name)
    size, sha256, first_bytes, text_valid = _read_file_stream(path)
    kind, mime = _classify_bytes(display_name, first_bytes, text_valid=text_valid)
    return StoredArtifact(
        path=path,
        storage_name=path.name,
        original_name=display_name,
        kind=kind,
        mime=mime,
        size_bytes=size,
        sha256=sha256,
    )


def persist_output_artifact(source: Path, root: Path) -> StoredArtifact:
    """Copy a generated output into a unique governed storage target."""

    source = Path(source)
    if not source.is_file():
        raise FileNotFoundError(source)

    original_name = sanitize_original_name(source.name)
    target = _new_storage_path(root, _safe_output_suffix(original_name))
    size = 0
    digest = hashlib.sha256()
    first_bytes = bytearray()
    text_decoder = codecs.getincrementaldecoder("utf-8")("strict")
    text_valid = True

    try:
        with source.open("rb") as source_file, target.open("xb") as destination:
            while True:
                chunk = source_file.read(CHUNK_SIZE)
                if not chunk:
                    break
                size += len(chunk)
                digest.update(chunk)
                if len(first_bytes) < _MAGIC_PREFIX_LENGTH:
                    first_bytes.extend(chunk[: _MAGIC_PREFIX_LENGTH - len(first_bytes)])
                try:
                    text_decoder.decode(chunk, final=False)
                except UnicodeDecodeError:
                    text_valid = False
                destination.write(chunk)
            if text_valid:
                try:
                    text_decoder.decode(b"", final=True)
                except UnicodeDecodeError:
                    text_valid = False
    except FileExistsError as exc:
        raise StorageConflictError("Generated output target already exists.") from exc
    except Exception:
        try:
            target.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            logger.exception("Could not remove a failed output partial.")
        raise

    kind, mime = _classify_bytes(
        original_name,
        bytes(first_bytes),
        text_valid=text_valid,
    )
    return StoredArtifact(
        path=target,
        storage_name=target.name,
        original_name=original_name,
        kind=kind,
        mime=mime,
        size_bytes=size,
        sha256=digest.hexdigest(),
    )


UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
