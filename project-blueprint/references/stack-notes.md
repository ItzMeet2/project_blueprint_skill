# Stack notes

Read the section for each stack the scan reports (`stack` and `languages` in `analysis.raw.json`) while reading key files in Phase 2. Each section says where screens, routes, and models usually live, what the scanner misses, and what to ask the user. Anything marked **verify** is from general knowledge, not checked against the current official docs or the scanner's code: confirm it in the project before relying on it.

## Contents

1. .NET MVC / .NET Core
2. Node / Express
3. Next.js
4. Python (Flask, FastAPI, Django)
5. Unity / C#
6. Flutter
7. Android / Kotlin

General rule for all stacks: the scanner finds names with patterns. When a stack uses indirection (mounted routers, URL config files, generated code), the real routes and models are in code the scanner does not parse. Read that code and correct the profile.

## 1. .NET MVC / .NET Core

Markers: `*.csproj`, `*.sln`, `Program.cs`, `Startup.cs`.

- **Screens:** `Views/<Controller>/<Action>.cshtml`. The scanner turns each into a screen id such as `account-login`. `Views/Shared/_Layout.cshtml` and other `_*.cshtml` files are layouts or partials, flagged `is_layout`; drop them. Areas keep views under `Areas/<Area>/Views/...`.
- **Routes:** controller classes with `[HttpGet]`, `[HttpPost]`, `[Route]`. Conventional routing is configured in `Program.cs` (`MapControllerRoute`). Minimal APIs use `app.MapGet(...)`.
- **Models:** `Models/`, `Entities/`, and `DbSet<T>` properties in the `DbContext` under `Data/`. Relations are often only in navigation properties or `OnModelCreating`; the scanner infers only `<Name>Id` foreign keys.
- **Config:** `appsettings.json` and `appsettings.*.json` hold connection strings and keys. Read structure only.
- **Pitfalls:**
  - The scanner does not read Razor Pages (`Pages/*.cshtml`) or Blazor (`*.razor`) as screens. Read them by hand if present.
  - An `[Route]` attribute on an action without an HTTP verb attribute is not picked up.
  - `[ApiController]` classes return data, not views; there is no screen for them.
  - Authorization (`[Authorize]`, roles) is the best source for `actors`.
- **Ask:** is this MVC with views, a Web API, or both? Which roles exist? Which database is production?

## 2. Node / Express

Markers: `package.json`, an entry file such as `server.js`, `app.js`, or `index.js`.

- **Routes:** `app.get('/x', ...)` and `router.post(...)`, usually in `routes/` or `controllers/`.
- **Screens:** often none in the server; the UI is a separate frontend (React, Vue, templates in `views/`). Check `package.json` for the frontend framework.
- **Models:** Mongoose schemas, Sequelize models, or `prisma/schema.prisma` (the scanner does not parse Prisma schemas; read the file).
- **Pitfalls:**
  - Routers mounted with `app.use('/api', router)` lose their prefix in the scan. Find the `app.use` lines and fix the paths.
  - TypeScript compiled output in `dist/` or `build/` is skipped by the scanner, which is correct; read `src/`.
  - Only paths written as string literals starting with `/` are found.
- **Ask:** where is the frontend, and is it in this repo? Which database? Is authentication session-based or token-based?

## 3. Next.js

Markers: `package.json` listing `next`, folders `app/` or `pages/` (possibly under `src/`).

- **Screens and routes:** in the App Router, each `app/**/page.*` is a page and `route.*` is an API endpoint. In the Pages Router, each file in `pages/` is a page and `pages/api/` holds endpoints. The scanner finds both, but only when `package.json` mentions `next`.
- **Pitfalls:**
  - Route groups like `(auth)` do not appear in URLs; the scanner strips them.
  - Dynamic segments such as `[id]` stay in the path and the screen id; rename screens for the user.
  - Server actions, middleware, and `next.config.js` rewrites change behavior without creating files. Read them if present (**verify** exact conventions for the Next.js version in use).
  - Data models usually live in `prisma/schema.prisma`, `types/`, or an ORM folder.
- **Ask:** which auth provider? Which backend or database? Any pages that exist only for admins?

## 4. Python (Flask, FastAPI, Django)

Markers: `requirements.txt`, `pyproject.toml`, `app.py`, `main.py`, `manage.py`.

- **Flask:** routes are `@app.route` or `@bp.route`; templates in `templates/` are the screens. The scanner reads route decorators but does not see blueprint `url_prefix` values; check where blueprints are registered.
- **FastAPI:** routes are `@app.get`, `@router.post`, and so on. The scanner does not see `include_router(prefix=...)`; check `main.py`. Response models are Pydantic classes, usually in `models/` or `schemas/`.
- **Django:** routes live in `urls.py` files (`urlpatterns`), which the scanner does **not** parse; read them. Views are in `views.py`, templates in `templates/`, models in `models.py`. The scanner recognizes classes deriving from `models.Model` but reports empty fields, because Django fields are assignments, not annotations; read `models.py` for the fields.
- **Pitfalls:**
  - Test files and folders named `test`/`tests` are skipped for route extraction on purpose.
  - Virtual environments (`venv`, `.venv`) are skipped; do not treat library code as the project.
  - Settings modules often hold secrets; read structure only.
- **Ask:** is there a frontend, or is this API-only? Which database? Who are the users and roles?

## 5. Unity / C#

Markers: a `ProjectSettings/` folder, `Assets/`, `*.unity` scene files, `Packages/manifest.json`.

- **Screens:** there are no views. Treat each scene (`Assets/Scenes/*.unity`) and each UI canvas or menu as a screen candidate. The scanner counts scene files but does not parse them (**verify** that scenes are text YAML in the project's serialization setting).
- **Flows:** game states (menu, play, pause, game over) are usually in `GameManager`-style scripts under `Assets/Scripts/`.
- **Models:** game data lives in `ScriptableObject` classes, `[Serializable]` classes, and save-data classes. The scanner only treats C# classes under `Models/`/`Entities/` folders or `DbSet<T>` as entities, so it will usually find none; read the scripts.
- **Pitfalls:** `Library/`, `Temp/`, and `obj/` are skipped by the scanner and should be. Generated and third-party code under `Assets/Plugins` or `Packages` is not the project's own logic.
- **Ask:** target platforms, core game loop in one sentence, single or multiplayer, and which systems exist (inventory, saving, shop).

## 6. Flutter

Markers: `pubspec.yaml`, `lib/main.dart`.

- **Screens:** widgets under `lib/screens/`, `lib/pages/`, or `lib/features/*` (naming varies; **verify** in the project).
- **Navigation:** `Navigator.push`, named routes in `MaterialApp`, or a router package such as `go_router` (**verify** which one `pubspec.yaml` lists). The scanner extracts no Dart routes, so build the navigation map by reading the router setup.
- **Models:** classes in `lib/models/`; JSON serialization may be generated code (`*.g.dart`), so read the source classes, not the generated ones.
- **Pitfalls:** state management (Provider, Bloc, Riverpod, and others) decides where logic lives; identify it from `pubspec.yaml` before describing flows. Platform folders (`android/`, `ios/`) are boilerplate.
- **Ask:** target platforms, backend (Firebase or custom API), offline requirements.

## 7. Android / Kotlin

Markers: `build.gradle` or `build.gradle.kts`, `AndroidManifest.xml`, `app/src/main/`.

- **Screens:** activities declared in `AndroidManifest.xml`; fragments; Jetpack Compose functions annotated `@Composable`; XML layouts in `res/layout/` for the older view system (**verify** which UI toolkit the project uses).
- **Navigation:** a navigation graph in `res/navigation/` or a Compose `NavHost` with route strings. The scanner does not extract any of these; read them.
- **Models:** Kotlin `data class` files, and Room `@Entity` classes for the local database (**verify** the persistence library in the Gradle files).
- **Pitfalls:** `build/` folders are skipped by the scanner. Multi-module projects split screens across modules; check `settings.gradle(.kts)` for the module list.
- **Ask:** minimum Android version, whether there is a backend, offline use, and which screens are the main flow.
