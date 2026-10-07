# Evals

`evals.json` holds 8 test prompts for the `project-blueprint` skill: 7 that should trigger it and 1 that should not. Each has concrete expectations you can check by looking at the agent's output. They are run by hand, and nothing in this repo automates them or scores a model. `tests/test_evals.py` only checks that the file is well formed.

| Id | Scenario | Should trigger |
|----|----------|----------------|
| 1 | Analyze a .NET MVC project and make wireframes | yes |
| 2 | Idea only: interview path | yes |
| 3 | Wireframes for a mobile app | yes |
| 4 | Flowchart of the auth flow | yes |
| 5 | Three-sprint plan with dependencies | yes |
| 6 | PRD from a README | yes |
| 7 | Vague prompt ("help me figure out what to build first") | yes |
| 8 | Negative case: fix a null reference bug | no |

## How to run an eval

1. **Install the skill** in the agent you are testing. Copy the `project-blueprint/` folder (the one containing `SKILL.md`) to the agent's skills location. For Claude Code the spec names `~/.claude/skills/` for a personal install or `<repo>/.claude/skills/` for a project install (verify in the official docs). For Claude.ai, upload the packaged skill through its skills settings (verify the current steps in the official docs). For other agents, point the agent at `project-blueprint/SKILL.md` as instructions.
2. **Use a scratch copy of the inputs.** Copy any folder listed in the eval's `files` (for example `examples/sample-dotnet-mvc`) to a temporary location and work there, so the generated `blueprint/` folder does not land in this repo.
3. **Start a fresh conversation** with the skill available and paste the eval's `prompt` exactly. Attach or point to the `files`. Do not add hints.
4. **Watch for triggering.** Note whether the agent used the skill. For eval 8 it must not.
5. **Compare with the expectations.** Go through the expectation list and mark each as met, partly met, or not met, using the files and the chat transcript as evidence. Where an expectation names a script, check that the script was really run (or that the agent said it could not run it) and look at its output.
6. **Record the result** in the table below, and note anything surprising.

Model output varies between runs. For a result you want to rely on, run the eval at least twice, and record the worse run. Re-run all evals after any change to `SKILL.md` or the references, especially a change to the `description`, because that controls triggering.

## Recording results

Copy this table into a new file (for example `evals/results/2026-01-15-claude-code.md`) or into an issue, and fill in one row per eval and run.

| Eval | Date | Agent and model | Triggered as expected? | Expectations met | Notes |
|------|------|-----------------|------------------------|------------------|-------|
| 1 |  |  |  | _ / 5 |  |
| 2 |  |  |  | _ / 5 |  |
| 3 |  |  |  | _ / 5 |  |
| 4 |  |  |  | _ / 4 |  |
| 5 |  |  |  | _ / 5 |  |
| 6 |  |  |  | _ / 5 |  |
| 7 |  |  |  | _ / 4 |  |
| 8 |  |  |  | _ / 4 |  |

If the skill under-triggers (evals 3, 4, 7) or over-triggers (eval 8), adjust the wording of the `description` in `SKILL.md` and run the evals again. Do not publish results you did not actually run.

## Adding an eval

Add an object to `evals.json` with a new unique `id`, a `prompt`, a `files` list (paths relative to the repo root, which must exist), `should_trigger`, and 3 to 5 expectations that someone else could check without guessing. Keep fixtures small and free of real personal data.
