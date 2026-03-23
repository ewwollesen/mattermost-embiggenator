"""LDIF file output (RFC 2849 compliant)."""

from __future__ import annotations

import base64
import shutil
from importlib import resources
from pathlib import Path

from embiggenator.models import GeneratedGroup, GeneratedUser
from embiggenator.utils import base64_encode_value, needs_base64


def write_ldif_files(
    users: list[GeneratedUser],
    groups: list[GeneratedGroup],
    output_dir: str | Path,
    include_defaults: bool = True,
) -> None:
    """Write generated data to LDIF files in the output directory."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Copy bundled default LDIF files
    if include_defaults:
        _copy_default_ldifs(output_path)

    # Write generated users
    users_file = output_path / "50_a_users.ldif"
    with open(users_file, "w", encoding="utf-8") as f:
        for i, user in enumerate(users):
            if i > 0:
                f.write("\n")
            _write_entry(f, user.to_ldif_attrs())

    # Write generated groups
    groups_file = output_path / "50_b_groups.ldif"
    with open(groups_file, "w", encoding="utf-8") as f:
        for i, group in enumerate(groups):
            if i > 0:
                f.write("\n")
            _write_entry(f, group.to_ldif_attrs())


def _write_entry(f, attrs: list[tuple[str, str | bytes]]) -> None:
    """Write a single LDIF entry."""
    for attr_name, attr_value in attrs:
        if isinstance(attr_value, bytes):
            encoded = base64.b64encode(attr_value).decode("ascii")
            line = f"{attr_name}:: {encoded}"
        elif needs_base64(attr_value):
            encoded = base64_encode_value(attr_value)
            line = f"{attr_name}:: {encoded}"
        else:
            line = f"{attr_name}: {attr_value}"

        # RFC 2849: fold lines longer than 76 chars
        _write_folded_line(f, line)
    f.write("\n")


def _write_folded_line(f, line: str) -> None:
    """Write a line with RFC 2849 folding (continuation lines start with a space)."""
    max_len = 76
    if len(line) <= max_len:
        f.write(line + "\n")
        return

    f.write(line[:max_len] + "\n")
    remaining = line[max_len:]
    while remaining:
        chunk = remaining[: max_len - 1]
        f.write(" " + chunk + "\n")
        remaining = remaining[max_len - 1 :]


def _copy_default_ldifs(output_dir: Path) -> None:
    """Copy bundled default LDIF files to the output directory."""
    defaults_dir = Path(__file__).parent.parent / "data" / "defaults"
    if not defaults_dir.is_dir():
        return

    for ldif_file in sorted(defaults_dir.glob("*.ldif")):
        dest = output_dir / ldif_file.name
        shutil.copy2(ldif_file, dest)
