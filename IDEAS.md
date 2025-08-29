# IDEAS.md - Experimental & Unsolved Problems

This file contains experimental features, complex problem statements, and ongoing research for Cherrytree v2.

## 🚧 EXPERIMENTAL COMMANDS

### `ct analyze` - Bulk Conflict Analysis
**Status**: Conceptual design complete, needs implementation
**Problem**: Need strategic overview of ALL pending PRs before starting cherry-pick workflow

**Proposed Solution**: Static bulk analysis showing conflict predictions for every PR in a sortable table:

```
Cherry-Pick Analysis: Current Branch
Total PRs: 47 | Clean: 12 | Simple: 18 | Moderate: 11 | Complex: 6

┌─────────┬────────────┬─────────────────────────┬──────────────┬────────────┐
│ SHA     │ PR#        │ Title                  │ Size         │ Complexity │
│         │            │                        │ Files│Lines │            │
├─────────┼────────────┼────────────────────────┼──────┼──────┼────────────┤
│ abc1234 │ #34821     │ fix: typo in docs      │   1  │   3  │ clean      │
│ def5678 │ #34822     │ test: add coverage     │   2  │  45  │ clean      │
│ ghi9012 │ #34823     │ feat: loading spinner  │   4  │  67  │ simple     │
│ pqr1234 │ #34826     │ feat: new dashboard    │  15  │ 456  │ complex    │
└─────────┴────────────┴────────────────────────┴──────┴──────┴────────────┘
```

**Benefits**: Strategic planning, bulk clean commit processing, risk assessment

### `ct chain` - Interactive Cherry-Pick Workflow
**Status**: Implemented but experimental, needs real-world validation
**Problem**: Cherry-picking blindly leads to conflicts; need intelligent guidance

**Current Implementation**:
- GitPython-based conflict analysis (replaced unreliable text parsing)
- Oldest-first PR processing (dependency-friendly order)
- Interactive 4-option menu: Proceed, Show diff, Skip, Abort
- Safety checks: branch verification, sync validation, state detection

**Known Issues**:
- Conflict prediction accuracy needs validation
- Diff display shows metadata instead of line changes
- Blame analysis shows wrong commits (target branch vs dependencies)

**Next Steps**: Improve prediction accuracy, fix diff display, enhance blame analysis

### `ct analyze-next` - Single PR Analysis
**Status**: Basic implementation, accuracy concerns
**Problem**: Want conflict prediction for next PR without git state changes

**Technical Approach**:
- GitPython three-way analysis (parent → cherry → target)
- File-level conflict detection with line estimates
- Blame analysis of recent commits touching conflicting files

**Validation Results**:
- PR #34871 predicted "clean" but actually had conflicts
- Root cause: Static analysis limitations vs real merge complexity

## 🧩 COMPLEX PROBLEM STATEMENTS

### Dependency Graph Construction
**Core Challenge**: Build commit dependency graphs without mutating repository state

**The Problem**: Cherry-picking fails when target commit depends on other commits not yet in release branch. Current manual approach is time-consuming and error-prone.

**Proposed Technical Architecture**:
1. **Simulate Cherry-Pick**: Use `git merge-tree` for conflict analysis
2. **Identify Conflicting Lines**: Parse output to locate conflict regions
3. **Trace Dependencies**: Use `git blame` to identify source commits
4. **Recursive Analysis**: Build dependency tree
5. **Complexity Thresholds**: Apply bailouts to prevent infinite recursion

**Key Insight**: Git provides non-destructive merge simulation:
```bash
git merge-tree $(git merge-base target commit) commit target
```

**Complexity Thresholds**:
- Maximum dependency depth: N levels
- Commit count limits: M commits
- File scope boundaries: X files
- Author diversity tracking

### Intelligent Conflict Resolution
**Two Approaches Under Consideration**:

#### Approach 1: Interactive Deterministic Tool
```bash
ct conflict analyze abc123d
→ Found 3 dependency conflicts:
  • sha1: fix API endpoint (alice) - 9 lines, 3 files
  • sha2: rename utility (bob) - 2 lines, 1 file
  • sha3: add validation (charlie) - 15 lines, 5 files

ct conflict pick abc123d --interactive
→ Recommended resolution order: sha2 → sha1 → abc123d
```

#### Approach 2: AI-Assisted Agent
```yaml
role: "Apache Superset cherry-pick conflict resolution specialist"
workflow:
  1. analyze_conflict: Parse merge-tree, classify complexity
  2. strategy_selection: Recommend resolution order
  3. execution: Execute with validation checkpoints
bailout_conditions:
  - Dependency depth > 5 levels
  - Total commits > 10
  - Cross-team conflicts
  - Estimated time > 2 hours
```

### Master → Release Branch Ordering Logic
**Critical Discovery**: Git log order matters enormously for conflict reduction

**Problem**: PRs have complex dependencies that aren't obvious from timestamps

**Solution**: Process in **oldest-first** order based on master branch sequence:
```bash
git log master --reverse --grep="#[0-9]"
# Returns: PR #100 → PR #101 → PR #102 (dependency-friendly)
```

**Why This Works**:
- Dependencies flow forward in time
- Newer PRs often use utilities/patterns from older ones
- Cherry-picking dependencies first prevents conflicts
- Matches incremental development workflow

**Example**: PR #102 adds feature using utility functions from PR #101. Cherry-picking #101 first makes #102 clean.

## 🔬 ONGOING RESEARCH

### GitHub API Performance Optimization Journey
**Solved Problem**: From N+1 timeout to 30-second sync

**Evolution**:
1. **Started**: N+1 API calls (1 search + N individual PR calls) → timed out
2. **Problem**: Individual PR details for merge commit SHA too slow
3. **Solution**: Git log parsing for PR→SHA mapping
4. **Final**: 1 GitHub search + 1 git log parse = complete data

**Key Learnings**:
- `base:master` filter essential (excludes feature branch PRs)
- Dual search strategy: `is:open` + `is:merged` (excludes abandoned)
- Pagination with progress indicators improves UX

### Git Commit Message Pattern Analysis
**Apache Superset Findings**:
- **100% parentheses format**: `(#12345)` at commit message end
- **Revert commits**: `Revert "fix: something (#28363)" (#28567)` → want outer PR
- **Regex solution**: `re.findall(r'\(#(\d+)\)')` + take last match
- **Success rate**: 192/192 PRs found (100% for actionable PRs)

### Conflict Prediction Accuracy Research
**Current Status**: Mixed results, needs refinement

**GitPython Approach**:
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

**Validation Issues**:
- Static analysis misses complex merge scenarios
- Rename detection needs improvement
- Binary file handling edge cases
- Line count estimates are heuristic-based

**Research Directions**:
- Three-way merge simulation accuracy
- Machine learning on historical conflict patterns
- Integration with external merge tools
- Conflict resolution templates

### Data Structure Evolution
**YAML Schema Refinement**:

**Final Structure**:
```yaml
release_branch:
  minor_version: "6.0"
  base_sha: "1f482b42"  # 8-digit merge-base
  base_date: "2025-08-18 14:04:26 -0700"

  targeted_prs:
    - pr_number: 34871
      master_sha: "836540e8"  # 8-digit for cherry-picking
      is_merged: true         # Boolean: ready or needs merge

  micro_releases:
    - version: "6.0.0rc1"
      tag_sha: "a5f7d236"
      tag_date: "2025-08-18T14:04:26-0700"    # When tagged
      commit_date: "2025-08-18T14:04:26-0700" # When coded
```

**Key Simplifications**:
- No labels array (we know PRs have target label)
- No status field (`is_merged` tells whole story)
- 8-digit SHAs (75% space reduction)
- Chronological integrity preserved

## 🔄 ITERATIVE IMPROVEMENTS

### Diff Display Enhancement
**Current Problem**: "Show diff" shows metadata, not actual changes

**User Expectation**: Line-by-line `+/-` diff content
**Current Reality**: Commit stats with ANSI color codes

**Solution**:
```bash
git show --no-color --no-stat <sha>  # Clean line-by-line changes
```

### Blame Analysis Refinement
**Current Limitation**: Shows commits in target branch, not potential dependencies

**More Useful**: Show commits between cherry-pick and target that touched same files
```python
blame_info = {
    "target_branch_commits": current_blame_analysis(),
    "potential_dependencies": find_commits_between(cherry, target, file_path),
    "related_master_commits": find_related_work(cherry, file_path)
}
```

### Advanced Workflow Ideas
**Future Command Extensions**:
```bash
ct analyze --complexity clean,simple     # Filter by complexity
ct analyze --pick-clean                  # Auto-execute clean PRs
ct chain --auto-clean                    # Skip interactive for clean
ct conflict templates                    # Common resolution patterns
```

## 🎯 SUCCESS METRICS & VALIDATION

### Real-World Testing Results
**Apache Superset 6.0 Branch** (Active Release):
- Fresh branch cut Aug 18, 2025
- 1 micro release: 6.0.0rc1 with 1 commit
- 35 targeted PRs: 33 merged + 2 open
- Perfect chronological ordering maintained

**Performance Validation**:
- 4.0 branch: 195 PRs → 30-second sync
- 6.0 branch: 35 PRs → 10-second sync
- Git parsing: 5000 commit window, 100% success rate
- GitHub API: Dual search, no timeouts

### Architecture Success Factors
**Design Decisions That Worked**:
1. Git log chronological ordering (preserves dependencies)
2. 8-digit SHAs (readability + uniqueness balance)
3. Dual GitHub searches (eliminates noise at source)
4. YAML state files (versioned, reviewable, Claude-accessible)
5. Boolean simplicity (`is_merged` vs complex enums)

**Technical Breakthroughs**:
1. N+1 elimination (git log parsing vs API calls)
2. Revert commit handling (take last PR number)
3. Branch auto-checkout (user permission + exact commands)
4. Tag metadata richness (creation + commit dates)

## 🚀 NEXT PHASE READINESS

**Experimental Commands Ready for Development**:
- Cherry-pick execution with conflict detection
- Batch operations for bulk clean commits
- Enhanced dependency analysis and visualization
- Progress tracking with YAML state updates

**Research Areas Needing Investment**:
- Conflict prediction accuracy improvement
- AI-assisted resolution strategy development
- Cross-repository pattern analysis
- Integration with external merge tools

The experimental foundation provides promising directions for advanced cherry-pick workflows, though significant validation and refinement work remains!
