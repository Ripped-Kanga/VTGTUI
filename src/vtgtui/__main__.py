"""Entry point for vtgtui."""

from vtgtui.app import VTGApp


def main() -> None:
    app = VTGApp()
    app.run()


if __name__ == "__main__":
    main()
