# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Anyone who has to understand a PDF, grouped by what they do with it:

- **Students:** exam preparation, or research (papers, theses, reading lists).
- **Professors:** research, or teaching (lecture and course material).
- **Employees**, by field:
  - legal and compliance (contracts, policies);
  - finance and business (reports, decks);
  - engineering and IT (specs, manuals);
  - HR, operations and other (handbooks, procedures, anything else).

A first-run onboarding asks the user's profession and field, and the app shapes its options around the answer.

## Product Purpose

Upload a PDF, ask questions answered only from that document with the pages they come from, and get the document told back as a short, witty narrated story with a slide video. Success is a user who understands their document faster than by reading it, and trusts the answers because every one points to a page.

## Positioning

- Answers come only from the user's own document and cite its pages. An answer the document does not support says so instead of guessing.
- A story is always delivered: when no AI model is available, it is told in the document's own words, quoted exactly.
- The profession lens changes what the app emphasises (exam points, research findings, obligations, figures, steps) without changing the facts.

## Operating Context

- **Launch:** open sign-up, sized for about 5 to 10 people using it at the same time.
- **Hosting:** free tiers. The API runs on a Hugging Face Space (CPU) and the web app on GitHub Pages.
- **AI:** free model tiers with small shared daily quotas (OpenRouter, Groq as backup), so every user has daily caps on questions and stories.
- **Documents:** reports, papers, contracts, manuals, handbooks, lecture notes. Typically 2 to 100 pages.

## Capabilities and Constraints

- **Accounts:** email and password (12 to 72 bytes).
- **Library:** per-user document library with search, filters and paging.
- **Uploads:** PDF only, with upload size, page and text limits. Processing runs in the background; there is no OCR, so scanned PDFs have no text.
- **Questions:** answers cite pages. When no model answers, the response is a labelled set of matching passages.
- **Stories:**
  - one at a time per user, with an overview or detailed length;
  - the video is narrated by an online voice service, Microsoft edge-tts;
  - a failed video still leaves the text story.
- **Quotas:** daily per-user caps on uploads, questions and stories, enforced by the API.
- **Undecided:** permanent storage for the hosted API. The free Space disk is temporary, so a hosted PostgreSQL database is the open option.

## Brand Commitments

- **Name:** guruCool. The logo is being redesigned (owner's request, 2026-11-06); the old wordmark ("guru" over a marigold swipe) is reference, not a commitment.
- **Typefaces:** Fraunces for display and Karla for body, which the owner confirmed ("font is fine"). JetBrains Mono is used for small labels.
- **Copy:** no emojis, no em dashes and no en dashes in the interface or copy; ranges are written "5 to 10".
- **Voice:** plain and warm. Stories may be witty, but never invent facts.

## Evidence on Hand

- **Exists:** the product itself, a generated sample report (`tests/eval/rag_dataset.py`), and retrieval evaluation figures (hit@1 0.94, MRR 0.985 on the built-in dataset).
- **Does not exist:** testimonials, user counts, logos, press or pricing. None may be invented.

## Product Principles

1. Grounded before clever: every answer and story fact traces to the document.
2. First value in under two minutes: sign up, upload, see the first answer.
3. Ask once, adapt everywhere: the profession answer shapes defaults, suggestions and wording, and can be changed later.
4. Always deliver something: degrade to quoted passages rather than error screens.
5. Honest limits: show remaining daily quota and why something is unavailable.

## Accessibility & Inclusion

WCAG 2.1 AA: keyboard operable, visible focus, sufficient contrast, reduced-motion support, and readable at 390 px wide.
