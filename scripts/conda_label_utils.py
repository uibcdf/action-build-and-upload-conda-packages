"""Exact public distribution identity shared by label operations."""

from __future__ import annotations

import re
from dataclasses import dataclass

from binstar_client import Binstar
from binstar_client.utils import get_server_api

SHA256 = re.compile(r"[0-9a-f]{64}")
LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_FIELD = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.+-]*")


@dataclass(frozen=True)
class ExactPackage:
    owner: str
    package: str
    version: str
    basename: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.package}/{self.version}/{self.basename}"


def parse_exact_spec(value: str) -> ExactPackage:
    parts = value.split("/")
    if len(parts) != 5 or any(
        len(part) > 255 or _FIELD.fullmatch(part) is None or part in {".", ".."}
        for part in parts
    ):
        raise ValueError(
            "package spec must be exact safe owner/package/version/subdir/filename"
        )
    owner, package, version, subdir, filename = parts
    if not filename.startswith(f"{package}-{version}-") or not filename.endswith(
        (".conda", ".tar.bz2")
    ):
        raise ValueError(
            "package filename must match package/version and end in .conda or .tar.bz2"
        )
    return ExactPackage(owner, package, version, f"{subdir}/{filename}")


def exact_distribution(api, package: ExactPackage) -> dict | None:
    """Find one file across all labels, rejecting incomplete or contradictory evidence."""
    document = api.release(package.owner, package.package, package.version)
    entries = document.get("distributions") if isinstance(document, dict) else None
    if not isinstance(entries, list) or any(
        not isinstance(item, dict) for item in entries
    ):
        raise RuntimeError("public distribution inventory is incomplete")
    matches = [
        item
        for item in entries
        if item.get("full_name") == package.full_name
        or item.get("basename") == package.basename
    ]
    if len(matches) > 1:
        raise RuntimeError("public distribution identity is duplicated")
    if not matches:
        return None
    item = matches[0]
    if (
        item.get("full_name", package.full_name) != package.full_name
        or item.get("basename", package.basename) != package.basename
    ):
        raise RuntimeError("public distribution identity is contradictory")
    labels = item.get("labels")
    if (
        not isinstance(labels, list)
        or len(labels) > 64
        or any(
            not isinstance(label, str)
            or len(label) > 128
            or LABEL.fullmatch(label) is None
            for label in labels
        )
        or len(set(labels)) != len(labels)
    ):
        raise RuntimeError("public distribution labels are incomplete")
    return item


def public_api():
    """Discard ambient credentials even if the installed client discovers a token."""
    return get_server_api(cls=lambda _token, **kwargs: Binstar(None, **kwargs))
