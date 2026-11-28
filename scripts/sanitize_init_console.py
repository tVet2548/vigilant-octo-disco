#!/usr/bin/env python3
"""Remove init-service console fd requests from a headless Android image.

This deliberately edits only the `console [device]` service option inside
`service ...` stanzas. It does not touch action commands, shell statements,
comments, or text outside service definitions.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


_CONSOLE_OPTION = re.compile(r"console(?:\s+\S+)?")


def sanitize_init_console(roots: list[Path]) -> tuple[int, int]:
    seen: set[Path] = set()
    changed_files = 0
    removed_options = 0

    for root in roots:
        if not root.exists():
            continue
        for rc_file in sorted(root.rglob("*.rc")):
            try:
                resolved = rc_file.resolve()
            except OSError:
                resolved = rc_file
            if resolved in seen or not rc_file.is_file():
                continue
            seen.add(resolved)

            try:
                lines = rc_file.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
            except OSError:
                continue

            output: list[str] = []
            in_service = False
            local_removed = 0
            for line in lines:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    output.append(line)
                    continue

                is_top_level = not line[0].isspace()
                if is_top_level:
                    in_service = stripped.startswith("service ")

                if in_service and _CONSOLE_OPTION.fullmatch(stripped):
                    indent = line[: len(line) - len(line.lstrip())]
                    output.append(indent + "# DroidPort headless CI: service console option removed; inherit /dev/null\n")
                    local_removed += 1
                else:
                    output.append(line)

            if local_removed:
                rc_file.write_text("".join(output), encoding="utf-8")
                changed_files += 1
                removed_options += local_removed

    return removed_options, changed_files


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(f"usage: {Path(argv[0]).name} ROOT [ROOT ...]", file=sys.stderr)
        return 2
    roots = [Path(arg) for arg in argv[1:]]
    removed, files = sanitize_init_console(roots)
    print(f"DROIDPORT_RC_CONSOLE_SANITIZE removed={removed} files={files}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
