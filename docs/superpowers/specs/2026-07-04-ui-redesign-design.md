# UI Redesign Spec

## Overview

Complete UI redesign for the vlog-video-analysis tool: modern, professional dark-first interface with light/dark mode toggle, refined component library, and missing style additions.

## Design Direction

- **Style**: Minimal professional (Linear / Vercel / Notion inspired)
- **Target**: Desktop web app (video editing workflow tool)
- **Mode**: Dark-first with light mode as secondary option

## 1. Color System

### Dark Mode (default)

| Token | Value | Usage |
|-------|-------|-------|
| `--bg-base` | `#0b0b0f` | Page background |
| `--bg-surface` | `#131318` | Cards, sidebar, editor |
| `--bg-surface-2` | `#1a1a22` | Elevated surfaces, inputs |
| `--bg-surface-3` | `#22222e` | Panel headers, section titles |
| `--bg-hover` | `#272735` | Hover states |
| `--bg-active` | `rgba(99,102,241,0.1)` | Active/selected items |
| `--border` | `#2a2a3a` | Default borders |
| `--border-light` | `#3a3a4e` | Lighter borders |
| `--border-focus` | `#818cf8` | Focus ring |
| `--text-primary` | `#ededef` | Primary text |
| `--text-secondary` | `#a1a1aa` | Secondary text |
| `--text-tertiary` | `#71717a` | Tertiary text |
| `--text-muted` | `#52525b` | Muted text |
| `--accent` | `#6366f1` | Primary accent (indigo) |
| `--accent-hover` | `#818cf8` | Accent hover |
| `--accent-bg` | `rgba(99,102,241,0.1)` | Accent background |
| `--accent-glow` | `0 0 20px rgba(99,102,241,0.15)` | Accent glow |
| `--success` | `#22c55e` | Success |
| `--success-bg` | `rgba(34,197,94,0.1)` | Success background |
| `--warning` | `#eab308` | Warning |
| `--warning-bg` | `rgba(234,179,8,0.1)` | Warning background |
| `--error` | `#ef4444` | Error |
| `--error-bg` | `rgba(239,68,68,0.1)` | Error background |

### Light Mode

| Token | Value |
|-------|-------|
| `--bg-base` | `#f8f9fc` |
| `--bg-surface` | `#ffffff` |
| `--bg-surface-2` | `#f1f3f5` |
| `--bg-surface-3` | `#e9ecef` |
| `--bg-hover` | `#dee2e6` |
| `--border` | `#e2e4e9` |
| `--border-light` | `#d0d3d8` |
| `--text-primary` | `#1a1a2e` |
| `--text-secondary` | `#52525b` |
| `--text-tertiary` | `#8a8a94` |
| `--text-muted` | `#b0b0b8` |

### Theme Toggle Implementation

- CSS custom properties driven: all colors use `var(--*)` references
- `body.light-theme` class overrides variables to light values
- JavaScript detects `prefers-color-scheme: light` on load
- User choice persisted in `localStorage`
- Toggle button in header bar

## 2. Typography

- **Font**: Inter (single font, weight variations)
- Base size: 13px (slightly larger than current 12-13px)
- Scale: 11/12/13/14/16/20/24px
- Monospace: JetBrains Mono / SF Mono for timecodes and code

## 3. Spacing & Radius

- Spacing: 4/8/12/16/20/24/32px (8px base grid, unchanged)
- Radius: 6/8/10/14px (slightly larger than current 4/6/8/12)

## 4. Component Redesign

### 4.1 Header
- Add brand logo/icon (purple "V" square)
- Project name with "PROJECT" label
- Source toggle as segmented control
- Right side: reload icon button + status badge
- Theme toggle button
- More compact: min-height 40px

### 4.2 Sidebar
- Project list items: rounded corners, better hover/active states
- Active item: indigo left border + indigo background tint
- Keyboard shortcut hints (⌘1-⌘4)
- Video list: thumbnail preview placeholder, duration, step badges
- Video badges using colored chips (success green, warning yellow, pending gray)
- Section headers: uppercase, smaller font, sticky

### 4.3 Player Pane
- Video player: full-width, dark background, subtle shadow
- Info bar: name left, timecode center (mono, accent), speed select right
- Preview bar (plan mode): segment blocks with labels, better coloring
- Keyboard hint: smaller, muted

### 4.4 Editor Panel
- Tabs: "segmented control" style (inner container with gap)
- Active tab: dark surface background, indigo text, font-weight 600
- Inactive: gray text, hover effect
- Tab panes: consistent padding
- Save button: full-width, indigo with glow, hover/active states

### 4.5 Buttons
- Primary (`btn-primary`): indigo bg, white text, border-radius 8px, box-shadow glow, hover brighten, active scale 0.98
- Secondary (`btn-secondary`): transparent bg, border, hover bg fill
- Icon buttons: 30x30px, border, rounded, hover highlight
- Danger: red variant

### 4.6 Form Controls
- Inputs: dark surface-2 bg, focus ring (3px indigo glow), consistent padding
- Checkboxes: custom styled, indigo accent
- Toggle switches: 32x18px pill, indigo when on
- Select: styled consistently with inputs

### 4.7 Modals
- Backdrop: blur(6px) + rgba(0,0,0,0.6)
- Dialog: border-light, border-radius 14px, shadow-xl
- Animation: `modalIn` (translateY -8px + scale 0.97 → identity), 200ms ease
- Header: semibold, 15px

### 4.8 Cards (project cards, provider cards)
- Consistent: bg-surface-2, border, radius 8px
- Hover: border accent, shadow lift
- Active: border accent, bg-active

### 4.9 Progress / Pipeline Steps
- Step items: icon circle with status (✓ done, number pending, spinner running)
- Duration hint on right
- Progress bar: gradient fill (indigo → indigo-light), smooth transition

## 5. Missing Styles to Add

### 5.1 Toast Notification System
- Fixed position, bottom-right, z-index 2000
- 4 variants: success (green), error (red), warning (yellow), info (blue)
- White text on colored background
- Close button ×
- Auto-dismiss after 4s
- Entry: slide up + fade in, exit: slide right + fade out
- Max 3 visible, queue overflow

### 5.2 Loading Skeleton
- Animated shimmer: linear-gradient moving across placeholder
- Used in: video list (while loading), editor content, project list
- CSS-only: `@keyframes shimmer` with background-position
- Rounded placeholders matching final content shape

### 5.3 Enhanced Empty States
- Icon + heading + description + action button
- Used for: no videos, no projects, no plan data
- Centered, generous padding

### 5.4 Unified Focus Ring
- All interactive elements: `:focus-visible` with indigo outline + box-shadow
- Never use `outline: none` without providing focus-visible alternative

### 5.5 Floating Editor Mode
- Toggle button to detach editor into floating panel
- Floating mode: absolute positioned, resizable, draggable
- Toggle back to docked mode

## 6. Micro-interactions & Animation

- All hover/active transitions: 150ms ease
- Panel show/hide: 200ms ease
- Modal entry: 200ms cubic-bezier
- Checkbox toggle: 150ms
- Resize handle hover: accent glow appears
- Respect `prefers-reduced-motion`: remove all animations

## 7. Scrollbar

- Width: 4px (thinner than current 6px)
- Track: transparent
- Thumb: border color, rounded
- Thumb hover: border-light
- Thin, unobtrusive, consistent across the app

## 8. Implementation Plan

1. Update `style.css` design tokens (colors, radius, transitions)
2. Refactor component styles section by section
3. Add light theme variables and toggle logic
4. Add missing styles (toast, skeleton, empty states, focus ring)
5. Update `index.html` for new structure (theme toggle, toast container)
6. Add toast JS module
7. Verify all existing functionality preserved
8. Test light/dark switching
