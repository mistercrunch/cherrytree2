# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Cherrytree v2** is an AI-assisted release management and cherry-picking tool for Apache Superset. It's a Python CLI built with Typer that automates complex release management workflows through GitHub API integration and git operations.

## Development Commands

### Setup & Installation
```bash
# Install development environment
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install
```

### Core Development Tasks
```bash
# Run tests
make test                    # Basic test run
pytest                      # Alternative test runner
make test-cov               # Tests with coverage (note: references old showtime, see Makefile line 19)

# Code quality
make lint                   # Run ruff check + mypy
ruff check .                # Linting only
mypy cherrytree             # Type checking (note: references old showtime, see Makefile line 23)
make format                 # Auto-format with ruff
pre-commit run --all-files  # Run all pre-commit hooks

# Build & package
make build                  # Build package with uv
uv build                    # Direct build command
make clean                  # Clean build artifacts
```

### Application Commands
```bash
# CLI shortcuts: both 'ct' and 'cherrytree' work identically

# Configuration (one-time setup)
ct config set-repo /path/to/superset
ct config show

# Core workflow commands
ct minor sync 6.0           # Sync release branch state from GitHub + git
ct minor status 6.0         # Show timeline + PR processing table
ct minor next 6.0           # Get next SHA to cherry-pick
ct micro status 6.0.0rc1    # Show PRs in specific micro release
ct version                  # Show version
```

## Architecture

### Core Domain Objects
- **`Minor`** (`minor.py`): Minor release branch management with GitHub API integration
- **`Micro`** (`micro_release.py`): Individual micro release tracking with git tag operations
- **`Commit`** (`commit.py`): Git commit representation with PR number extraction
- **`PullRequest`** (`pull_request.py`): GitHub PR data with merge state tracking

### Key Interfaces
- **`GitInterface`** (`git_interface.py`): Object-oriented git operations wrapper
- **`GitHubInterface`** (`github_interface.py`): GitHub CLI authentication and command execution
- **Configuration** (`config.py`): YAML-based config management in `~/.cherrytree/config.yml`

### Data Flow Architecture
1. **Sync**: GitHub API (PR search) + git log (commit parsing) → `releases/{version}.yml`
2. **Status**: Read YAML state → Rich table display with clickable GitHub links
3. **Next**: Parse YAML chronological PR order → Return next SHA for cherry-picking

### CLI Command Structure
```
cherrytree/
├── minor/           # Minor release management
│   ├── sync         # Collect GitHub + git state
│   ├── status       # Timeline + PR table display
│   └── next         # Get next cherry-pick SHA
├── micro/           # Micro release analysis
│   └── status       # PRs in specific micro release
└── config/          # Configuration management
    ├── set-repo     # Set local repo path
    ├── set-github   # Set GitHub repo
    └── show         # Display current config
```

## Important Implementation Details

### GitHub API Optimization
- Uses **dual search strategy**: `is:open` + `is:merged` to filter abandoned PRs at source
- **N+1 elimination**: Single GitHub search + git log parsing (not individual PR API calls)
- **Performance**: 30-second sync for 195 PRs (production-tested on apache/superset)

### Git Commit Message Parsing
- **100% parentheses format**: Extracts PR numbers from `(#12345)` at end of commit messages
- **Revert handling**: Takes last PR number for revert commits like `Revert "fix: something (#28363)" (#28567)`
- **Regex**: `re.findall(r'\(#(\d+)\)')` with last match selection

### State Management
- **YAML files**: `releases/{version}.yml` with complete branch state
- **8-digit SHAs**: Consistent shortened format throughout (75% space reduction)
- **Chronological ordering**: PRs ordered by git log sequence to preserve dependencies

### Branch Management
- **Auto-checkout**: Prompts with exact git command when release branch missing locally
- **Remote handling**: Handles fresh repos where release branches exist on origin but not locally
- **User permission**: Shows `git checkout -b 4.0 origin/4.0` and asks before executing

## Quality Standards

### Code Quality Tools
- **Ruff**: Linting and formatting (configured in pyproject.toml)
- **MyPy**: Type checking with strict configuration
- **Pre-commit**: Hooks for trailing-whitespace, yaml, toml validation
- **Pytest**: Testing with coverage reporting

### Type Safety
- Python 3.8+ with comprehensive type hints
- Strict mypy configuration: `disallow_untyped_defs = true`
- Type checking for all modules required

### Error Handling
- Custom exceptions: `GitError`, `GitHubError`
- Proper exception chaining with clear error messages
- User guidance for authentication and setup issues

## Dependencies & Libraries

### Core Runtime Dependencies
- **Typer**: CLI framework with rich integration
- **Rich**: Terminal formatting and progress indicators
- **Pydantic**: Data validation and settings management
- **GitPython**: Git repository operations
- **PyYAML**: Configuration and state file management
- **PyGitHub**: GitHub API integration
- **httpx**: HTTP client for API requests

### Development Dependencies
- **pytest**: Testing framework with coverage
- **ruff**: Linting and formatting
- **mypy**: Static type checking
- **pre-commit**: Git hooks for code quality

## Testing

No test files exist yet in the `tests/` directory (only `__init__.py`). When adding tests:
- Use `pytest` framework
- Place test files in `tests/` directory with `test_*.py` pattern
- Run tests with `make test` or `pytest`
- Include coverage with `make test-cov`
