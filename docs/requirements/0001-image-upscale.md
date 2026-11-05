# 0001: Bounded image enlargement

Status: pending-verification

- Owner: image enlargement service
- Created: 2026-11-05
- Updated: 2026-11-05
- Related ADRs: 0003, 0004 (storage ownership unchanged)

## Problem and user outcome

The existing optional image enlargement stretches mismatched aspect ratios,
waits indefinitely on a global lock, and lacks processing timings and actionable
Call Record diagnostics. Improve quality, throughput, and diagnosis using the
existing Sharp and Pillow interpolation engines.

## Scope and non-goals

Add full-frame contain (default) and centered cover policies, EXIF-aware input
checks, bounded admission and execution, consistent encoding, and safe per-image
diagnostics. No AI super resolution, model-routing change, new dependency,
account mutation, storage migration, version bump, or repository publication.

## Unique owners and Interfaces

| Concern | Owner | Interface |
| --- | --- | --- |
| Geometry, admission, fallback, cleanup | image_upscale_service | upscale_image_if_needed returns bytes with optional diagnostic report |
| Persistent policy | SettingsManagementService / SystemSettingsRepository | image_upscale_fit in existing revisioned settings |
| Request deadline and lifecycle | ConversationRequest / ImageTaskService | existing deadline passed to enlargement |
| Asset persistence | ImageStorageService | existing save_image_bytes seam |
| Diagnostic persistence and presentation | LoggedCall / request_detail_view | private image metadata and backend detail fields |
| Draft, focus, layout, scrolling | SettingsBasicPolicyPanel / settings page | existing settings editor and select controls |

## Failure, concurrency, security

At most two workers per application process; queue wait at most five seconds.
Processing shares a 60-second total budget, capped by request deadline with a
two-second return reserve. Both engines execute in killable child processes.
Invalid, oversized, animated, busy, timed-out, or failed enlargements retain the
original image. A Sharp failure may fall back once to Pillow within the same
budget. No payload, prompt, URL, or credentials enter enlargement diagnostics.

## Acceptance criteria and verification matrix

- Contain preserves full composition; cover crops centrally; neither stretches.
- Alpha, EXIF orientation, PNG/JPEG/WebP output, and no-enlargement behavior are verified with synthetic images on both engines.
- Queue, deadline, resource limits, fallback, and output validation retain originals safely.
- Settings validation/persistence and direct/SSE/Chat/Responses log privacy are checked through existing Interfaces.
- Desktop and mobile Settings render and persist only in an isolated environment; browser console and other main routes are checked.
- Python suite, frontend build, real-engine benchmark, diff checks, and source rebuild are recorded outside the repository.
- Product acceptance remains pending the user's review.

## Verification state

The 38 targeted Python cases passed locally and in the Linux image. Frontend
type checking and production build passed. Playwright/Edge verified isolated
settings changes, reload persistence, keyboard dismissal, desktop (1440x1000),
mobile (390x844), dark theme, and eight primary routes without console errors.
The repository's broader frontend runtime suite could not run because its
ignored test sources are absent from the checkout. Synthetic 1024-to-4096
four-request Sharp batches improved from a 1588 ms to an 809 ms median locally;
this is workload-specific, not a production latency guarantee. The app image
was rebuilt and deployed with the prior enable/engine settings retained.
User review of real generated image quality remains pending.
