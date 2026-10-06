# Brand and Visual System Reference

## 1. Purpose

This document defines visual and interaction constraints for consistent UI delivery across dashboard and Copilot experiences.

## 2. Design Principles

- Enterprise SaaS polish over internal-tool styling.
- Clean operational dashboards over decorative UI.
- High readability for dense technical data.
- Clear page hierarchy so first-time users can understand each surface without telecom shorthand.
- Strong emphasis on status clarity (healthy, warning, failed, running).
- Consistent behavior between table workflows and form workflows.

## 3. Core Tokens (Current Implementation)

Source: `app/globals.css`

## 3.1 Semantic Colors

- Background and surface
  - `bg-background`, `bg-card`, `bg-popover`
- Text
  - `text-foreground`, `text-muted-foreground`
- Borders and focus
  - `border-border`, `ring`, `focus-visible:ring-*`
- Action colors
  - `primary`, `secondary`, `destructive`, `accent`
- Status helpers (via badge variants)
  - `success`, `info`, `destructive`, `secondary`, `outline`

## 3.2 Typography

- App shell
  - `Open Sans` in dashboard layout.
- Root font variables
  - Geist Sans and Geist Mono are available globally.
- Guidance
  - Titles: semibold, clear hierarchy, paired with short layman-friendly subtitles on major pages
  - Data and IDs: use monospaced styling where helpful

## 3.3 Radius and Spacing

- Base radius token: `--radius`
- UI defaults
  - Inputs/buttons/cards use rounded surfaces with slightly softer enterprise treatment across buttons, badges, tables, and cards
- Spacing baseline
  - 4px scale with generous panel spacing in data-heavy views
  - Page sections should feel spacious rather than cramped

## 3.4 Shell Hierarchy and Surface Weight

- Sidebar remains the darkest persistent shell surface so navigation stays visually anchored without overpowering the content canvas.
- Topbar should read as a lighter utility band with brand presence, Copilot entry, notifications, and workspace/account controls.
- Primary page content should sit on the brightest neutral surface, with cards and tables using subtle borders instead of heavy shadows.
- Dense operational pages should separate information by spacing and card grouping first, not by introducing new background colors for every module.
- Repeated maintenance controls such as search, status filters, and refresh actions should read as one composed rail rather than disconnected floating widgets.

## 4. Component-Level Rules

## 4.1 Buttons

- Use shared button variants from `components/ui/button.tsx`.
- Primary actions use `variant="default"`.
- Primary CTA copy should be product-facing and action-oriented, for example `Create Digital Twin`, `Create Model`, or `Run Model`.
- Destructive actions use `variant="destructive"` or destructive text treatment.

## 4.2 Inputs and Forms

- Use shared input with standard focus ring.
- Use React Hook Form + Zod for validation.
- Error text appears inline under fields.

## 4.3 Tables

- Use `GenericDataTable` / `ControlledGenericDataTable` as default pattern.
- Include search by default.
- Prefer lighter table chrome with stronger row hover, clear headers, and enterprise card framing over dense admin-console styling.
- Include explicit destructive confirmation for delete actions.

## 4.4 Filter Bars and Action Rails

- Search, select filters, and refresh actions should share one horizontal rail with matched heights and consistent spacing.
- Keep select controls wide enough for operational statuses such as `In Progress`; do not compress them until labels truncate.
- Prefer text-plus-icon maintenance buttons such as `Refresh All` over icon-only affordances on library pages, because these controls are repeated but not primary brand CTAs.
- On smaller screens, wrap the rail while preserving reading order and visual grouping instead of shrinking controls below readable widths.
- Reuse the same rail treatment across BDT, rApp, admin, and upload-monitoring tables so the product feels system-driven rather than page-by-page.

## 4.5 Status Presentation

- Status should be communicated first through concise labels and consistent badge treatment, then reinforced with surrounding copy when needed.
- `queued`, `training`, and `in progress` states should read as active operational work, not failure-adjacent warning states.
- `ready` or completed states should use the calm positive badge treatment already present in shared status components.
- `failed` states should use destructive styling, but supporting copy should stay factual and actionable rather than alarmist.

## 5. Copilot Brand Requirements

These are mandatory for Copilot-aligned work.

## 5.1 Layout Model

Desktop:

- Two zones:
  - Main area on the left.
  - Fixed-width right panel.

Panel sections:

1. Header
2. Body (scrollable)
3. Composer (bottom)

Mobile:

- Full-screen sheet/drawer presentation.
- Composer must remain usable while keyboard is open.

## 5.2 Copilot Component Set

Expected component system:

- `CopilotShell`
- `CopilotPanel`
- `CopilotHeader`
- `CopilotEmptyState`
- `CopilotMessageList`
- `CopilotComposer`
- `CopilotFloatingButton`
- `CopilotSessionList`
- `CopilotAgentPicker`

## 5.3 Copilot Styling

- Use existing tokens only:
  - `bg-background`, `bg-card`, `text-foreground`, `text-muted-foreground`, `border-border`
- Panel separation:
  - `border-l` preferred for desktop right panel.
- Keep generous whitespace in composer and thread sections.

## 6. Accessibility Baseline

- Buttons and icon-only controls require `aria-label`.
- Inputs must preserve visible focus ring.
- Keyboard behavior for Copilot composer:
  - Enter sends message.
  - Shift + Enter adds newline.
- Escape key closes Copilot panel.

## 7. Assets and Identity

Available assets under `public/`:

- `Logo-Horizontal.png`
- `Logo-Vertical-on dark bg.png`
- `Logomark-on dark bg.png`

Usage notes:

- Topbar currently uses `Logomark-on dark bg.png` with product name label.
- The dashboard shell reuses existing logo assets with a darker enterprise sidebar and restrained top-bar branding; no new brand assets were introduced for the UI refresh.
- Auth pages use subtle background brand mark overlays.
- The `/select-tenant` entry flow pairs `Logo-Horizontal.png` with a restrained split-shell layout and low-opacity `Logomark-on dark bg.png` backdrop treatment.
- The `/trial` entry flow extends the same asset system with a darker product-led hero, a minimalist signup card, a direct returning-user sign-in action, and no new brand files.
- Data-library pages such as Digital Twin and Network Optimisation should continue using brand expression through shell framing, card hierarchy, and status presentation rather than introducing page-specific illustrations or additional raster art.
- Auth entry copy should stay aligned to `artifacts/marketing.md` and use enterprise platform language rather than backend implementation terminology.

## 7.1 Asset Reuse and Extension Rules

- Prefer existing assets under `public/` before introducing new files.
- When adding brand assets, keep naming consistent with current convention:
  - logo role + background context, for example `Logo-Horizontal.png`.
- Keep original raster formats currently used in repo (`.png`) unless there is a clear quality/performance requirement for an additional format.
- Document every new asset in this file and where it is used.

## 8. Do and Do Not

Do:

- Reuse existing UI primitives and tokens.
- Keep trial-mode emphasis informational: one banner, one clear CTA, and guided demo language instead of warning-heavy dashboards.
- Keep trial CTA copy enterprise-facing, for example `Interested in a dedicated workspace?` with a `Book a Call` action, rather than generic consumer-style sales prompts.
- Keep information density high but scannable.
- Use customer-facing page titles such as `Topology`, `Mobility Data`, `Digital Twin`, and `Network Optimisation` on primary surfaces.
- Keep inference-facing pages on a guided enterprise workspace pattern: sticky context bar, one workflow explainer, summary-first outcome framing, and tabs that progressively reveal validation, risks, and metadata.
- Keep `/infer` on the compact selected-hour review grouping: recommendations, KPI payload, serving-cell load, and raw RSRP/SINR summaries.
- Use consistent status visuals across modules.

Do not:

- Introduce isolated color systems for individual pages.
- Bypass shared form or table patterns.
- Reintroduce acronym-heavy customer-facing copy on primary navigation or page headers when `artifacts/ui-label-mapping.md` already defines the presentation-layer label.
- Reintroduce separate selected-hour cell-state or `tilt_by_cell` tables on `/infer` unless the API contract or an explicit product decision requires them again.
- Add new visual styles that conflict with token-based surfaces.
