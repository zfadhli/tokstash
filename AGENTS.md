# AGENTS.md — Modern Python Development

This file provides context and conventions for AI coding agents working on this project. It establishes the toolchain, coding standards, architectural patterns, and critical rules to follow.

---

## 1. Python & Toolchain

| Tool | Purpose | Config Files |
|------|---------|-------------|
| **Python 3.12+** | Runtime | `pyproject.toml` → `requires-python` |
| **uv** | Package/project manager (replaces pip+venv+poetry) | `pyproject.toml`, `uv.lock` |
| **ruff** | Linter + formatter (replaces flake8+isort+black) | `pyproject.toml` → `[tool.ruff]` |
| **mypy** | Static type checker | `pyproject.toml` → `[tool.mypy]` |
| **pytest** | Test runner | `pyproject.toml` → `[tool.pytest.ini_options]` |
| **pre-commit** | Git hook runner | `.pre-commit-config.yaml` |

### Committed files (do not edit manually)

- `uv.lock` — deterministic dependency lockfile, regenerated via `uv lock`
- `.python-version` — single-line Python version pin (used by uv, pyenv)

### Key commands

```bash
# Setup
uv sync                           # Install all dependencies from lockfile
uv sync --group dev               # Include dev dependencies
uv sync --all-groups              # Include all optional dependency groups

# Adding / removing dependencies
uv add package_name               # Add runtime dependency + update lockfile
uv add --group dev package_name   # Add dev dependency
uv remove package_name

# Running
uv run python -m src.module       # Run module in project's venv
uv run pytest                     # Run tests in project's venv

# Linting & formatting
uv run ruff check .               # Lint all files
uv run ruff format --check .      # Check formatting (CI)
uv run ruff format .              # Auto-format all files
uv run ruff check --fix .         # Lint + auto-fix

# Type checking
uv run mypy src/

# Lockfile management (no `uv pip compile`)
uv lock                           # Regenerate uv.lock from pyproject.toml
```

---

## 2. Project Structure

```
project-root/
├── src/
│   └── package_name/             # Main package (import as `import package_name`)
│       ├── __init__.py
│       ├── __main__.py           # `python -m package_name` entry
│       ├── cli/                  # CLI entrypoints (click, typer, argparse)
│       ├── core/                 # Business logic, no side effects
│       ├── models/               # Data models, Pydantic, dataclasses
│       ├── infrastructure/       # DB, HTTP clients, file I/O, external services
│       └── _compat.py            # Version/import compatibility shims
├── tests/
│   ├── unit/                     # Pure unit tests, no I/O
│   ├── integration/              # Tests with real I/O (DB, network, files)
│   ├── conftest.py               # Shared fixtures
│   └── fixtures/                 # Test data files
├── scripts/                      # Dev/CI helper scripts (not shipped)
├── docs/                         # Documentation (MkDocs / Sphinx)
├── pyproject.toml                # Single source of truth for metadata/deps/tooling
├── AGENTS.md                     # This file
├── README.md
├── LICENSE
├── .pre-commit-config.yaml
└── .gitignore
```

### When to modify this list

- A new **importable subpackage** gets added to `src/package_name/`.
- A new **dependency group** (e.g. `--group docs`) is added to `pyproject.toml`.
- Tool configuration moves from one file to another.

---

## 3. Coding Standards

### 3.1 Style & Formatting

Enforced by **ruff** (format subcommand). These rules are **not negotiable** — if ruff reformats code, the output is the source of truth.

- Line length: **88** (ruff default, same as black)
- Quotes: **double quotes** for strings (`"hello"` not `'hello'`)
- Trailing commas: always add after the last element in multi-line collections
- Imports: ruff's `isort`-style grouping — stdlib, third-party, first-party; `TYPE_CHECKING` blocks at the bottom

### 3.2 Type Annotations

This project requires **strict type annotations** enforced by mypy.

```python
# ✅ Correct
def process_item(item: Item, batch_size: int = 10) -> list[Result]: ...

from collections.abc import Sequence  # not typing.Sequence

# ❌ Avoid
def process_item(item, batch_size=10): ...
```

**Rules:**

1. Every function/method **must** have typed parameters and return type (including `-> None`).
2. Use `collections.abc` for generic types (`Sequence`, `Mapping`, `Iterable`) instead of `typing` versions (Python 3.9+).
3. Prefer `|` union syntax: `str | None` not `Optional[str]`.
4. Prefer `list[X]` over `List[X]`, `dict[K, V]` over `Dict[K, V]` (Python 3.9+).
5. Use `Self` return type for `@classmethod` and fluent interfaces.
6. Use `type[X]` for class objects, not `Type[X]`.
7. Use `@override` decorator from `typing` (3.12+) when overriding methods.
8. Annotate `__init__` arguments, not just the method signature.
9. Use `Protocol` for structural subtyping (duck types).
10. Use `TypedDict` for dicts with known keys.

### 3.3 Modern Python Idioms

| Idiom | Do | Don't |
|-------|----|-------|
| **Dataclasses** | `@dataclass(slots=True, frozen=True)` | Manual `__init__`, `__repr__` |
| **Pattern matching** | `match value: case str(): ...` | Chained `isinstance()` |
| **Exception chaining** | `raise RuntimeError(...) from exc` | Bare `raise` losing context |
| **Path handling** | `pathlib.Path` | `os.path.join`, `os.path.exists` |
| **String formatting** | f-strings `f"hello {name}"` | `%` formatting, `.format()` |
| **Enums** | `StrEnum`, `IntEnum` (3.11+) | Ad-hoc string constants |
| **Type aliases** | `type JSON = str | int | float | bool | None | list[JSON] | dict[str, JSON]` | Manual `Union` |
| **Context managers** | `with (open(a) as f, open(b) as g):` (3.10+) | Nested `with` blocks |
| **Generics** | `def first[T](items: list[T]) -> T` (3.12+) | `def first(items: list[Any]) -> Any` |

### 3.4 Naming Conventions

| Category | Convention | Example |
|----------|-----------|---------|
| Packages / modules | `snake_case`, short, no hyphens | `core`, `db_adapters` |
| Classes / Types | `PascalCase` | `UserRepository`, `ItemRequest` |
| Functions / Methods | `snake_case` | `get_user_by_id` |
| Variables | `snake_case` | `user_record` |
| Constants | `UPPER_SNAKE_CASE` | `DEFAULT_TIMEOUT` |
| Private (module-internal) | Leading underscore | `_normalize_name` |
| Test functions | `snake_case`, descriptive | `test_create_user_raises_on_duplicate_email` |

### 3.5 Architecture & Design

- **Layered architecture**: `models` → `core` → `infrastructure` → `cli/web`
  - `core` never imports from `infrastructure` or `cli`
  - `infrastructure` implements interfaces defined in `core`
  - `cli` is thin — parses input, calls `core`, formats output
- **Dependency injection**: Pass dependencies explicitly, no global state, no `os.environ` reads inside functions (inject via config objects)
- **Composition over inheritance**: Prefer small, focused classes with Protocols rather than deep class hierarchies
- **Error handling**: Define project-specific exception hierarchy rooted in a base `ProjectError(Exception)`
- **Async**: Use `asyncio` for I/O-bound work, `anyio` for structured concurrency if needed

### 3.6 Logging

- Use `structlog` if available, otherwise `logging.getLogger(__name__)`
- Log levels: `debug` for details, `info` for normal operations, `warning` for recoverable issues, `error` for failures
- Never log sensitive data (PII, tokens, passwords)

---

## 4. Testing

### Standards

- **Coverage target**: 90%+ for `src/` (enforced in CI)
- **Test types**:
  - `tests/unit/` — Fast, no I/O, test single functions/classes. Mock at interface boundaries.
  - `tests/integration/` — Test real interactions (DB, API, filesystem). Use fixtures, not mocks.
- **File naming**: `test_<module_name>.py` mirroring `src/`

### pytest conventions

```python
# Use fixtures for shared setup
@pytest.fixture
def user_repo() -> UserRepository:
    return InMemoryUserRepository()

# Parametrize for data-driven tests
@pytest.mark.parametrize("input,expected", [("a", 1), ("b", 2)])
def test_something(input: str, expected: int) -> None: ...

# Use tmp_path (pathlib.Path) not tempfile
def test_file_creation(tmp_path: Path) -> None:
    f = tmp_path / "data.json"
    ...
```

### Running tests

```bash
uv run pytest                        # All tests
uv run pytest tests/unit/            # Unit tests only
uv run pytest -k "create_user"       # Filter by test name
uv run pytest --coverage             # With coverage report
uv run pytest --no-header -q         # Quiet mode
```

---

## 5. Documentation & Commits

### 5.1 Docstrings

Use **Google-style** docstrings:

```python
def fetch_user(db: Database, user_id: int) -> User | None:
    """Fetch a single user by their primary key.

    Args:
        db: An open database connection.
        user_id: The user's numeric identifier.

    Returns:
        The matching User, or None if not found.

    Raises:
        DatabaseError: If the query fails due to a connection issue.
    """
```

### 5.2 Commit messages

```
type(scope): brief description in lowercase

- Body can use bullet points for rationale
- Reference issues with #123
```

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `perf`, `ci`

---

## 6. AI Agent Operational Rules

1. **Read first** — Always read `AGENTS.md` and `pyproject.toml` before making changes.
2. **Respect auto-generated files** — Do not manually edit `uv.lock`, `.python-version`, or generated code.
3. **Run linter before committing** — `uv run ruff check . && uv run ruff format . && uv run mypy src/`
4. **Write tests for new logic** — Every new function/class needs a corresponding test.
5. **Prefer small, focused edits** — One logical change per PR. Refactor separately from feature work.
6. **Use f-strings** — Never use `%` or `.format()`.
7. **Type everything** — No untyped function signatures. Use `Any` only as a last resort.
8. **Ask for clarification** — If requirements are ambiguous, ask before coding.
9. **Do not add dependencies lightly** — Each new dependency must be justified. Prefer stdlib solutions.
10. **Compatibility** — Target Python 3.12+. Use `from __future__ import annotations` at module top if deferred eval is needed.

---

## 7. CI/CD

See `.github/workflows/ci.yml` (or equivalent). Typical pipeline:

1. `uv sync --all-groups`
2. `ruff check . && ruff format --check .`
3. `mypy src/`
4. `pytest --coverage`
5. `pip-audit` or `uv export --format requirements | safety check`
