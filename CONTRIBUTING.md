# Contributing

Thanks for helping improve project-blueprint. Bug reports, ideas, new stack notes, and fixes are all welcome.

## Getting set up

```
git clone https://github.com/ItzMeet2/project_blueprint_skill.git
cd project_blueprint_skill
pip install -r requirements-dev.txt
pytest -q
```

You need Python 3.10 or newer. `pytest` and `jsonschema` are development dependencies only. `mmdc` (mermaid-cli) is optional and makes the Mermaid validator stricter.

## Ground rules

- **Scripts are standard library only.** Anything under `project-blueprint/scripts/` may import only the Python standard library. If you think a dependency is needed, open an issue first; it would need a written justification in [docs/DESIGN_DECISIONS.md](docs/DESIGN_DECISIONS.md).
- **Scripts stay safe.** No network access, no executing analyzed code, no reading secret files (`.env`, `*.pem`, `*.key`, `secrets*`), no writing outside the output directory they are given.
- **Deterministic output.** The same input must give the same output. Do not add timestamps or random ids to generated files.
- **Cross-platform paths.** Use `os.path` or `pathlib`; scripts must work on Windows, macOS, and Linux.
- **No invented claims.** Do not add benchmark numbers, install steps, or UI menu names you have not verified. If you cannot verify something, say so in the text.
- **Instructions explain why.** In `SKILL.md` and `references/`, give the reason behind a rule, and keep `SKILL.md` short; detail belongs in the references.

## Making a change

1. Open an issue for anything larger than a small fix, so we can agree on the approach.
2. Create a branch and make your change with tests. Every script change needs a happy-path test and failure-case tests.
3. Run the checks:
   ```
   pytest -q
   python project-blueprint/scripts/validate_mermaid.py README.md docs project-blueprint examples
   ```
4. If you changed `SKILL.md`, a reference, or the description, check the affected prompts in [evals/README.md](evals/README.md) by hand, especially if you changed the description (it controls triggering).
5. Update [CHANGELOG.md](CHANGELOG.md) under "Unreleased".
6. Open a pull request that says what changed and why, and what you ran.

Use [conventional commit](https://www.conventionalcommits.org/) messages: `feat:`, `fix:`, `docs:`, `test:`, `ci:`, `chore:`.

## Common contributions

- **A stack note:** add or correct a section in `project-blueprint/references/stack-notes.md`. Mark anything you have not verified as "verify".
- **An extractor:** add a separate function in `analyze_project.py`, mark every item `inferred: true`, make failures log a warning instead of crashing, and add a test with a small fixture.
- **A wireframe element type:** update the renderer, `wireframe.schema.json`, the element table in `references/wireframes.md`, and the tests together.
- **A new eval:** see "Adding an eval" in [evals/README.md](evals/README.md).

## Reporting bugs and ideas

Use the issue templates. For a bug, include the agent and model you used, your operating system, your Python version, the prompt, and any script error output. Do not paste secrets or private code.

## License

By contributing you agree that your contributions are licensed under the [MIT License](LICENSE).
