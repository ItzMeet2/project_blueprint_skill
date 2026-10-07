# Changelog

All notable changes to this project are documented here. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - Unreleased

### Added

- The `project-blueprint` skill: `SKILL.md` with a four-phase workflow, routing table, output contract, and failure handling.
- Seven reference guides: analysis, stack notes, wireframes, diagrams, sprints, requirements, and a quality checklist.
- `analyze_project.py`: scans a project (languages, stack markers, key folders, entry points) and extracts routes, screens, and entities with lightweight patterns. Never reads secret files.
- `render_wireframe.py`: renders a JSON wireframe spec to grayscale SVG for 21 element types, an optional HTML gallery with light and dark variants, and a screen-flow Mermaid diagram.
- `validate_mermaid.py`: heuristic Mermaid checks for Markdown and `.mmd` files, with optional `mmdc` parsing.
- `export_sprint.py`: parses and validates sprint-plan tables and exports CSV and JSON.
- JSON schemas for the project profile and the wireframe spec, plus templates for PRDs, user stories, ADRs, and sprint plans.
- A fake ASP.NET MVC sample project and the full output the skill generated for it.
- Eight eval prompts with expectations, including a negative case.
- A pytest suite for the scripts, schemas, `SKILL.md`, and evals.
- Documentation: README, architecture notes, design decisions, and contributing guide.
