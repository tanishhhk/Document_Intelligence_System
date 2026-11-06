---
name: guruCool
description: Understand any PDF; every answer comes with its page.
colors:
  highlighter-marigold: "#ffc94d"
  highlighter-hover: "#ffd36b"
  marigold-ink: "#8f5200"
  desk-ink: "#0e2229"
  desk-ink-raised: "#16323b"
  ink-slate: "#2b4b57"
  ink-mist: "#8fa6ad"
  paper-white: "#ffffff"
  page-shade: "#eef1f0"
  ruled-line: "#dde3e1"
  pencil-grey: "#55666c"
  red-pen: "#c2362b"
  green-tick: "#1d6e4f"
typography:
  display:
    fontFamily: "Fraunces, Georgia, serif"
    fontSize: "clamp(2.25rem, 1.6rem + 2.8vw, 3.75rem)"
    fontWeight: 600
    lineHeight: 1.1
    letterSpacing: "-0.015em"
    fontVariation: "\"SOFT\" 50, \"WONK\" 0"
  headline:
    fontFamily: "Fraunces, Georgia, serif"
    fontSize: "clamp(1.75rem, 1.4rem + 1.4vw, 2.375rem)"
    fontWeight: 600
    lineHeight: 1.1
    letterSpacing: "-0.015em"
  title:
    fontFamily: "Fraunces, Georgia, serif"
    fontSize: "1.5rem"
    fontWeight: 600
    lineHeight: 1.25
  reading:
    fontFamily: "Fraunces, Georgia, serif"
    fontSize: "1.125rem"
    fontWeight: 400
    lineHeight: 1.8
  body:
    fontFamily: "Karla, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.55
    fontFeature: "\"onum\", \"pnum\""
  label:
    fontFamily: "Karla, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 700
  folio:
    fontFamily: "Fraunces, Georgia, serif"
    fontWeight: 500
    fontFeature: "\"onum\""
rounded:
  sheet: "4px"
  s: "6px"
  m: "10px"
spacing:
  "1": "4px"
  "2": "8px"
  "3": "12px"
  "4": "16px"
  "5": "24px"
  "6": "32px"
  "7": "48px"
  "8": "72px"
components:
  button-primary:
    backgroundColor: "{colors.highlighter-marigold}"
    textColor: "{colors.desk-ink}"
    typography: "{typography.label}"
    rounded: "{rounded.m}"
    padding: "0 24px"
    height: "44px"
  button-primary-hover:
    backgroundColor: "{colors.highlighter-hover}"
  button-quiet:
    backgroundColor: "{colors.paper-white}"
    textColor: "{colors.ink-slate}"
    rounded: "{rounded.m}"
    padding: "0 24px"
    height: "44px"
  button-danger:
    textColor: "{colors.red-pen}"
    rounded: "{rounded.m}"
    padding: "0 24px"
    height: "44px"
  input:
    backgroundColor: "{colors.paper-white}"
    textColor: "{colors.desk-ink}"
    rounded: "{rounded.m}"
    padding: "0 16px"
    height: "46px"
  tab:
    textColor: "{colors.pencil-grey}"
    rounded: "{rounded.s}"
    padding: "0 16px"
    height: "40px"
  tab-active:
    backgroundColor: "{colors.paper-white}"
    textColor: "{colors.desk-ink}"
  nav-item:
    textColor: "{colors.ink-mist}"
    rounded: "{rounded.s}"
    padding: "0 12px"
    height: "40px"
  nav-item-current:
    backgroundColor: "{colors.desk-ink-raised}"
    textColor: "{colors.paper-white}"
  page-sheet:
    backgroundColor: "{colors.paper-white}"
    textColor: "{colors.desk-ink}"
    rounded: "{rounded.sheet}"
    width: "780px"
---

# Design System: guruCool

## Overview

**Creative North Star: "The Highlighted Textbook"**

Studying a document is highlighting it. The app is an ink-blue desk with white paper sheets laid on it, and one marigold highlighter that marks what matters: the cited sentence, the current selection, the progress made. Margin notes and page folios are written in pencil grey; errors are marked in red pen. Nothing in the interface pretends to be a chat thread; answers sit on the page with their folio beside them.

Density is that of a well-set textbook: one sheet per screen (780px measure), generous margins, reading text in Fraunces at a long line height, interface chrome in Karla. The desk stays dark and quiet so the paper and the highlighter carry the attention.

**Key Characteristics:**
- Dark ink desk, white paper sheets with a soft page shadow.
- One accent, the marigold highlighter, used as a stroke behind text, never as decoration.
- Fraunces for titles, reading text and italic folios; Karla for every control.
- Lucide outline icons at stroke 1.75.
- Pencil-grey secondary text; red pen only for errors and destructive actions.

## Colors

A two-ground palette: dark ink for the desk, white for the paper, with a single warm highlighter between them.

### Primary
- **Highlighter Marigold** (`highlighter-marigold`): the highlighter stroke behind cited sentences, `::selection`, progress strokes, the primary button fill, and the focus ring. On the ink desk it also colours folios and small accent rules.
- **Marigold Ink** (`marigold-ink`): marigold as legible text on paper: citation superscripts, list markers, the story drop cap, the "choose a file" link, the caret, and the drag-over border.

### Neutral
- **Desk Ink** (`desk-ink`): the body background, the top bar, and primary text on paper.
- **Raised Desk** (`desk-ink-raised`): the desk surface under sheets in the workspace and onboarding; current nav item fill.
- **Ink Slate** (`ink-slate`): quiet button text, suggestion text, scrollbar track tone.
- **Ink Mist** (`ink-mist`): secondary text on the dark desk (nav, usage, ledes), and hover borders on paper.
- **Paper White** (`paper-white`): every sheet, input and quiet button.
- **Page Shade** (`page-shade`): tab tray, progress track, notices, the sheet's under-page.
- **Ruled Line** (`ruled-line`): hairline dividers, resting input and choice borders.
- **Pencil Grey** (`pencil-grey`): margin notes, folios, hints, meta lines, ledes on paper.
- **Red Pen** (`red-pen`): field errors, invalid borders, delete hover.
- **Green Tick** (`green-tick`): the "saved" confirmation only.

### Named Rules
**The One Highlighter Rule.** Marigold is the only accent. It marks evidence, selection and progress; it does not tint cards, icons or headings.

**The Legible Marigold Rule.** Marigold fill (`highlighter-marigold`) never carries text on white by itself; text that must read as marigold on paper uses `marigold-ink`.

## Typography

**Display Font:** Fraunces (with Georgia, serif), variable, `SOFT 50, WONK 0`.
**Body Font:** Karla (with system-ui, sans-serif).

**Character:** A soft, bookish serif for anything that belongs to the document (titles, reading text, quoted excerpts, folios) against a plain, warm grotesque for anything that belongs to the tool.

### Hierarchy
- **Display** (600, `--step-4` clamp 2.25 to 3.75rem, 1.1): story chapter titles.
- **Headline** (600, `--step-3` clamp 1.75 to 2.375rem, 1.1): page titles (document, library, settings, onboarding).
- **Title** (600, 1.5rem, 1.25): asked questions, choice labels, empty-state headings.
- **Reading** (Fraunces 400, 1.0625 to 1.125rem, 1.8): story scenes and excerpts; max 60 to 66ch.
- **Body** (Karla 400, 1rem, 1.55; answers at 1.1875rem, 1.65, 66ch): interface text, oldstyle proportional numerals.
- **Label** (Karla 700, 0.875rem): field labels, legends, buttons and tabs (buttons at 1rem).
- **Folio** (Fraunces italic 500, pencil grey, oldstyle numerals): page numbers, step counts ("2 of 3"), citations.

### Named Rules
**The Folio Rule.** Every page reference is a folio: Fraunces italic in pencil grey (marigold on the desk, marigold ink as a superscript citation). Page numbers are never set in Karla.

## Layout

One centred sheet per screen, 780px wide (760px in onboarding), on a dark desk padded 32px top and 72px bottom. Sheet padding scales `clamp(24px, 4vw, 48px)`. Spacing follows a 4/8/12/16/24/32/48/72 scale; sections inside a sheet separate at 24 to 32px, conversational turns at 48px. Excerpts use a two-column grid: a 64px right-aligned folio margin, then the text.

The sign-in page does not use the desk; it is its own world (see "Sign-in: The Cool Guru"). Below 760px sheets go full-bleed with square corners, nav labels hide to icons, and two-column choice grids collapse to one column. Controls keep a 44px minimum target.

## Elevation & Depth

Depth is physical: paper sheets lie on the desk and cast one soft page shadow. Inside a sheet the surface is flat and separated by hairline rules and page-shade trays. The sticky ask bar floats a little higher than the page; the primary button carries a faint marigold-tinted lift.

### Shadow Vocabulary
- **Page** (`0 1px 2px rgba(14,34,41,.08), 0 18px 40px -18px rgba(14,34,41,.35)`): every paper sheet.
- **Floating bar** (`0 10px 30px -12px rgba(14,34,41,.35)`): the sticky ask bar.
- **Highlighter lift** (`0 1px 2px rgba(143,82,0,.25), 0 8px 16px -10px rgba(143,82,0,.5)`): primary button at rest; removed when disabled.
- **Active tab** (`0 1px 2px rgba(14,34,41,.12)`): the selected tab lifting out of its tray.

### Named Rules
**The One Sheet Rule.** Only paper casts the page shadow. Cards and choices inside a sheet are bordered, not shadowed; only the floating ask bar and the active tab lift.

## Shapes

Sheets are nearly square (4px, 0 on phones), like trimmed paper. Controls are gently rounded (10px for buttons, inputs, choices and the tab tray; 6px for nav items, tabs and icon buttons). Borders are 1px hairlines for dividers and 1.5px for inputs and choices; the drop zone is a 2px dashed border. The highlighter carries the only non-rectangular geometry: slanted ends on the text stroke and a skewed `clip-path` on progress bars, as if drawn by a chisel tip.

## Components

### Buttons
Tactile and plain; the primary one is literally a highlighter swatch.
- **Shape:** gently rounded (10px), 44px tall, 24px side padding, Karla 700.
- **Primary:** marigold fill, ink text, highlighter lift; hover brightens and rises 1px (160ms, `cubic-bezier(.16,1,.3,1)`); disabled at 55% opacity, no shadow.
- **Quiet:** paper fill, ruled-line border, ink-slate text; hover darkens the border to ink mist.
- **Danger:** red-pen text, transparent border that turns red pen on hover and focus.
- **Icon button:** 44px square, 6px radius, pencil grey; destructive hover goes red pen on an 8% red wash.

### Inputs / Fields
- **Style:** paper fill, 1.5px ruled-line border, 10px radius, 46px tall; label above in Karla 700 0.875rem; hint below in pencil grey.
- **Focus:** border goes ink and a 3px soft-marigold halo appears.
- **Error:** red-pen border and a red-pen 600 message.

### Navigation
- **Top bar:** sticky ink bar; nav items in ink mist, Karla 700, with an 18px Lucide icon; hover and current fill with raised desk and turn paper white. Usage counts sit right, separated by small dots.
- **Tabs:** a page-shade tray (4px inset, 10px radius) holding pencil-grey tabs; the active tab is a paper chip with ink text.

### Choices
Option cards for onboarding and story length: 1.5px ruled border, 10px radius; hover and selected turn the border ink. Hover drops a soft marigold underline stroke behind the label; selected segmented options also take a 14% marigold wash.

### Highlighter Stroke (signature)
A marigold band behind text, 72% of the line height, sitting low (70%), with ends slanted at 100deg so it looks hand-drawn; it clones across line breaks. It marks the best-matching sentence in an excerpt and can draw in over 900ms. The same stroke appears as: the selection colour, the soft hover stroke on suggestions and choices, the current-document mark in the library, and the slanted progress bar for story generation.

### Excerpt
A cited passage: italic folio in the left margin, the passage in Fraunces reading text at 1.8 line height, the supporting sentence under the highlighter stroke.

## Do's and Don'ts

### Do:
- **Do** put every answer and quoted passage on a paper sheet with its folio beside it.
- **Do** use the highlighter stroke for evidence, selection and progress, and nowhere else.
- **Do** set page numbers as Fraunces italic folios.
- **Do** use Lucide outline icons, 16 to 20px (18px default), stroke 1.75, `aria-hidden`.
- **Do** use the 3px marigold outline (2px offset) as the focus ring everywhere in the app (the sign-in page has its own ring, below).
- **Do** keep controls at a 44px minimum target and honour reduced motion.

### Don't:
- **Don't** render answers as chat bubbles; questions are Fraunces titles, answers are page text.
- **Don't** introduce a second accent colour in the app; green tick and red pen are status marks, not accents. The sign-in palette stays on the sign-in page.
- **Don't** shadow cards inside a sheet; borders separate them, and only paper casts the page shadow.
- **Don't** put marigold-fill text on white; use marigold ink.

## Sign-in: The Cool Guru (page exception)

The sign-in and create-account page is its own world, scoped to that one page (`frontend/src/screens/SignIn.jsx`, `frontend/src/components/Guru.jsx`, `frontend/src/styles/signin.css`). Everything above describes the app behind it; nothing below carries into the workspace, onboarding, library or settings. guruCool taken at its word: a cool guru in sunglasses floats on his halo on a rani pink poster ground and watches you sign in. Fonts stay Fraunces and Karla; the copy rules (no emojis, no em or en dashes) hold here too.

### Palette (scoped to `.gc-signin`)
- **Rani** (`#ff4f97`): the ground, drenched edge to edge and set on `html` and `body` too, so overscroll never flashes the app's ink. Also the label colour on the pressed switch segment.
- **Rani Deep** (`#f03a86`): an unlit halo ring. A designed state of its own, not an absence.
- **Saffron** (`#ff8a1f`) and **Saffron Deep** (`#e8650c`): the robe; the deep tone for the sash and robe folds. Saffron lights halo rings 1 and 3 and the odd password beads.
- **Sun** (`#ffd23f`): the disc behind his head, halo rings 2 and 4, the even password beads, the primary button, the inner focus ring on inputs, and the seal's tick.
- **Indigo** (`#2a0f45`): all text, every line in the drawing, the 2.5px borders, the shades, the pressed switch fill, the seal, the caret, and `::selection` (indigo ground, sun text).
- **Maroon** (`#5c0026`): errors only: the invalid field border (on a `#fff0f5` fill) and bold error messages with an alert icon.
- **Skin** (`#c47a4a`) and **Beard** (`#fff6e8`): the guru's face, hands and feet; beard, brows and moustache.
- White (`#fff`) fills the field slabs, the speech bubble and the book in his lap.

**The One Saturated Note Rule.** Interactive accents come one at a time: the halo lights saffron and sun alternately; the form itself is indigo on white with a single sun button.

### Type
- **Name** (Fraunces 900, `SOFT 100, WONK 1`, `clamp(3rem, 1.6rem + 4.4vw, 6rem)`, line height 0.92, tracking -0.035em): the guruCool wordmark heading the panel. Steps down to `clamp(2.5rem, 1.5rem + 5vw, 3.5rem)` below 820px and 2.25rem on short phones.
- **Speech** (Fraunces 600, `clamp(1.05rem, 0.9rem + 0.5vw, 1.3rem)`, 1.35, centred, balanced): what the guru says.
- **Controls** (Karla): the lede at about 1.0625 to 1.1875rem, labels and notes at 0.9375rem (labels 700), inputs and the button at 1.0625rem (button 700).

### Layout
- One viewport, no scroll at common desktop and phone sizes (1280 by 720, 1440 by 900, 390 by 844, 375 by 667), and full page width. Only windows shorter than 560px fall back to scrolling rather than clipping.
- Desktop: a 55/45 grid. The stage on the left holds the drawing at `min(86dvh, 780px)` tall, shifted 70px left, so the outer halo ring bleeds past the left and top edges and ends before the form. The speech bubble sits just above his head, its tail pointing down at him. The panel on the right holds the name, one lede line, the sign-in or create switch, two fields and the button, in a column up to 27rem.
- Below 820px: one column. The guru is framed close on head and shoulders (a cropped viewBox) above the form, the bubble pinned to the top of the stage; the panel follows below, centred. Narrow windows 720px tall or less tighten the bubble, spacing, and control heights to 48px.

### The guru
A flat-shape drawing: saffron robe, indigo line with a heavier silhouette stroke (6) than interior lines (4 and 3.5), indigo shades, a sun disc and four halo rings behind him. The book in his lap is a guruCool page with a sun-yellow stroke across it. He floats (14px rise over 5s) above a soft indigo shadow that narrows as he rises, and blinks every 6s.

**Moods** (driven by the form):
- **Watch** (resting, or email focused): smiles and peers over his shades. His pupils follow the pointer; while the email is typed they track along the field as it fills.
- **Shy** (password focused, hidden): shades slide up over his eyes.
- **Peek** (password shown): shades lift and tilt, a grin.
- **Oops** (any error): brows jump, head tilts, mouth goes round.
- **Bliss** (submitting): grins and rises higher and faster (46px over 1.4s).

**Signature interactions:**
- **Halo as strength.** When creating an account, one ring lights per three characters of the 12 required; all four are lit when signing in.
- **Streamed speech.** His line types out two letters at a time and changes with mode, focus, input and errors ("A student, I sense. Exams soon?" for academic addresses). The bubble is `aria-hidden`; every fact it states is also in the form's own text.
- **Email seal.** A 28px indigo disc with a sun tick, sitting inside the email field, spins and pops in once the address looks complete.
- **Password beads.** Four 11px beads inside the password field (create mode), white with an indigo ring, filling saffron and sun alternately in step with the halo.

### Components
- **Switch:** a 2.5px indigo pill holding two 42px pill buttons; the pressed one is indigo with rani text, the other takes a 10% indigo wash on hover.
- **Field:** white slab, 2.5px indigo border, 14px radius, 52px tall, a faint inset shadow; the wrap lifts 2px on focus. The show-password button is a 44px target inside the field.
- **Primary button:** sun fill, 2.5px indigo edge, 14px radius, 56px tall; rises 2px on hover and presses 1px on active, with an indigo-tinted drop shadow.
- **Speech bubble:** white, 2.5px indigo border, 22px radius, a rotated-square tail.

### Focus
Inputs: a sun ring inside an indigo ring (`0 0 0 4px` sun, `0 0 0 6.5px` indigo), kept through browser autofill. Everything else: a 3px indigo outline at 3px offset. The app's marigold ring is not used here; it does not read on rani.

### Motion
Spring easing (`cubic-bezier(0.34, 1.56, 0.64, 1)`) belongs to the character only: his head, brows and shades (380ms), the seal and the bead pop (320ms). Everything else uses ease-out: ring colour (320ms), pupils (140ms), mouths (160ms), the switch and field shadows (200ms), field and button lift (220ms, the app's `--ease-out`). Reduced motion stops the float, shadow, blink and bliss rise, removes the transitions, and shows the guru's line whole instead of typing it.

### Do and don't on this page
- **Do** keep the palette, the spring and the guru on this page only.
- **Do** keep the primary action inside the first viewport at every common size.
- **Don't** add a product screenshot or a centred card; the guru is the brand moment.
- **Don't** let text depend on the speech bubble; it is decoration that repeats the form.
