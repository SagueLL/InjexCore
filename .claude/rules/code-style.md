# InjexCore Code Style Rules

These rules apply to all InjexCore code unless a more specific rule file overrides them.

## General Principles

* Prefer small, explicit, maintainable changes.
* Do not over-engineer.
* Do not create files, folders, abstractions or dependencies unless they are clearly needed by the current task.
* Keep each change aligned with the current project phase.
* Prioritize clarity over cleverness.
* Prefer boring, predictable code over complex abstractions.
* Preserve existing architecture and naming conventions unless explicitly asked to refactor.

## Project Context

InjexCore is an Industrial Intelligence Layer for operational data.

The current frontend work belongs to Dashboard v0.

Dashboard v0 is not a full SaaS product yet. It is a demo-ready MVP used to explain industrial intelligence over real operational data.

The frontend should help translate technical outputs into clear operational understanding.

## Implementation Scope

When implementing a task:

* Only touch files required by the task.
* Do not create future-oriented folders or components unless requested.
* Do not implement authentication, user management, billing, multi-tenant SaaS logic or backend APIs unless explicitly requested.
* Do not add mock systems that are larger than the current frontend need.
* Do not rewrite working code without a clear reason.

## File Organization

Respect the current monorepo structure.

Frontend dashboard code lives in:

```txt
apps/dashboard/src/
```

Use this structure:

```txt
apps/dashboard/src/app/
apps/dashboard/src/components/
apps/dashboard/src/components/app/
apps/dashboard/src/components/ui/
apps/dashboard/src/lib/
apps/dashboard/src/lib/dashboard/
```

Do not create duplicate top-level folders such as:

```txt
apps/dashboard/app/
apps/dashboard/components/
apps/dashboard/lib/
```

unless the project has explicitly moved away from the `src/` structure.

## Naming

Use clear, descriptive names.

Prefer:

```txt
app-shell.tsx
sidebar-nav.tsx
page-header.tsx
kpi-card.tsx
severity-badge.tsx
```

Avoid vague names:

```txt
box.tsx
thing.tsx
helper.ts
misc.ts
new-component.tsx
```

## TypeScript

* Use TypeScript strictly.
* Avoid `any`.
* Prefer explicit types for exported functions, props and shared data structures.
* Keep types close to the feature until they become shared.
* Do not introduce complex generic types unless they provide clear value.

## Imports

* Prefer absolute imports using the configured alias when available.
* Keep imports organized and minimal.
* Remove unused imports.
* Do not introduce circular dependencies.
* UI components should not import from route files.

## Comments

* Do not add obvious comments.
* Add comments only when explaining business logic, industrial context, non-obvious decisions or known limitations.
* Prefer readable code over comments.

## Dependencies

* Do not add new dependencies unless the task explicitly needs them.
* Use existing project dependencies first.
* For dashboard UI, prefer existing stack:

  * Next.js
  * TypeScript
  * Tailwind CSS
  * shadcn/ui
  * Recharts

## Quality Gates

Before considering a task complete:

* Code should compile.
* TypeScript errors should be avoided.
* ESLint issues should be avoided.
* Unused files should not be created.
* The result should be easy to review in a small commit.

## Commit Discipline

Prefer small commits with focused scope.

Examples:

```bash
feat(dashboard): add minimal app shell and routes
feat(dashboard): add shared dashboard cards
feat(dashboard): implement overview demo view
```

Avoid large mixed commits that combine routing, charts, data contracts and styling in one step.
