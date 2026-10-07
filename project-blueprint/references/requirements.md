# Requirements: user stories, PRD, ADRs

Read this file when the user wants user stories, acceptance criteria, a PRD, a project brief, requirements, scope, or architecture decision records. Everything here is generated from `blueprint/profile.json`, so the same screens, entities, and ids appear in every artifact. Use the templates in `assets/templates/` (`user-story.md`, `prd.md`, `adr.md`).

## Contents

1. User stories
2. Acceptance criteria (Given/When/Then)
3. Prioritization (MoSCoW)
4. PRD
5. ADRs
6. Numbering and file conventions

## 1. User stories

Format:

> As a **\<actor\>**, I want **\<capability\>**, so that **\<benefit\>**.

Rules:
- **Actor** comes from `profile.actors`. If the profile has none, derive one from the code (roles, auth) or the user's words and mark it `ASSUMPTION:`.
- **Capability** is one thing a user can do, stated from the user's side ("I can add a book"), not an implementation detail ("the controller saves a row").
- **Benefit** says why it matters. If you cannot name a benefit, the story may not be needed.
- **Trace every story** to the profile: name the screen id(s) and route(s) it covers (for example screen `books-create`, route `POST /books/create`). Why: traceability shows what the code already does and what is new.
- **Do not invent features.** Stories describe behavior that the code or the user's request supports. Proposed additions are labeled `ASSUMPTION:`.
- Keep stories small enough to estimate at 8 points or less (see `sprints.md`).
- One file holds all stories: `blueprint/requirements/user-stories.md`, using the template block per story.

## 2. Acceptance criteria (Given/When/Then)

Each story has **at least 2 criteria, and at least one must be a negative case** (what happens when input is wrong, missing, or not allowed).

Pattern: **Given** a starting state, **when** the user does one action, **then** one observable result.

Example for "As a reader, I can sign in":
1. **Given** a registered reader on the login page, **when** they submit the correct email and password, **then** they land on My Books.
2. **Given** a registered reader on the login page, **when** they submit a wrong password, **then** they stay on the login page and see an error message. *(negative case)*

Rules:
- One action in each "when"; one behavior per criterion.
- Observable and testable: name what the user sees (screen, message, data), not internal state.
- Use the real screen names and field names from the profile.
- In the sprint table the criteria go in one cell on one line; see `sprints.md`. Keep the full list in `user-stories.md`.

## 3. Prioritization (MoSCoW)

| Priority | Meaning |
|---|---|
| **Must** | The product fails without it; part of the first release |
| **Should** | Important, but a workaround exists |
| **Could** | Nice to have if time allows |
| **Won't** | Agreed to be out of scope for now (list it, do not schedule it) |

Rules of thumb: if everything is Must, nothing is; keep Must to roughly half the work or less. Ask the user to confirm Must items only when the choice changes the MVP scope.

## 4. PRD

Use `assets/templates/prd.md`; write to `blueprint/requirements/prd.md`. Sections, in order:

1. **Problem**: who has what problem, from the profile summary and the user's words.
2. **Goals and non-goals**: what success looks like, and what is explicitly out.
3. **Personas**: one row per actor.
4. **Scope**: MVP vs later.
5. **Functional requirements**: numbered `FR-001`, each a testable statement ("The system lets a reader add a book with title, author, and ISBN"), each with a MoSCoW priority.
6. **Non-functional requirements**: performance, security, accessibility, only those the project actually implies.
7. **Success metrics**: how the owner will know it worked. Do not invent numeric targets; propose them as `ASSUMPTION:` or leave them as open questions.
8. **Open questions**: everything you could not determine.
9. **Risks**: from `profile.risks`, with impact and mitigation.

Write about what exists or was requested. For an existing codebase, describe the current product and clearly separate "implemented" from "proposed".

## 5. ADRs

An architecture decision record captures one significant decision and why it was made. Use `assets/templates/adr.md`.

- **When to write one:** a choice that is expensive to reverse and that a newcomer would wonder about (database, framework, auth approach, hosting, a major library). Skip small choices.
- **Existing code:** record decisions visible in the code (for example "uses SQL Server with EF Core"). If the *reason* is not stated anywhere, write `ASSUMPTION:` for the context and say that the rationale was inferred.
- **Status:** `Proposed`, `Accepted`, `Deprecated`, or `Superseded`. A decision found in running code is normally `Accepted`.
- **Alternatives:** list at least one realistic alternative and why it was not chosen. If none is known, say so; do not make one up.
- **Consequences:** include both benefits and costs.
- One decision per file; never edit an accepted ADR to change history, write a new one that supersedes it.

## 6. Numbering and file conventions

| Item | Pattern | Example |
|---|---|---|
| User story | `US-001`, three digits, never reused | `US-007` |
| Functional requirement | `FR-001` | `FR-012` |
| Non-functional requirement (optional convention) | `NFR-001` | `NFR-003` |
| ADR | four digits in the filename and title | `adr/0001-use-sql-server.md`, title `ADR 0001` |

Files, inside `blueprint/requirements/`: `prd.md`, `user-stories.md`, `adr/0001-<slug>.md`. The slug is lowercase-kebab.

Every generated markdown file starts with the generated-by header, date, and profile hash described in the output contract in `SKILL.md`. Never overwrite an existing file: if it exists, ask, or write the new version with a `-v2` suffix.
