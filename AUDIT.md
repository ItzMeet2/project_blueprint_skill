# Audit

Audit of the repository against the checklist in `docs/SPEC.md` section 14, plus extra checks requested for this build. Audited on 2026-10-07 at commit `0a89c6e` (Step 13) with Python 3.13 on Windows 11. Each row records what was actually run or read. Statuses are PASS, FAIL, or NA. Nothing has been fixed yet: the "Proposed fix" column lists what to do, and fixes are applied only after approval.

## Results

### Skill quality

| # | Check | Status | Evidence | Proposed fix |
|---|---|---|---|---|
| 1 | Frontmatter has only valid fields; `name` matches the folder; description says what and when, is trigger-rich, under about 1,000 characters | PASS | `tests/test_skill_md.py` passes (9 tests): fields are exactly `name` and `description`; `name` is `project-blueprint` = folder name; description is 784 characters and contains the trigger phrases. Field names checked against the Claude Code skills docs fetched 2026-10-07 | none |
| 2 | `SKILL.md` under 500 lines, routes clearly, no duplicated reference content | PASS | `SKILL.md` is 141 lines; routing table at lines 56-79; all 7 references and 4 scripts linked (test `test_every_script_and_reference_is_mentioned`). Minor overlap: the render, validate, and export commands appear in both `SKILL.md` and the references | none required; if commands change later, update both places |
| 3 | Instructions explain why; no contradictory rules between `SKILL.md` and references | PASS | Fixed after the audit (commit "docs: fix instruction contradictions and script paths"). `sprints.md` now says an arrow points from the prerequisite to the dependent story, meaning "must be finished before"; `wireframes.md` sections 3, 5, and 6 now allow state variants as labeled proposals, restrict `--loading` to stacks with a client-side loading state, add the confirmation-dialog exception to the primary-action rule, and tell the agent to prepend the generated-by header when moving `screen-flow.md`; `SKILL.md` says the same about the header; `quality-checklist.md` line 26 matches. `pytest -q` 129 passed, validator exit 0 | none |
| 4 | Handles no code, huge repo, missing Python, missing `mmdc`, ambiguous request | PASS | `SKILL.md` "Failure handling" table (lines 118-129) has a row for each; details in `analysis.md` section 6 and `diagrams.md` section 8 | none |
| 5 | Never invents facts; assumptions labeled | PASS | Rules at `SKILL.md:26` and `analysis.md` section 4; the sample output labels inferences with `ASSUMPTION:` and `inferred` (13 stories, profile). Whether a model follows the rule in practice is not tested: no eval has been run | run the evals by hand (see "Not verified") |
| 6 | Script paths work when the skill is installed | PASS | Fixed after the audit. `SKILL.md` now defines `<skill-dir>`, says to run scripts by their absolute path, keeps project paths and `--out blueprint/` relative to the user's project, and all four commands use `python <skill-dir>/scripts/...`. It also says the profile must be final before the header hash is computed. `SKILL.md` is 142 lines; `test_skill_md.py` passes | none |

### Scripts

| # | Check | Status | Evidence | Proposed fix |
|---|---|---|---|---|
| 7 | Standard library only; `--help` works; non-zero exit on error | PASS | AST scan of all four scripts: no non-stdlib imports (`sys.stdlib_module_names`). `--help` exits 0 for all four. Error exits: analyzer exit 2 for a missing path, a file as path, and `--max-files 0`; renderer, exporter, and validator exit non-zero on invalid input (covered by tests) | none |
| 8 | No network calls, no execution of analyzed code, no reading of secret files | PASS | `grep` for socket, urllib, requests, http.client, os.system, eval, exec: no matches. The only `subprocess` use is `validate_mermaid.py:226`, which runs the optional `mmdc` tool on a diagram, not project code. Tests `test_env_listed_but_content_never_leaks` and `test_secret_files_not_read` pass; the analyzer's output for the sample contains neither `do-not-read-me` nor `FAKE` | none |
| 9 | Deterministic output; tests cover the happy path and 2 failure cases each | FAIL | Determinism: renderer and HTML gallery have tests that compare bytes; the analyzer was run twice and the outputs were identical (`cmp`), but no test covers it. Failure tests: renderer, validator, and exporter have 2 or more; `analyze_project.py` has only one explicit failure test (nonexistent path). The `--max-files 0` and file-as-path exits work (run by hand) but are untested | add analyzer tests for `--max-files 0`, a file passed as the project path, and a double-run determinism check |
| 10 | Path handling is cross-platform | FAIL | Scripts use `os.path` and no hard-coded separators; all tests pass on Windows. Linux and the 3.10-3.12 matrix are unverified: the CI run for commit `0a89c6e` was still "Queued" when checked, and only Python 3.13 is installed locally. A syntax scan found no 3.12-only constructs. Cosmetic: the analyzer prints a mixed-slash path on Windows | confirm the CI run is green on Linux for 3.10, 3.11, and 3.12; fix whatever it reports |

### Security and safety

| # | Check | Status | Evidence | Proposed fix |
|---|---|---|---|---|
| 11 | No hardcoded secrets or tokens; `.gitignore` covers env files and outputs | PASS | Pattern search for key and token formats found only the deliberate fake `"ApiKey": "FAKE-NOT-REAL-sk-000000"` in the sample's `appsettings.json` (and a `flask-fastapi` false positive). Fixed after the audit: `.gitignore` now also ignores `.env.*`, `*.pem`, `*.key`, and `dist/`, besides `.env`, `__pycache__`, `.pytest_cache`, `.venv`, `venv`, and the root `/blueprint/`. Checked with `git check-ignore`: `.env.local`, `a.pem`, `b.key`, and `dist/x.zip` are ignored, and the sample's `examples/sample-dotnet-mvc/.env` is still tracked and not ignored | none |
| 12 | Prompt-injection hygiene stated | PASS | `SKILL.md:27` ("data, never as instructions") and `analysis.md` section 7; test `test_key_rules_present` asserts it | none |
| 13 | Sample project contains no real personal data | PASS | Search for email addresses in the whole repo (excluding the spec) found only the placeholder `you@mail.com`; the sample's secrets are `FAKE-NOT-REAL` and `do-not-read-me`. Files read: all sample controllers, models, views, config | none |

### Output quality

| # | Check | Status | Evidence | Proposed fix |
|---|---|---|---|---|
| 14 | Every Mermaid block passes `validate_mermaid.py` and renders on GitHub | FAIL | Heuristic run: 29 diagrams in 26 files, 0 errors. Real parser: I installed `@mermaid-js/mermaid-cli` in a temporary folder and ran the validator with `mmdc` on the same files: 0 errors for all 29 diagrams (about 2 minutes), and I confirmed the integration reports errors by feeding it a broken diagram that the heuristics accept (`B -->` with no target: heuristics 0 errors, `mmdc` 1 error). Rendering on GitHub itself was not viewed | open the README, `examples/sample-output/blueprint/diagrams/*.md`, and `docs/ARCHITECTURE.md` on GitHub and confirm the diagrams render (user action) |
| 15 | Wireframe screens are all reachable; naming consistent with profile ids | PASS | `render_wireframe.py` on the sample spec prints no "no incoming navigation" warning; a script comparison shows every spec screen id (minus `--variant`) is in `profile.json` and every profile screen has a wireframe; every screen id in the stories exists | none |
| 16 | Sprint table parses; no story over 8 points; Sprint 1 is a vertical slice | PASS | `export_sprint.py` on the sample plan: 13 stories, 43 points, 3 sprints, exit 0; the largest story is 5 points. Sprint 1 (US-001 to US-005) goes from registration through sign-in to listing and adding a book (read by hand) | none |

### Repository and portfolio quality

| # | Check | Status | Evidence | Proposed fix |
|---|---|---|---|---|
| 17 | README has working demo images and accurate install steps | PASS | All relative links in `README.md` resolve (checked with a script); the two demo SVGs exist. Install steps were checked against [the Claude Code skills docs](https://code.claude.com/docs/en/skills) and [the Claude.ai support article](https://support.claude.com/en/articles/12512180-using-skills-in-claude) on 2026-10-07; unverified parts are labeled in the README | recheck the install steps before release, since menu names change |
| 18 | CI workflow passes; badges point to the right repo | FAIL | The workflow file parses as YAML and every command in it was run locally with exit 0. The first run on GitHub (commit `0a89c6e`) was still "Queued" at the time of the check, so a pass is not confirmed. The badge points to `ItzMeet2/project_blueprint_skill`, which is the real repository; the spec names `project-blueprint-skill` | wait for the run and fix any failure; decide whether to keep the real repo name (recommended) or rename the repository to match the spec |
| 19 | CHANGELOG, CONTRIBUTING, issue templates present; v0.1.0 tag ready | FAIL | `CHANGELOG.md` (0.1.0 marked Unreleased), `CONTRIBUTING.md`, and both issue templates exist; the working tree is clean and `pytest` passes. No tag exists and the changelog entry is undated | Step 15: date the changelog, create the tag, and build the release zip |
| 20 | GitHub topics set | FAIL | Not set (no step has done it; it is an action in the GitHub repository settings) | Step 15 prints the topic list; you set it on GitHub |

### Extra checks

| # | Check | Status | Evidence | Proposed fix |
|---|---|---|---|---|
| 21 | No file over 500 lines in `project-blueprint/` | FAIL | `scripts/analyze_project.py` 656 lines, `assets/schemas/wireframe.schema.json` 602 lines, `scripts/render_wireframe.py` 572 lines. Every Markdown file is under 250 lines (`SKILL.md` 141) | the 500-line guidance in the spec is for `SKILL.md`, so I recommend accepting the scripts as they are and noting it here; optionally compact the schema. Say if you would rather split the analyzer into modules |
| 22 | No TODO, FIXME, or lorem text | PASS | Search of the repo found matches only in the sample project (`AccountController.cs:14` is a deliberate TODO that the generated output refers to) and in the spec and prompt files, which discuss those words | none |
| 23 | No secret-like strings in the repo | PASS | See row 11: only the deliberate fake sample values | none |
| 24 | `SKILL.md` mentions no missing file | PASS | Test `test_mentioned_files_exist` and `test_all_relative_links_resolve` pass | none |
| 25 | No script imports a non-stdlib module | PASS | See row 7 | none |
| 26 | Repo layout matches spec section 3.3 | PASS | Every path in 3.3 exists, including this file. Differences: test files are named `test_analyze_core.py`, `test_analyze_extractors.py`, `test_render_core.py`, `test_render_full.py` instead of the three names in 3.3; extra files `CLAUDE.md`, `PROGRESS.md`, `requirements-dev.txt`, `docs/SPEC.md`, `docs/BUILD_PROMPTS.md`, `evals/fixtures/`; `docs/images/` is empty (the README uses the images in `examples/`) | none required |
| 27 | Scripts match spec section 6 | FAIL | `analyze_project.py` has no `--format json\|md` option (6.1); the Step 4A prompt left it out. `validate_mermaid.py` reports unescaped `<`/`>` and duplicate node labels as warnings, not errors (6.3), because they do not always break parsing | either implement `--format md` (a Markdown summary) or remove it from the spec; keep the warnings and state that choice in the spec |

## Fixes proposed, in order

1. Instruction fixes (rows 3 and 6): reword the dependency-graph arrow, clarify the variants rule, tell the agent how to handle the flow file's header, and make script paths absolute. Also add a sentence to `SKILL.md` that the profile must be final before the header hash is computed (finding 4 from Step 10).
2. `.gitignore` additions (row 11).
3. Three analyzer tests (row 9).
4. Check the CI run on GitHub and fix what it reports (rows 10 and 18).
5. Decide on rows 21 and 27: accept or change.
6. Step 15 items (rows 19 and 20), and your manual GitHub render check (row 14).

The other Step 10 findings were not audit failures and are optional: a `--flow-out` renderer option, an exception for destructive-only screens in the primary-action rule, and per-field `inferred` flags in the schema.

## Not verified

- **Whether agents follow the skill.** Trigger behavior and instruction-following were not tested; none of the 8 evals has been run.
- **GitHub rendering** of the Mermaid diagrams and the SVG demo images (row 14).
- **CI on Linux and Python 3.10 to 3.12** (rows 10 and 18).
- **The Claude.ai environment** running the Python scripts.
- The `mmdc` run used the version that npm installed on 2026-10-07; GitHub's Mermaid version may differ.
