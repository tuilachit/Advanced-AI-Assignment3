# Frontend redesign — 6 September 2026

Luke requested a redesign using the supplied Urbanet reference: spacious layouts, restrained colours, large typography and understated borders.

## Design decisions

- Replaced the dark sidebar with a horizontal four-stage navigation.
- Used an off-white canvas, charcoal controls and a muted slate-blue introduction.
- Paired system sans-serif typography with a serif italic headline accent. No external font dependency.
- Created a decorative CV-paper composition in HTML/CSS. It is marked hidden from assistive technology and does not represent generated candidate data.
- Show the introductory hero only on the Profile stage before facts are captured; subsequent work prioritises the editor.
- Added practical introduction guidance and a profile empty state that explains what happens next.
- Applied the same spacing, border, colour and control styles across job matching, CV editing and evidence views.
- Kept the existing confirmation, selection, validation and export behaviour. Corrected the confirmed-profile status display when revisiting Profile from a later stage.
- Made startup connection errors visible instead of leaving an indefinite loading message.

## Verification

- Frontend production build (including TypeScript): passed.
- ESLint: passed.
- Vitest unit suite: 7 passed. Browser tests are excluded from Vitest discovery and run separately through Playwright.
- Playwright: 2 passed, covering the guided flow, export relocking after edits and recoverable provider errors.
- Added desktop/mobile overflow assertions and screenshots to the existing browser workflow test.
- Profile inspected at 1440, 1024, 768 and 375 pixels; no horizontal overflow. Hero CTA focuses the introduction textarea. No browser page errors observed.
- Job cards and CV editor visually inspected at 1440 and 375 pixels; Evidence also captured and checked for horizontal overflow.

Screenshots are under the ignored `artifacts/generated/redesign-*` paths. Job, CV and Evidence screenshots use mocked browser-test responses; they are design verification, not live model evaluation evidence. No OpenAI generation requests were made for this redesign.
