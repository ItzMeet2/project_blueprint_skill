# Working rules

- Build one step at a time; stop after each step and wait for the user.
- docs/SPEC.md is the source of truth. If something is unclear or contradictory, ask instead of guessing.
- Scripts under project-blueprint/scripts use Python 3.10+ standard library only. Tests may use pytest.
- Never fabricate claims, benchmarks, or install instructions.
- Never read or print secrets or .env files.
- After each step: run the checks, update PROGRESS.md, make one git commit using conventional commits.
- Step prompts live in docs/BUILD_PROMPTS.md.
