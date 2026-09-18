# Tectonic spatial pilot console

A repository-backed demonstration experience for the existing support-agent slice.
Warm neutral navigation surrounds a connected isometric agent workspace. A visitor
can move from team → agent → module → API operation, or scenario → run → step →
structured evidence. The three scripted journeys map to Ticket #82: policy answer,
order lookup, and an $850 refund requiring human review.

## Run

Python 3.12, no third-party server packages required:

```sh
python apps/pilot-console/server.py
# Open http://127.0.0.1:3000
```

The server binds to localhost. Do not expose it as the authenticated public pilot
API: that gateway remains separate work in the ten-ticket plan. This UI feature
branch does not claim to complete the baseline or production acceptance gates.

## Included

- Spatial/list team views, 18 illustrative agent personas and searchable catalogue.
- 34 modules and 297 route declarations extracted from source at commit 7a48334.
- Three animated scenario playbacks, pause/resume, step inspector and JSON evidence export.
- Refund review claim, reason, approve/reject and one-time local resume.
- Browser-persisted demo configuration, run records and TXT/Markdown source previews.
- Assurance outcomes derived from the current browser's runs; fixed illustrative costs.
- Acme/Globex demo switching, global search, keyboard navigation, reduced motion and responsive layouts.
- Server-side pilot enquiry capture with validation, explicit consent, rate/body limits and SQLite persistence.
- No automatic email, CRM sync or public publication. Operators can export enquiries:

```sh
python apps/pilot-console/server.py --export-leads > enquiries.json
```

Enquiries live in `.data/leads.sqlite3` (mode 0600, directory 0700). Set
`TECTONIC_CONSOLE_DATA` to an operator-managed persistent location if needed.
The export contains personal data and should be stored appropriately.

## Optional real support conversation

Start and seed Ticket #82 using the existing stack instructions. Then supply the
seeded tenant and the same non-default shared secret used by those services:

```sh
export TECTONIC_CONSOLE_LIVE=1
export TECTONIC_CONSOLE_TENANT_ID='<seeded tenant UUID>'
export TECTONIC_JWT_SHARED_SECRET='<stack secret>'
python apps/pilot-console/server.py
```

The scenario chooser then exposes **Open connected backend chat**. Only creation
of a web session and sending messages to sessions created by this local adapter
are supported. Credentials and tenant selection remain server-side; browser
`X-Tenant-Id` and role headers are not forwarded. The adapter rejects redirects
and unknown operations. It is intended for one trusted local operator, not
multi-user public authentication. It does not expose administrative/review APIs.

Actual conversation responses are displayed without fabricated per-step telemetry.
Spatial animation and detailed run evidence always remain labelled simulation.
Backend failures stay errors; they never fall back to invented live responses.
No live backend integration was validated unless separately stated in the handoff.

## Honest demonstration boundaries

The 18 agent names are presentation personas mapped to module responsibilities,
not a claim of deployed autonomous workers. Knowledge uploads/configuration do
not modify backend resources. Browser tenant switching is not a security boundary.
PDF/DOCX ingestion, authenticated roles, versioned citations, enforced publication
evaluation and production spending limits still need the ten-ticket implementation.
The original scenario uses USD; this console does not silently relabel it GBP.

## Maintenance and verification

```sh
python apps/pilot-console/generate_catalog.py
python -m unittest discover -s apps/pilot-console/tests -v
node --check apps/pilot-console/static/app.js
npm ci --prefix apps/pilot-console
npx --prefix apps/pilot-console playwright install chromium
# With the console running in another terminal:
npm run test:browser --prefix apps/pilot-console
```

`generate_catalog.py` inventories route decorators without importing module
services or claiming their deployment health. Source links use the inspected
commit. Run `tests/browser.cjs` using Playwright to exercise navigation, all three
journeys, approval/resume, persistence, consent capture and desktop/mobile layout.

External Google Fonts are optional; local system fallbacks work offline. Host HTML,
CSS, JavaScript and catalogue together. Lead capture and the local adapter require
the Python server; opening index.html with file:// is unsupported.

## Verification recorded for this change

Nine Python server tests pass. The Chromium browser check passes all three
support scenarios, review/resume, source preview, operation inspection, persisted
runs, demo tenant switching, enquiry submission and eight routes at desktop and
390px mobile width, with no uncaught JavaScript errors. Screenshots were inspected.
The live adapter and the full 34-service production stack were not exercised.
