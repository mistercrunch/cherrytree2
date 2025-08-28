# 🍒 Cherrytree

Intelligent AI-assisted release management and cherry-picking for Apache Superset.

## Overview

Cherrytree 2.0 is a modern rewrite of the original cherrytree tool, enhanced with AI capabilities to automate the complex parts of release management:

- **Smart Cherry-Picking**: Automatically resolve merge conflicts using AI
- **Dependency Analysis**: Understand the chain of dependencies behind each commit
- **Intelligent Planning**: Create optimal release plans from GitHub labels and PR IDs
- **Confidence Scoring**: Get confidence levels for cherry-pick success
- **Interactive Resolution**: Human-in-the-loop for complex decisions

## Installation

```bash
# Install with uv (recommended)
uv pip install cherrytree

# Or with pip
pip install cherrytree
```

## Quick Start

```bash
# Check version (both commands work)
cherrytree version
ct version

# Sync a release branch (requires local Superset repo and gh CLI auth)
ct sync 5.0 --repo /path/to/superset

# Dry-run to see what would be done
ct sync 5.0 --repo /path/to/superset --dry-run
```

## Available Commands

### `cherrytree sync` - Build Release Branch State
Collects complete release branch state from git repository and GitHub API.

**Usage:**
```bash
# Sync release branch 5.0 (ct is shortcut for cherrytree)
ct sync 5.0 --repo /path/to/superset

# Use with fork or different repo
ct sync 5.0 --repo /path/to/fork --github-repo myorg/superset

# Preview without creating files
ct sync 5.0 --repo /path/to/superset --dry-run
```

**What it does:**
- Finds merge-base SHA where branch diverged from master
- Gets all commits currently in release branch
- Queries GitHub API for all PRs labeled `v5.0`
- Extracts PR numbers from commit messages
- Creates `releases/5.0.yml` with complete state

**Prerequisites:**
- Local Superset repository clone
- GitHub CLI authenticated: `gh auth login`

## Coming Soon

- `ct status` - Show current release branch state
- `ct next` - Get next SHA to cherry-pick
- `ct cherry-pick` - Execute cherry-picks with conflict analysis
- `ct config` - Set repository path and preferences

## Development

```bash
# Setup development environment with uv
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install

# Run tests
make test

# Run linting
make lint
```

## Philosophy

Like Joe said: "It's like early stage robotaxi. I'm still in the driver seat and if I need to I can stop it if I see danger ahead."

Cherrytree provides AI assistance for the tedious parts while keeping humans in control of critical decisions.

## License

Apache 2.0
