# Failure and Repair

## Observed failure: Playwright browser version mismatch

- **Goal:** Run the real browser-level workflow tests.
- **Initial command:** `npm run e2e`
- **Observed result:** Both tests failed before opening the app because Playwright expected Chromium headless shell revision `1243`, while the machine only had an older cached revision. The message reported that the expected executable did not exist.
- **Likely cause:** The installed `@playwright/test` package had been updated independently of the cached browser binary.

## Repair

- **Change:** Set `channel: 'chrome'` in `frontend/playwright.config.ts` so Playwright uses the already-installed Google Chrome application.
- **Why this repair:** It avoids an unnecessary browser download, keeps the check reproducible on this Mac and tests the same browser family used for the manual local review.
- **Expected improvement:** Both workflow tests should launch and reach application assertions.

## Retest and regression

- **Actual retest:** `npm run e2e` completed two tests in Chrome: the full profile-to-validated-export flow and recoverable provider failure. Result: `2 passed`.
- **Regression:** Backend Ruff, strict mypy and pytest remained green; frontend lint, TypeScript, Vitest and production build remained green.
- **Remaining limitation:** A fresh machine without Chrome should install the Playwright browser or change the configured channel. The README records this requirement.

## Secondary quality finding: sample arrangement

The first three reviewed PDFs originally used three different supplied users. A deliverables audit found that the brief requires two jobs for one confirmed profile and one job for a different user. A new failing test encoded that rule, the sample data was rearranged, and the test passed. The obsolete generated PDFs were removed; they remain recoverable from Git history.
