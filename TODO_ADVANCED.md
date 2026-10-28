# Advanced Development Backlog

## Audit baseline

- **Initial-audit architecture:** FastAPI backend (`backend/app`) with PyMuPDF parsing, regex-based metadata/section/evidence heuristics, and Supabase persistence with an in-process dictionary fallback; React 19/Vite frontend. The initial audit predates comparison and gap API/dashboard work recorded below.
- **Repository gaps:** There is no root README, checked-in database schema/migration, backend API documentation, or implementation of the advanced routes/services shown in `structure`. `backend/.env` defines `SUPABASE_URL`, `SUPABASE_KEY`, and `FRONTEND_ORIGIN`; values are not recorded here.
- **Baseline:** Backend tests: 6 passed, 1 failed. The missing-paper test attempted a Supabase network request and failed because the configured endpoint could not resolve; the backend virtualenv also has no `pytest`. Frontend `npm run build` passed (with a 573.71 kB JavaScript chunk warning); `npm run lint` passed.
- **Post-task validation:** Backend tests now pass offline: 16 passed. The missing-paper test explicitly clears Supabase configuration; upload tests cover size boundaries, rejected content, partial-file cleanup, duplicate filenames, malformed PDF cleanup, and a real PDF-to-claim API flow. Frontend build and lint pass; build still reports a 574.09 kB JavaScript chunk warning. One Starlette/AnyIO deprecation warning remains in tests.
- **Continuation verification:** The previous upload and claim-record implementation is still present. The comparison API/service suite passes; the comparison UI was manually exercised in a browser with mocked uploads and API responses, confirming both request payloads contain the selected IDs and that source-linked results render. Frontend build and lint pass. The complete backend suite is rerun after this continuation and recorded below.
- **Latest verification:** Backend: 56 passed, 1 existing Starlette/AnyIO deprecation warning, including embedding unit coverage and a parser output-shape regression test. Frontend: 5 Node built-in tests passed; production build and ESLint pass (584.71 kB minified JS, above Vite's 500 kB warning threshold). Browser mock-integration exercised upload-to-claim-reason rendering, year/topic/method/evidence filtering, relationship filtering, gap rationale/source rendering, and summary statistics; duplicate React keys were fixed and rechecked. The report download button click produced no page error, but the integrated browser did not emit a download event, so actual browser download is not claimed as verified. No embedding API or frontend similarity integration exists.
- **Resource/deployment notes:** Render config uses a free Python web service and static frontend. The upload API enforces the UI's 50 MiB maximum. Local files `2_MACS.pdf` (0.85 MB) and `1_FedEff.pdf` (4.9 MB) parse; `3_SAGE.pdf` (32.9 MB) is not a valid PDF despite its extension (its leading bytes are ASCII hex text and PyMuPDF reports no PDF objects). Parser profiling in isolated local Windows processes after imports measured peaks of 61.0 MiB/0.34 s and 94.1 MiB/0.74 s before removing unused text-layout retention; afterward peaks were 50.2 MiB/0.14 s and 70.5 MiB/0.37 s, respectively. This saves approximately 10.8 MiB and 23.6 MiB peak RSS in those runs. These are local single-upload measurements, not Render or concurrency guarantees; the parser still retains full extracted text/page text. Installed local sizes (not deployment image sizes): frontend `node_modules` 100.3 MiB, root Python `site-packages` 138.8 MiB, and backend virtualenv `site-packages` 80.1 MiB. The app has no heavyweight ML model dependency.
- **Persistence limitation:** Repository code references a Supabase `papers` table, but its schema and access policies are not checked in. Local fallback storage is process-local and is lost at restart. Do not add schema-dependent features until the live schema is inspected and a compatible migration is approved.

## Phase 1 — Advanced Analysis

### P1 — Add source-grounded claim records and classifications
- **Current status:** Complete (heuristic classification; no model confidence claimed).
- **Dependencies:** None.
- **Relevant files:** `backend/app/services/paper_analyzer.py`, `backend/app/services/pdf_parser.py`, `backend/app/main.py`, `backend/tests/test_pdf_structure.py`, `frontend/src/App.jsx`.
- **Implementation approach:** Preserve the existing `claims` response for compatibility; add structured claim records with claim text, heuristic category, section, paper ID when available, and page when reliably mapped. Avoid external models and label heuristic output.
- **Acceptance criteria:** Every generated record has source text and only includes page/section metadata when supported by extraction; paper IDs are attached in API responses; existing response consumers keep working.
- **Tests required:** Findings/hypothesis/limitation/causal/correlational categorization, missing sections/pages, multi-page input, empty text, response compatibility, PDF upload integration.

### P1 — Compare evidence and synthesize across papers
- **Current status:** Complete (explicit-ID API and session-scoped frontend flow; lexical heuristic screening, not semantic verification).
- **Dependencies:** Source-grounded claim records; caller supplies paper IDs, avoiding a schema-dependent bulk-list API.
- **Relevant files:** `backend/app/services/cross_paper_analyzer.py`, `backend/app/main.py`, `backend/tests/test_cross_paper_analyzer.py`, `backend/tests/test_pdf_structure.py`.
- **Implementation approach:** `POST /papers/compare` accepts 2–10 unique paper IDs. It returns pairwise results with claim excerpts and source paper/section/page, heuristic status/confidence, and extracted methodology, sample-size/statistic/uncertainty/limitation signals. Where both papers report context, exact extracted values are juxtaposed as matching/differing/not comparable without interpreting differences as contradictions. Legacy string claims are supported. No schema migration or new dependency is required.
- **Acceptance criteria:** Pass in backend implementation/tests: lexical alignment is not treated as verification; opposing cues are labeled potential conflict; missing claims are insufficient evidence; context differences are not treated as contradictions; invalid IDs and storage failures have explicit responses. Pass in manual browser check: user can select uploaded papers, invoke comparison, and see cited claim pairs. Remains limited to session-uploaded papers in UI and lexical heuristics.
- **Tests required:** Potential conflict, supporting lexical alignment, complementary outcomes, incomparable and insufficient evidence, extracted study context, legacy records, 2–10 ID bounds, duplicate IDs, missing papers, storage errors, source traceability; browser check of upload/selection/request/render flow.

### P1 — Detect research gaps and score research opportunities
- **Current status:** Complete as a source-grounded heuristic API and frontend flow; not a corpus-wide gap detector or validated opportunity model.
- **Dependencies:** Source-grounded claims and cross-paper evidence.
- **Relevant files:** `backend/app/services/research_gap_engine.py`, `backend/app/main.py`, `backend/tests/test_research_gap_engine.py`, `backend/tests/test_pdf_structure.py`, `frontend/src/App.jsx`, `frontend/src/App.css`.
- **Implementation approach:** `POST /papers/gaps` accepts 1–10 unique explicit paper IDs. It extracts literal author-reported limitation, future-work, underexplored, and missing-comparison statements, plus potential-conflict claim pairs from the comparison screen. It emits source references, configurable score weights, named factors, and uncertainty limitations. The UI renders returned evidence and scores. It does not infer gaps from absent topics/comparisons in the selected corpus.
- **Acceptance criteria:** Evidence and score factors are included per result; confidence and score are labeled heuristic; only quoted source statements or potential-conflict screening results create gaps; missing corpus topics alone create none; missing paper IDs and storage errors are explicit. Validation: backend unit/API tests and browser UI-to-API check.
- **Tests required:** Explicit limitations, future-work/underexplored statements, author-reported missing comparisons, inconsistent-claim screening signal, no-gap corpus, empty selection, configurable weight boundaries, factor explanations, citation metadata, API missing IDs, UI rendering.

## Phase 2 — Research Relationships

### P0 — Generate and cache paper embeddings and semantic similarity
- **Current status:** Partial. Schema-independent components are implemented and unit-tested: Unicode/whitespace normalization and SHA-256 content hashes, a bounded version/content-keyed in-memory cache, a configurable hosted-provider adapter, validated vectors, cosine similarity, and thresholded ranking. This is not persisted, wired into the paper/API workflow, or exposed in the frontend.
- **Dependencies:** Persistence/schema decision; paper text normalization.
- **Relevant files:** New embedding service, `backend/app/services/paper_repository.py`, configuration, tests.
- **Implementation approach:** Persist paper ID, model ID/version, dimension, normalized-content hash, and vector only after confirming the actual schema and migration permissions. Benchmark the preferred MiniLM model against the Render memory budget before enabling local inference; use the configured hosted adapter only after provider settings are supplied. Keep cache keys sensitive to content and model version.
- **Acceptance criteria:** Partial only: schema-independent hashing, bounded cache, provider validation/error handling, metadata, and similarity ranking are implemented. Persistence, duplicate prevention across restarts, content-change invalidation in persisted records, API/frontend integration, pgvector/JSONB selection, and production model/resource validation remain incomplete. User selected PostgreSQL with pgvector preferred (JSONB fallback), `sentence-transformers/all-MiniLM-L6-v2`, and the SQL Editor migration workflow. Repository inspection found no checked-in schema/migrations; a read-only Supabase REST schema probe failed with a connection error. Actual columns, constraints, pgvector availability, and permissions remain unverified. `sentence-transformers`, PyTorch, Transformers, and cached Hugging Face models are absent locally, so model memory has not been benchmarked. Do not create a guessed migration or enable an unbenchmarked model in Render.
- **Tests required:** Schema-independent tests pass: cache hit/miss/invalidation and bounded eviction, normalization/hash stability, hosted-provider success/failure and redaction, invalid vectors, similarity ranking/filtering. Persistence/API integration and resource/latency budget remain unverified until prerequisites are available.

### P1 — Build typed evidence relationships and citation data
- **Current status:** Not started.
- **Dependencies:** Claim records, embeddings, and an approved persistence design.
- **Relevant files:** New relationship service/API, `backend/app/services/paper_repository.py`, database migration only after schema review.
- **Implementation approach:** Store or derive typed `supports`, `contradicts`, `cites`, and `semantically similar` edges with evidence and provenance. Include citation edges only from supplied or reliably retrieved citation data.
- **Acceptance criteria:** No fabricated citations; each edge has provenance and relationship type; database access remains compatible with existing schema.
- **Tests required:** Typed edges, provenance, duplicate handling, absent citation data, repository failure.

### P2 — Add an interactive evidence graph
- **Current status:** Not started.
- **Dependencies:** Relationship API and claim/paper detail endpoints.
- **Relevant files:** `frontend/src/App.jsx`, `frontend/src/App.css`, `frontend/package.json`, relationship API.
- **Implementation approach:** Extend the existing dashboard with a graph view, relationship filters, and paper/claim details using actual API data.
- **Acceptance criteria:** Loading, empty, error, and responsive states; filters reflect returned relationship types.
- **Tests required:** Graph data mapping, filtering, empty/error states, frontend build and lint.

## Phase 3 — Trends and Forecasting

### P1 — Aggregate topic publication trends and emerging topics
- **Current status:** Not started.
- **Dependencies:** Multiple persisted papers with usable year and topic metadata.
- **Relevant files:** New trend service and statistics API; frontend dashboard.
- **Implementation approach:** Use reproducible topic assignment/clustering and aggregate actual papers by year; expose corpus coverage, recency, and volume.
- **Acceptance criteria:** Topics and counts derive only from stored papers; sparse coverage is disclosed and does not imply a reliable trend.
- **Tests required:** Year/topic aggregation, missing metadata, sparse data, reproducibility.

### P2 — Forecast research trends when time series support it
- **Current status:** Not started.
- **Dependencies:** Publication trend aggregation and sufficient observations.
- **Relevant files:** New forecasting service/API, trend dashboard, tests.
- **Implementation approach:** Use a lightweight, reproducible baseline; return no forecast when the series is insufficient and report uncertainty/assumptions.
- **Acceptance criteria:** No unsupported forecast or high-growth claim; output includes data coverage and limitations.
- **Tests required:** Adequate and inadequate series, reproducibility, uncertainty bounds.

## Phase 4 — AI and Explainability

### P1 — Explain analysis results and calibrate confidence labels
- **Current status:** Partial. Evidence Stability Score factors and formula are exposed and displayed. Claim records now include the exact matched wording marker and a limitation-qualified heuristic classification reason; gap results include the matched source marker or opposing-cue screening rationale. The dashboard displays these explanations. Confidence calibration remains unavailable without evaluation data, and relationship explanations remain limited to lexical heuristics.
- **Dependencies:** Source-grounded claims, contradiction/gap pipeline, evaluation data.
- **Relevant files:** Analysis services and API schemas; frontend analysis panels; tests/docs.
- **Implementation approach:** Return evidence snippets and explicit heuristic factors. Keep Evidence Stability Score separate from model confidence; avoid implying generated explanations verify scientific findings.
- **Acceptance criteria:** Pass for Evidence Stability Score transparency and the tested claim/gap explanation path: factors, points, formula/thresholds, source wording triggers, limitations, and heuristic labels are returned/displayed. Comparison explains lexical screening without treating it as verification. **Incomplete:** no labeled evaluation set exists to calibrate result confidence or the score; explanations do not verify findings; human feedback remains separate.
- **Tests required:** Evidence links, factor accounting and boundaries, heuristic labeling, score/confidence separation, frontend score disclosure.

### P1 — Add human review and feedback
- **Current status:** Not started; persistence schema and authentication requirements unknown.
- **Dependencies:** Schema/access-policy review and approved authentication/authorization requirements.
- **Relevant files:** Database migration/API, `backend/app/services/paper_repository.py`, frontend review UI.
- **Implementation approach:** Persist accept/reject/correct/flag feedback with reviewer and timestamp under authorized access; do not use process-local feedback as durable success.
- **Acceptance criteria:** Feedback survives restart, is scoped to an authorized result, and is auditable.
- **Tests required:** Feedback lifecycle, invalid result IDs, authorization, persistence failure.

### P2 — Evaluate optional hosted or local AI models
- **Current status:** Not started.
- **Dependencies:** Measurable extraction baseline and deployment resource budget.
- **Relevant files:** New optional provider integration, configuration, requirements only if justified.
- **Implementation approach:** Compare against deterministic extraction; keep credentials server-side and make unavailable providers fail explicitly or use a clearly identified deterministic path.
- **Acceptance criteria:** Demonstrated quality gain justifies cost/latency; no frontend secrets or model claims without validation.
- **Tests required:** Provider success/failure, timeout, secret handling, output provenance.

## Phase 5 — Advanced Dashboard

### P1 — Add multi-paper comparison and cross-paper statistics
- **Current status:** Complete for explicit session-selected paper comparison and available summary statistics; not a corpus-wide paper browser.
- **Dependencies:** Multi-paper retrieval and cross-paper analysis API.
- **Relevant files:** `frontend/src/App.jsx`, `frontend/src/App.css`, backend paper/analysis routes.
- **Implementation approach:** Extend `POST /papers/compare` with actual publication-year coverage, evidence-score values/range/average, and extracted-method counts; render these together with sourced claim comparisons in the existing dashboard.
- **Acceptance criteria:** Pass: computed statistics derive only from selected backend responses, missing values are disclosed, and the original single-paper analysis remains available. Browser-tested API calls and rendering; dashboard selection is limited to papers uploaded during the current UI session.
- **Tests required:** Two/multiple papers, missing values, API errors, summary-stat calculation, browser upload/selection/request/render flow, responsive rendering.

### P1 — Add transparent Evidence Stability Score explanations
- **Current status:** Complete for score explanation; confidence calibration remains a separate blocked portion of the Phase 4 item.
- **Dependencies:** Existing score factors; no evaluation data needed for transparency.
- **Relevant files:** `backend/app/services/paper_analyzer.py`, `backend/tests/test_pdf_structure.py`, `frontend/src/App.jsx`, `frontend/src/App.css`.
- **Implementation approach:** Return applied/unapplied factor points, reasons, clamping formula, label thresholds, and limitations with the existing score; disclose the factors in the paper detail panel.
- **Acceptance criteria:** Score exactly matches applied factors and remains distinct from confidence; explicitly state it measures extracted reporting signals, not validity or calibrated confidence.
- **Tests required:** Empty and saturated signals, factor sum, thresholds, response compatibility, frontend disclosure.

### P1 — Add search, filters, and exportable reports
- **Current status:** Partial. Session-only paper search covers title, filename, author, year, extracted keywords, method terms, claims, and reported gap text; dedicated year/topic/method/evidence-label filters use only uploaded API data. Comparison results can be filtered by returned relationship type. JSON report construction includes current/related papers, returned comparison/gap data, and uncertainty notes. No server-side corpus search exists.
- **Dependencies:** Searchable paper/relationship APIs and stable analysis schemas.
- **Relevant files:** `frontend/src/App.jsx`, `frontend/src/researchReport.js`, `frontend/tests/researchReport.test.js`; server-side search is not implemented.
- **Implementation approach:** Filter only session-uploaded API results using available topic, year, methodology, evidence-label, and relationship fields; export source-linked JSON from actual upload/comparison/gap responses. Add server-wide search only with a verified repository query path.
- **Acceptance criteria:** Pass for tested session-local search, year/topic/method/evidence-label filters, and relationship filtering. Report JSON content/provenance/uncertainty and filename sanitization pass utility tests. Browser rendered query/filter results; export click has no observed JS error but actual download event was not verified. **Incomplete:** cross-session/corpus search, export error handling, and actual file download verification.
- **Tests required:** Node built-in utility tests for supported paper-field search/filtering, relationship filtering, selected source papers, uncertainty notes, missing comparison data, and filename sanitization; frontend build/lint and browser-mocked rendering.

### P2 — Add publication and topic trend visualizations
- **Current status:** Not started.
- **Dependencies:** Trend API.
- **Relevant files:** `frontend/src/App.jsx`, `frontend/src/App.css`.
- **Implementation approach:** Extend the existing dashboard and charts; show corpus coverage, uncertainty, and sparse-data empty states.
- **Acceptance criteria:** Visualization values match API output; no fabricated trend line.
- **Tests required:** Data mapping, empty/error states, frontend build and lint.

## Phase 6 — Production Quality

### P0 — Enforce upload size/type validation and safe file handling
- **Current status:** Complete.
- **Dependencies:** None.
- **Relevant files:** `backend/app/main.py`, `backend/tests/test_pdf_structure.py`, frontend upload form.
- **Implementation approach:** Enforce the UI's 50 MiB limit on the server while streaming; reject non-PDF content; avoid overwriting uploads with duplicate names and clean up partial files.
- **Acceptance criteria:** Oversized or invalid uploads receive explicit 4xx errors; accepted PDFs retain the existing response/API behavior; no partial file remains after rejection.
- **Tests required:** Valid PDF, non-PDF extension/content, exact size boundary, oversized body, duplicate filenames, parse/storage failures.

### P0 — Make baseline API tests independent of live Supabase
- **Current status:** Complete.
- **Dependencies:** Test environment with `pytest`; no live credentials required for unit tests.
- **Relevant files:** `backend/tests/test_pdf_structure.py`, `backend/app/services/paper_repository.py`.
- **Implementation approach:** Isolate local repository tests from inherited credentials and mock remote repository operations in route tests; provision pytest through the project test setup if needed.
- **Acceptance criteria:** Offline test suite is deterministic and does not make external network calls.
- **Tests required:** Missing-paper route, local save/retrieve, mocked Supabase success/failure.

### P1 — Add API/integration coverage, structured logging, and monitoring
- **Current status:** Partial. Offline API and integration coverage is expanded to 56 passing tests; redacted JSON error events are logged for parsing and paper-storage failures. Production monitoring and deployment health verification are not implemented.
- **Dependencies:** Stable API schemas and repository boundaries.
- **Relevant files:** `backend/tests/`, `backend/app/main.py`, service modules, Render config.
- **Implementation approach:** Test end-to-end upload, persistence and retrieval with controlled fakes; emit structured, redacted operational logs and useful errors.
- **Acceptance criteria:** Pass for tested API outcomes and redacted error events; **incomplete** for metrics/monitoring and production health/connectivity verification.
- **Tests required:** API success/failure cases, logging redaction, health and storage connectivity behavior.

### P1 — Bound PDF/NLP memory and add background processing where needed
- **Current status:** Partial. Removed unused per-span layout/font/bounding-box data from every parsed page while preserving page number and text for claim-source mapping. Two valid local samples were profiled before/after; see the resource notes above. A valid large (near-limit) PDF, deployed-instance profiling, concurrency budget, and background-job/retry implementation remain unverified.
- **Dependencies:** Upload limits and measured production-like profiling.
- **Relevant files:** `backend/app/services/pdf_parser.py`, `backend/app/main.py`, Render config, performance tests.
- **Implementation approach:** Measure peak memory/latency, retain only data used by analysis/API, then consider deployment-compatible background processing if representative large-document or concurrency measurements warrant it.
- **Acceptance criteria:** Pass for removing unused page layout and preserving source page mapping. **Incomplete:** a near-limit valid PDF and Render measurements are unavailable; no evidence currently justifies background-job infrastructure; retry/idempotence behavior is not implemented.
- **Tests required:** Parser output retains source text/page number without unused layout; representative large PDF profiling, deployment budget, and job failure/retry/idempotence when justified.

### P1 — Review authentication, authorization, CORS, and database policies
- **Current status:** Not started; product access requirements and live Supabase policies are unknown.
- **Dependencies:** Owner confirmation of access model and authorized schema/policy inspection.
- **Relevant files:** `backend/app/main.py`, repository/database configuration, Render environment and Supabase policies.
- **Implementation approach:** Define authorization boundaries, least-privilege database access, CORS allowlist, and request limits without exposing service-role credentials.
- **Acceptance criteria:** Production access policies match the approved user model and secrets remain server-side.
- **Tests required:** CORS/preflight, authorization, rate/file limits, policy verification.

### P2 — Verify deployment, dependencies, and operational behavior
- **Current status:** Not started; static build passes locally, but Render/Supabase production behavior is unverified.
- **Dependencies:** Successful deploy and authorized production health/database checks.
- **Relevant files:** `render.yaml`, backend/frontend dependency manifests, health/API tests.
- **Implementation approach:** Review dependency size/vulnerability reports and verify startup, environment configuration, health checks, and database connectivity on Render.
- **Acceptance criteria:** Deployment works with documented environment variables and no embedded secrets; production verification is recorded.
- **Tests required:** Dependency audit, clean install/build, deployment health and connectivity checks.

## Next task

Next, the highest-priority embedding persistence/API work remains blocked until actual Supabase schema, pgvector-or-JSONB support, and migration permissions are verified. Do not guess DDL, request credentials, or load unbenchmarked MiniLM into Render. Resource work needs a valid large PDF for further capacity measurement; the available 32.9 MB file is malformed, so do not treat its size as a valid workload. Confidence calibration remains blocked pending a labeled evaluation set; durable human feedback remains blocked pending authorized schema/policy details. No safe migration, reliable trend aggregation, or production verification is possible from the currently available evidence.
