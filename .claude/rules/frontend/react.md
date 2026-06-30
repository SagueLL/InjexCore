# Frontend React Rules

These rules apply to the InjexCore Dashboard frontend located in:

```txt
apps/dashboard/
```

The current app uses:

* Next.js App Router
* TypeScript
* Tailwind CSS
* shadcn/ui
* Recharts

## Current Frontend Structure

The dashboard uses the `src/` directory structure.

Use:

```txt
apps/dashboard/src/app/
apps/dashboard/src/components/
apps/dashboard/src/components/app/
apps/dashboard/src/components/ui/
apps/dashboard/src/lib/
apps/dashboard/src/lib/dashboard/
```

Do not create duplicate folders outside `src/`.

Avoid:

```txt
apps/dashboard/app/
apps/dashboard/components/
apps/dashboard/lib/
```

## Dashboard v0 Scope

Dashboard v0 is a simple industrial intelligence MVP.

It should be:

* demo-ready;
* clear for a non-technical industrial stakeholder;
* focused on operational intelligence;
* built step by step;
* easy to extend later.

It should not be:

* a full SaaS application;
* an admin panel;
* an authentication system;
* a real-time industrial SCADA;
* a complex design system;
* a generic analytics template.

## Required Dashboard Views

The planned Dashboard v0 views are:

```txt
/overview
/timeline
/sensor-health
/drift-anomaly
/incidents
```

Incident detail may be added later when the incidents list and data shape are clearer:

```txt
/incidents/[incidentId]
```

Do not create this route unless explicitly requested.

## App Router Rules

Use the Next.js App Router.

Route files live in:

```txt
src/app/
```

Each route should stay thin.

Route pages should mainly compose components and pass data.

Avoid putting large UI logic directly inside `page.tsx`.

Good:

```tsx
export default function OverviewPage() {
  return (
    <div className="space-y-6">
      <PageHeader title="Executive Overview" />
      ...
    </div>
  )
}
```

Avoid:

```tsx
export default function OverviewPage() {
  // huge data mapping
  // huge inline UI
  // chart config
  // table config
  // utility functions
}
```

## Components

Use small, focused components.

Recommended component areas:

```txt
src/components/app/
```

For application shell components:

```txt
app-shell.tsx
sidebar-nav.tsx
page-header.tsx
topbar.tsx
```

Later, when needed:

```txt
src/components/dashboard/
src/components/charts/
src/components/tables/
```

Do not create these folders before they are needed.

## shadcn/ui

shadcn/ui components live in:

```txt
src/components/ui/
```

Do not manually rewrite shadcn/ui internals unless required.

Use shadcn/ui for primitives such as:

```txt
button
card
badge
table
tabs
select
separator
dropdown-menu
scroll-area
```

Only add shadcn components when needed by the current step.

Do not install a large batch of components preemptively.

## Styling

Use Tailwind CSS.

Prefer consistent spacing and simple layouts.

Use:

```txt
space-y-*
grid
flex
rounded-lg
border
bg-background
bg-muted
text-muted-foreground
```

Avoid excessive custom CSS.

Avoid hardcoded one-off visual hacks.

Do not introduce custom themes before the base dashboard works.

## Server and Client Components

Default to Server Components.

Only use `"use client"` when required for:

* interactivity;
* hooks;
* browser APIs;
* Recharts charts;
* client-side state;
* event handlers.

Do not add `"use client"` to layout or pages unless necessary.

## Data Flow

For the first phase, pages can use static placeholder content.

Do not implement real backend integration yet.

Do not read Parquet files directly from the frontend.

Later, dashboard data should come from dashboard-ready JSON exports produced by the backend/intelligence layer.

Preferred future direction:

```txt
Python intelligence outputs
      ↓
dashboard-ready JSON
      ↓
Next.js dashboard
```

## Charts

Use Recharts only when the base layout and shared components exist.

Charts should be isolated in dedicated components.

Do not put chart code directly inside route pages.

Charts will likely require `"use client"`.

Keep chart components focused and reusable.

## Industrial UX Rules

The dashboard must communicate operational meaning, not only technical metrics.

Prefer labels like:

```txt
Operational status
Sensor health
Drift detected
Anomaly windows
Affected signals
Incident evidence
Data quality notes
```

Avoid overly academic or vague labels like:

```txt
Model output
Score thing
Data stuff
Algorithm result
```

Use honest language.

Do not claim exact failure prediction unless the data and model support it.

Prefer:

```txt
Early deviation detection
Operational drift
Anomaly evidence
Sensor reliability
Incident aggregation
```

Avoid:

```txt
Guaranteed failure prediction
Automatic root cause
Real-time plant optimization
```

## Minimalism Rule

For every new file, ask:

```txt
Is this file needed for the current step?
```

If not, do not create it.

For every new component, ask:

```txt
Will this be reused soon or does it make the page clearer now?
```

If not, keep the code inline for the moment.

## Review Checklist

Before finishing frontend work:

* Routes are navigable.
* Components are small.
* No duplicate app/components/lib folders outside `src/`.
* No unnecessary `"use client"`.
* No unnecessary dependencies.
* No unused imports.
* No overbuilt design system.
* UI language matches industrial intelligence positioning.
