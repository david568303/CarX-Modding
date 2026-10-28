"""Command-line compatibility entrypoint for binary-only API discovery."""
from prepare_api_map import main

if __name__ == "__main__":
    raise SystemExit(main())
