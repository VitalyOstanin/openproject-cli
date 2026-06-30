"""Allow ``python -m openproject_cli`` to run the CLI."""

import sys

from openproject_cli.cli import main

if __name__ == "__main__":
    sys.exit(main())
