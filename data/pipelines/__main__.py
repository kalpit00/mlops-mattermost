"""Allow ``python -m data.pipelines`` as an alias for the Jigsaw CLI."""

from .cli_jigsaw import main

if __name__ == "__main__":
    raise SystemExit(main())
