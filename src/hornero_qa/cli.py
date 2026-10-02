"""hornero-qa command line."""

from __future__ import annotations

import argparse

from hornero_qa import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hornero-qa", description=__doc__)
    parser.add_argument("--version", action="version", version=f"hornero-qa {__version__}")
    parser.parse_args(argv)
    parser.print_help()
    return 0
