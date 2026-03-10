"""Conductor CLI entry point."""

import argparse


def main() -> None:
    """Run the Conductor CLI."""
    parser = argparse.ArgumentParser(
        prog="conductor",
        description="Conductor: AI agent orchestration",
    )
    parser.parse_args()
    print("Conductor v0.1.0")
