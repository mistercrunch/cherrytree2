# 🍒 Cherrytree v2

AI-assisted release management and cherry-picking tool for Apache Superset. A Python CLI built with Typer that automates complex release management workflows through GitHub API integration and git operations.

## Overview

Cherrytree v2 streamlines Apache Superset release management by automating the tedious parts while keeping humans in control of critical decisions:

- **Smart State Collection**: 30-second sync for 195 PRs using optimized GitHub API + git integration
- **Rich Visual Interface**: Clickable GitHub links, timeline displays, and progress tracking
- **Chronological Cherry-Picking**: Dependency-friendly PR ordering to minimize conflicts
- **Human-Claude Collaboration**: Structured YAML workspace for AI assistance
- **Production Tested**: Validated on real Apache Superset releases (4.0, 6.0)

## Quick Start

### Installation

```bash
# Install development environment
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install
```

### Basic Workflow

```bash
# One-time setup
ct config set-repo /path/to/superset

# Daily release management workflow
ct minor sync 6.0                    # Refresh state (10-30s)
ct minor status 6.0                  # Review timeline + pending PRs
ct minor next 6.0                    # Get next SHA: 836540e8
ct minor next 6.0 -v                 # Full details + cherry-pick command
git cherry-pick -x 836540e8          # Execute (human or Claude)
```

## Production-Ready Commands

### Core Workflow
- **`ct minor sync <version>`** - Collect GitHub + git state (30s for 195 PRs)
- **`ct minor status <version>`** - Timeline + PR table with clickable links
- **`ct minor next <version>`** - Get next cherry-pick SHA (chronological order)
- **`ct micro status <version>`** - PRs in specific micro release
- **`ct version`** - Show version

### Configuration
- **`ct config set-repo <path>`** - Set local repo path
- **`ct config set-github <repo>`** - Set GitHub repo
- **`ct config show`** - Display current config

**CLI shortcuts**: Both `ct` and `cherrytree` work identically

## Experimental Commands

> See [IDEAS.md](IDEAS.md) for detailed experimental features and research

- **`ct analyze`** - Bulk conflict analysis for all PRs (conceptual)
- **`ct chain`** - Interactive cherry-pick workflow (implemented, needs validation)
- **`ct analyze-next`** - Single PR conflict prediction (basic implementation)

## Project Structure

```
cherryblossom/
├── cherrytree/                 # Main package
│   ├── cli/                    # CLI entry points and commands
│   ├── core/                   # Core domain objects (Minor, Micro, Commit, PullRequest)
│   ├── interfaces/             # External system integrations (Git, GitHub)
│   ├── models/                 # Data models and validation
│   └── utils/                  # Shared utilities
├── releases/                   # YAML state files (git-ignored)
│   ├── 4.0.yml                # Release branch state
│   └── 6.0.yml                # Current active release
├── docs/                       # Documentation
│   ├── CLAUDE.md               # Stable documentation for Claude Code
│   └── IDEAS.md                # Experimental features and research
├── pyproject.toml              # Package configuration
├── Makefile                    # Development commands
└── README.md                   # This file
```

## Real-World Performance

- **Apache Superset 4.0**: 195 PRs analyzed in 30 seconds
- **Apache Superset 6.0**: 35 PRs analyzed in 10 seconds
- **Success rate**: 100% PR→SHA mapping accuracy
- **Scale tested**: Enterprise repository complexity

## Key Features

### Smart GitHub API Integration
- **Dual search strategy**: `is:open` + `is:merged` to filter abandoned PRs at source
- **N+1 elimination**: Single GitHub search + git log parsing (not individual PR API calls)
- **Progress indicators**: Real-time feedback during large dataset processing

### Intelligent Git Operations
- **100% parentheses parsing**: Extracts PR numbers from `(#12345)` commit message format
- **Revert handling**: Takes last PR number for complex revert commits
- **8-digit SHAs**: Consistent shortened format (75% space reduction)
- **Chronological ordering**: PRs ordered by git log sequence to preserve dependencies

### Rich User Experience
- **Clickable GitHub integration**: PR numbers and SHAs link directly to GitHub
- **Dual date display**: Tag creation vs commit dates in micro releases
- **Cherry count tracking**: Visual 🍒 indicators showing commits between releases
- **Semantic version logic**: Auto-detects latest minor, redirects PRs appropriately

### Human-Claude Collaboration
- **Shared YAML workspace**: Both human and Claude can read/write state
- **Multiple output formats**: Human tables + JSON for programmatic use
- **Session persistence**: State survives across Claude sessions
- **Command compatibility**: Same interface for manual and automated use

## Development

### Setup
```bash
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
pre-commit install
```

### Daily Development
```bash
make lint                    # ruff + mypy
make format                  # Auto-format
make test                    # Run tests (when they exist)
make build                   # Package build

# Git workflow
pre-commit run --all-files   # Check before commit
git add . && git commit      # Never use --no-verify
```

### Quality Standards
- **Ruff**: Linting and formatting (configured in pyproject.toml)
- **MyPy**: Type checking with strict configuration
- **Pre-commit**: Hooks for trailing-whitespace, yaml, toml validation
- **Python 3.8+**: Comprehensive type hints throughout

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

## State Management

### YAML Files
- **Location**: `releases/{version}.yml` with complete branch state
- **Format**: 8-digit SHAs, chronological PR ordering, dual date tracking
- **Accessibility**: Human-readable, Claude-parseable, git-trackable

### Configuration
- **User config**: `~/.cherrytree/config.yml` (repo paths, GitHub settings)
- **One-time setup**: Set local repo path, GitHub repo (defaults to apache/superset)
- **Smart defaults**: Minimal configuration required

## Claude Code Integration

Cherrytree v2 is designed for seamless human-Claude collaboration:

```bash
# Claude can analyze structured data
ct minor next 6.0 --format json     # Machine-readable output
ct minor status 6.0 --format json   # Full state for analysis

# Claude can reason about PRs
# "PR #34871 is test-related, low risk, safe to cherry-pick"
# "PR #34825 touches authentication, needs careful review"
```

**Documentation for Claude Code**: See [CLAUDE.md](CLAUDE.md)

## Philosophy

> "It's like early stage robotaxi. I'm still in the driver seat and if I need to I can stop it if I see danger ahead." - Joe

Cherrytree provides AI assistance for the tedious parts while keeping humans in control of critical decisions. It transforms cherry-picking from a reactive, manual process into a strategic, data-driven workflow.

## License

Apache 2.0
