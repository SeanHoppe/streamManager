import sys

from stream_manager import __version__


def main() -> int:
    print(f"StreamManager v{__version__} - pre-POC scaffold; see INITIAL_PLAN.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
