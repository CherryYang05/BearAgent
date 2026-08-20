import ast
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src" / "bearagent"
CORE_DIRECTORIES = ("domain", "runtime", "ports")
OUTER_OR_FRAMEWORK_PREFIXES = (
    "aiosqlite",
    "anthropic",
    "bearagent.adapters",
    "bearagent.application",
    "bearagent.interfaces",
    "docker",
    "fastapi",
    "google",
    "mcp",
    "openai",
    "sqlalchemy",
    "starlette",
    "typer",
)
APPLICATION_FORBIDDEN_PREFIXES = tuple(
    prefix for prefix in OUTER_OR_FRAMEWORK_PREFIXES if prefix != "bearagent.application"
)


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_core_does_not_import_frameworks_or_outer_layers() -> None:
    violations: list[str] = []
    for directory in CORE_DIRECTORIES:
        for path in sorted((SOURCE_ROOT / directory).rglob("*.py")):
            for module in imported_modules(path):
                if module.startswith(OUTER_OR_FRAMEWORK_PREFIXES):
                    relative = path.relative_to(SOURCE_ROOT)
                    violations.append(f"{relative}: {module}")

    assert not violations, "Forbidden core imports:\n" + "\n".join(violations)


def test_application_does_not_import_adapters_frameworks_or_sdks() -> None:
    violations: list[str] = []
    for path in sorted((SOURCE_ROOT / "application").rglob("*.py")):
        for module in imported_modules(path):
            if module.startswith(APPLICATION_FORBIDDEN_PREFIXES):
                relative = path.relative_to(SOURCE_ROOT)
                violations.append(f"{relative}: {module}")

    assert not violations, "Forbidden application imports:\n" + "\n".join(violations)
