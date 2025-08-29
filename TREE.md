# Smart Cherry-Pick Conflict Resolution

This document outlines the design for advanced merge conflict resolution tooling in Cherrytree v2. When cherry-picking commits in Apache Superset, complex dependency chains can create challenging merge conflicts that require intelligent analysis and resolution strategies.

## Problem Statement

Cherry-picking individual commits often leads to merge conflicts when the target commit depends on other commits that haven't been cherry-picked to the release branch. Current manual resolution approaches are:
- Time-consuming for complex dependency chains
- Error-prone when multiple interdependent commits are involved
- Difficult to assess the scope of required changes upfront

## Conflict Resolution Strategy

### Simple Conflicts
**Scope**: Few lines across 1-2 files with obvious resolution paths
**Approach**: Manual resolution using standard git conflict markers

### Complex Conflicts
**Scope**: Multi-file conflicts with unclear dependency relationships
**Approach**: Automated dependency graph analysis to identify prerequisite commits

## Technical Architecture

### Dependency Graph Construction

The core innovation is building a dependency graph without mutating repository state:

1. **Simulate Cherry-Pick**: Use `git merge-tree` to analyze potential conflicts without entering merge state
2. **Identify Conflicting Lines**: Parse merge-tree output to locate specific conflict regions
3. **Trace Dependencies**: Use `git blame` on conflicting lines to identify source commits
4. **Recursive Analysis**: Build dependency tree by analyzing each identified commit
5. **Complexity Assessment**: Apply bailout thresholds to prevent excessive recursion

### Non-Destructive Analysis

Key insight: Git provides commands to explore merge conflicts without mutating working directory state:

```bash
# Simulate three-way merge without changing working tree
git merge-tree $(git merge-base target commit) commit target

# Identify which commits last modified conflicting lines
git blame --porcelain <file> | grep -A1 conflicting_line_range
```

This enables safe exploration of complex dependency chains without disrupting the current cherry-pick workflow.

### Complexity Thresholds

To prevent infinite recursion and scope creep, the system applies configurable thresholds:

- **Maximum dependency depth**: Limit recursive analysis to N levels
- **Commit count limits**: Bail out if dependency chain exceeds M commits
- **File scope boundaries**: Consider conflicts spanning >X files as high complexity
- **Author diversity**: Track conflicts across different development teams

## Implementation Approaches

### Approach 1: Interactive Deterministic Tool

A command-line tool that guides users through conflict resolution with intelligent analysis:

```bash
# Example workflow
ct conflict analyze abc123d
→ Analyzing potential conflicts for commit abc123d...
→ Found 3 dependency conflicts:
  • sha1: fix: update API endpoint (author: alice)
    9 conflicting lines across 3 files
  • sha2: refactor: rename utility function (author: bob)
    2 conflicting lines across 1 file
  • sha3: feat: add new validation logic (author: charlie)
    15 conflicting lines across 5 files

ct conflict pick abc123d --interactive
→ Attempting to cherry-pick commit abc123d
→ Execute git cherry-pick abc123d? (Y/n): Y
→ Conflict detected. Recommended resolution order:
  1. sha2 (lowest complexity)
  2. sha1 (moderate complexity)
  3. abc123d (target commit)
→ Start with sha2? (Y/n): Y
```

**Benefits**:
- User maintains control over the process
- Clear visibility into dependency analysis
- Can pause/resume conflict resolution sessions

### Approach 2: AI-Assisted Agent

An intelligent agent that automates conflict resolution with human oversight:

```yaml
# AI Agent Prompt Framework
role: "Apache Superset cherry-pick conflict resolution specialist"
capabilities:
  - Assess merge conflict complexity using git diff analysis
  - Build dependency graphs via git blame on conflicting lines
  - Evaluate resolution strategies and recommend optimal paths
  - Execute cherry-pick sequences with validation checkpoints

workflow:
  1. analyze_conflict:
     - Parse git merge-tree output for conflict regions
     - Classify complexity: simple|moderate|complex
     - Generate dependency graph with depth limits

  2. strategy_selection:
     - Recommend resolution order based on complexity scoring
     - Identify prerequisite commits for successful cherry-pick
     - Estimate time and risk for each approach

  3. execution:
     - Execute git operations with validation at each step
     - Provide detailed progress reporting
     - Bail out if complexity exceeds configured thresholds

bailout_conditions:
  - Dependency depth > 5 levels
  - Total commits required > 10
  - Cross-team conflicts detected
  - Estimated resolution time > 2 hours
```

**Benefits**:
- Automated analysis and execution
- Consistent conflict assessment methodology
- Detailed reporting for complex scenarios
- Learning from resolution patterns over time

## Integration with Cherrytree v2

This functionality would extend the existing command structure:

```bash
ct conflict analyze <sha>     # Generate dependency analysis report
ct conflict pick <sha>        # Interactive guided cherry-pick
ct conflict auto <sha>        # AI-assisted automatic resolution
ct conflict report <sha>      # Export complexity assessment
ct conflict config            # Configure thresholds and preferences
```

The system leverages existing Cherrytree infrastructure:
- **Git Interface**: Extend `GitInterface` with merge-tree and blame operations
- **GitHub Integration**: Enrich conflict analysis with PR context and metadata
- **YAML State**: Persist conflict analysis results alongside release state
- **Rich Display**: Present dependency graphs using existing table formatting

## Current Implementation: Chain Command

### What's Been Built

The `ct minor chain 6.0` command provides an interactive cherry-pick workflow with intelligent conflict analysis. Instead of blindly attempting cherry-picks, it analyzes each commit upfront and provides actionable information to guide decision-making.

### Key Features

**Interactive Workflow Loop**:
- Analyzes PRs in dependency-friendly order (oldest in master → newest in master)
- Shows conflict predictions with file-level detail
- Presents 4-option menu: Proceed, Show diff, Skip, Abort
- Continues until no more PRs or user aborts

**Intelligent Conflict Analysis**:
- **GitPython Integration**: Uses structured Git objects instead of text parsing
- **File-Level Predictions**: Shows exact files that will conflict with line estimates
- **Complexity Classification**: Categorizes as clean, simple, moderate, or complex
- **Safety Checks**: Branch verification, sync validation, cherry-pick state detection

**Rich Information Display**:
- **Blame Analysis**: Shows recent commits that touched each conflicting file
- **Clickable Links**: SHA and PR numbers link directly to GitHub
- **Detailed Tables**: Conflict regions, line ranges, and change descriptions
- **Progress Tracking**: Running count of successful/skipped cherry-picks

### Technical Approach

**Evolution from Text Parsing to Structured Analysis**:

Initial approach used `git merge-tree` with text parsing:
```bash
git merge-tree $(git merge-base target commit) commit target
```
This generated 2.3M+ characters of output that was difficult to parse reliably.

**Current GitPython Approach**:
```python
# Get structured commit objects
target_commit = repo.commit(target_branch)
cherry_commit = repo.commit(commit_sha)
parent_commit = cherry_commit.parents[0]

# Analyze each changed file
commit_diff = parent_commit.diff(cherry_commit)
for diff_item in commit_diff:
    conflict_info = analyze_file_conflict(parent, cherry, target, file_path)
```

**Critical Ordering Logic**:
The chain processes PRs in **oldest-first** order based on their merge sequence in master branch:
```bash
git log master --reverse --grep="#[0-9]"
# Returns: PR #100 → PR #101 → PR #102 (dependency-friendly order)
```

**Why Oldest-First Matters**:
- **Dependencies flow forward**: Newer PRs often depend on older ones
- **Conflict reduction**: Cherry-picking dependencies first prevents conflicts
- **Natural workflow**: Matches how features are built incrementally
- **Example**: If PR #102 adds a feature that uses utility functions from PR #101, cherry-picking #101 first makes #102 clean

**Benefits of Structured Approach**:
- **Accurate File Detection**: Gets actual files changed in the commit
- **Content Analysis**: Compares file versions at three points (parent → cherry → target)
- **Better Estimates**: Uses real line counts instead of parsing heuristics
- **Reliability**: Handles edge cases like binary files, renames, and deletions

### Current Capabilities

**Conflict Analysis**:
```bash
🚨 2 files, 23 lines (moderate)
  • UPDATING.md: 1 region(s), 15 lines
    └─ abc12345 (#34821): fix: update release process documentation
       by alice on 2024-08-28
  • superset-frontend/spec/helpers/jsDomWithFetchAPI.ts: 1 region(s), 8 lines
    └─ jkl45678 (#34702): test: mock MessageChannel for Jest stability
       by david on 2024-08-28
```

**Interactive Decision Making**:
```
What would you like to do?
1. Proceed - Execute: git cherry-pick 836540e8
2. Show diff - View raw changes before deciding
3. Skip - Skip this PR and continue to next
4. Abort - Stop the cherry-pick chain
Choose option (1-4) [1]:
```

**Safety Features**:
- Branch mismatch detection and confirmation
- SHA validation against git repository
- Cherry-pick state detection (prevents starting mid-operation)
- Sync validation (warns when YAML data is stale)

### Known Limitations

**Blame Analysis Scope**:
- Currently shows commits already in target branch that touched conflicting files
- More useful would be showing **potential dependencies** (commits between cherry-pick and target)
- Missing analysis of related PRs that might need to travel together

**Diff Display Issues**:
- "Show diff" option shows commit metadata and stats, not actual line-by-line changes
- ANSI color codes (`[33m`, `[32m+[m`) make output hard to read
- Users expect to see the actual `+/-` diff content

**Conflict Prediction Accuracy**:
- Static analysis may not catch all real-world conflicts
- Complex merge scenarios (renames, binary files) need refinement
- Line count estimates are heuristic-based

### Future Roadmap

**Enhanced Dependency Analysis**:
```python
blame_info = {
    "target_branch_commits": current_blame_analysis(),
    "potential_dependencies": find_commits_between(cherry, target, file_path),
    "related_master_commits": find_related_work(cherry, file_path)
}
```

**Improved Diff Display**:
- Use `git show --no-color --no-stat` for clean line-by-line changes
- Add separate "Show summary" vs "Show raw diff" options
- Implement proper pager with syntax highlighting

**Advanced Conflict Resolution**:
- Automated dependency detection and suggestion
- Interactive conflict resolution guidance
- Integration with external merge tools
- Conflict resolution state persistence

**Workflow Enhancements**:
- Bulk operations (cherry-pick multiple clean commits)
- Conflict resolution templates
- Integration with GitHub PR workflows
- Automated testing of cherry-picked commits

## Proposed Enhancement: Master Analysis Command

### Overview: `ct minor analyze 6.0`

A comprehensive static analysis command that evaluates **all pending PRs** in a release branch to identify the easiest cherry-picks without any git state changes. Instead of the sequential approach of `chain`, this provides a bird's-eye view of all available work.

### Core Concept

**Static Bulk Analysis**: For every PR marked for cherry-pick in the YAML state, run conflict analysis against the current target branch state and present results in a sortable table showing complexity metrics.

### Command Output Format

```
Cherry-Pick Analysis: 6.0 Branch (Current State)
Total PRs to analyze: 47 | Clean: 12 | Simple: 18 | Moderate: 11 | Complex: 6

┌─────────┬────────────┬─────────────────────────────────┬─────────────┬──────────────────┬────────────┐
│ SHA     │ PR#        │ Title                          │ SHA Size    │ Conflicts        │ Complexity │
│         │            │                                │ Files│Lines │ Files│Rgns│Lines │            │
├─────────┼────────────┼─────────────────────────────────┼──────┼──────┼──────┼────┼──────┼────────────┤
│ abc1234 │ #34821     │ fix: typo in documentation     │   1  │   3  │   0  │ 0  │  0   │ clean      │
│ def5678 │ #34822     │ test: add unit test coverage   │   2  │  45  │   0  │ 0  │  0   │ clean      │
│ ghi9012 │ #34823     │ feat: add loading spinner      │   4  │  67  │   3  │ 1  │  5   │ simple     │
│ jkl3456 │ #34824     │ refactor: extract utility fn   │   6  │ 123  │   4  │ 2  │ 12   │ simple     │
│ mno7890 │ #34825     │ fix: authentication timeout    │   8  │ 234  │   6  │ 3  │ 23   │ moderate   │
│ pqr1234 │ #34826     │ feat: new dashboard component  │  15  │ 456  │  12  │ 8  │ 67   │ complex    │
└─────────┴────────────┴─────────────────────────────────┴──────┴──────┴──────┴────┴──────┴────────────┘

Legend: SHA Size = actual commit size | Conflicts = predicted conflicts if cherry-picked now

Recommendations:
• 12 clean PRs ready for immediate cherry-pick (no conflicts, various sizes)
• Small clean commits (abc1234: 1 file, 3 lines) = ideal quick wins
• Large clean commits (def5678: 2 files, 45 lines) = safe but review-worthy
• Review moderate/complex PRs for dependency relationships
```

### Technical Implementation

**Non-Destructive Batch Analysis**:
```python
def analyze_all_pending_prs(minor_version: str) -> List[AnalysisResult]:
    minor = Minor.from_yaml(minor_version)
    target_commit = repo.commit(minor_version)

    results = []
    for pr_data in minor.targeted_prs:
        if pr_data['is_merged'] and pr_data['master_sha']:
            # Conflict analysis (existing)
            analysis = analyze_cherry_pick_conflicts(minor_version, pr_data['master_sha'])

            # SHA size analysis (new)
            commit = repo.commit(pr_data['master_sha'])
            parent = commit.parents[0] if commit.parents else None

            sha_size = calculate_commit_size(parent, commit) if parent else {
                'files_changed': len(commit.stats.files),
                'lines_changed': commit.stats.total['lines']
            }

            results.append({
                'sha': pr_data['master_sha'][:8],
                'pr_number': pr_data['pr_number'],
                'title': pr_data['title'][:30],

                # SHA complexity (size of the change)
                'sha_files': sha_size['files_changed'],
                'sha_lines': sha_size['lines_changed'],

                # Conflict complexity (predicted conflicts)
                'conflict_files': len(analysis['conflicts']),
                'conflict_regions': sum(c.get('region_count', 0) for c in analysis['conflicts']),
                'conflict_lines': sum(c.get('conflicted_lines', 0) for c in analysis['conflicts']),
                'complexity': analysis['complexity']
            })

    return sorted(results, key=lambda x: (COMPLEXITY_ORDER[x['complexity']], x['sha_lines']))

def calculate_commit_size(parent_commit, commit) -> Dict[str, int]:
    """Calculate actual size of commit changes."""
    diff = parent_commit.diff(commit)
    files_changed = len(diff)

    lines_changed = 0
    for diff_item in diff:
        if diff_item.diff:
            # Count actual line changes (additions + deletions)
            diff_text = diff_item.diff.decode('utf-8', errors='ignore')
            lines_changed += len([line for line in diff_text.split('\n')
                                if line.startswith('+') or line.startswith('-')])

    return {'files_changed': files_changed, 'lines_changed': lines_changed}
```

### Key Benefits

**Strategic Cherry-Pick Planning**:
- Identify all "no-brainer" clean commits for bulk processing
- Spot complex PRs that need careful consideration
- See the full landscape before starting cherry-pick operations

**Efficiency Optimization**:
- Cherry-pick clean commits first to build momentum
- Save complex/conflicting PRs for focused attention
- Avoid getting stuck on difficult conflicts early in the process

**Risk Assessment**:
- Quantify the total complexity of remaining work
- Identify high-risk PRs that might need dependency analysis
- Plan cherry-pick sessions based on available time/complexity tolerance

### Important Considerations

**Out-of-Order Cherry-Picking**:
- Clean commits can be picked regardless of chronological order
- May create a "messier" git history but functionally equivalent
- Trade-off: cleaner workflow vs. pristine chronological history

**Dynamic Conflict Landscape**:
- Each cherry-pick changes the target branch state
- Earlier picks may make later ones easier OR harder
- Static analysis is a snapshot, not a prediction of future state
- Need to re-run analysis periodically as picks accumulate

**Workflow Integration**:
```bash
# Full analysis workflow
ct minor sync 6.0              # Ensure fresh state
ct minor analyze 6.0           # Get overview of all PRs
ct minor chain 6.0 --auto-clean # Auto-pick all clean commits
ct minor analyze 6.0           # Re-analyze remaining PRs
ct minor chain 6.0             # Interactive mode for remaining
```

### Advanced Features

**Filtering and Sorting**:
```bash
ct minor analyze 6.0 --complexity clean,simple  # Show only easy picks
ct minor analyze 6.0 --sort lines               # Sort by conflict lines
ct minor analyze 6.0 --format json             # Export for scripting
```

**Bulk Operations**:
```bash
ct minor analyze 6.0 --pick-clean              # Auto-execute all clean PRs
ct minor analyze 6.0 --pick-shas abc1234,def5678 # Pick specific SHAs
```

**Progress Tracking**:
- Show analysis delta between runs (how complexity changed)
- Track which PRs become easier/harder as others are picked
- Estimate remaining work complexity

### Sample Use Cases

**Release Manager Workflow**:
1. **Morning planning**: `ct minor analyze 6.0` to see the day's complexity
2. **Quick wins**: Pick all clean commits to build momentum
3. **Focus time**: Tackle moderate/complex PRs when fresh
4. **End-of-day**: Re-analyze to see progress and plan tomorrow

**Team Coordination**:
- Share analysis table in team chat: "12 clean PRs ready for auto-pick"
- Identify complex PRs that need developer consultation
- Plan pair-programming sessions around high-complexity changes

**Risk Management**:
- Before release deadline: Focus only on clean/simple commits
- Early in cycle: Tackle complex PRs when there's time to resolve issues
- Continuous monitoring: Watch for PRs that become more complex over time

This approach transforms cherry-picking from a linear, reactive process into a strategic, data-driven workflow where complexity is visible upfront and decisions can be made based on effort-vs-benefit analysis.
