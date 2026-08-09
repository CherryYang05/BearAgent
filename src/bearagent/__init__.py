"""BearAgent package."""

from importlib.metadata import PackageNotFoundError, version


def package_version() -> str:
    """Return the installed package version without exposing packaging details elsewhere."""
    try:
        return version("bearagent")
    except PackageNotFoundError:
        return "0.1.0+local"


__all__ = ["package_version"]
