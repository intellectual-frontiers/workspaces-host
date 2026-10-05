import sys

from ws_host.core.cli import main


def run() -> None:
    """The `ws-host` program an installed wheel provides."""
    sys.exit(main(sys.argv[1:]))


if __name__ == "__main__":
    run()
