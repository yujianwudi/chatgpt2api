# 0001: GIF/SVG Output Contracts

Status: pending-verification

- Owner: shared image execution and image storage modules
- Created: 2026-11-05
- Updated: 2026-11-11
- Related ADRs: 0002, 0003

## Problem and user outcome

A successful image response must contain the requested number of deliverable
assets. A storyboard or still image must not stand in for an animation. Canvas
and timing adaptations must be disclosed, unsupported options rejected, and
model aliases distinguished from a verified upstream image engine.

## Scope and non-goals

Merge upstream v3.2.6 (including v3.2.5 SVG generation and Studio controls)
while retaining bounded raster enlargement and gallery origin fixes. Harden
GIF/SVG results through the existing image execution path. No new provider,
storage repository, AI upscaler, account import, billing configuration, or
production deployment is included. The 2.5/2.6 aliases continue using Web auto;
this work does not claim a verified official engine or quality entitlement.

## Unique owners and Interfaces

| Concern | Owner | Interface |
| --- | --- | --- |
| Request normalization and final cardinality | services/protocol/conversation.py | validate_image_parameters, shared execution wrapper |
| GIF validation and adaptation | services/image_upscale_service.py | normalize_gif_output and the existing bounded worker |
| Static SVG safety and canvas | utils/svg.py | svg_dimensions, fit_svg_canvas |
| Asset persistence and publication | ImageStorageService | existing save/read operations |
| Task admission, retries and recovery | ImageTaskService and image failure policy | existing lifecycle, terminal output error |
| Composer draft and presentation | StudioComposer and Studio runtime | existing format/frame controls |

## Contract and failure behavior

- The subsequent image-option forwarding change accepts quality xhigh/max and
  complexity low/medium/high through the existing image execution Interface. Web
  JSON preserves the values without prompt mapping; auto complexity is omitted.
  Acceptance and image delivery do not verify native upstream effects. Call
  Records retain requested controls as passthrough_unverified. SVG continues using
  quality prompt hints and explicitly rejects xhigh/max and non-auto complexity.
- GIF frame_count accepts integers 2..60; numeric form strings are normalized.
  frame_duration_ms accepts 10..60000 in multiples of ten. Booleans, objects,
  null frame options and frame options for non-GIF formats are rejected before work.
- Canvas input is auto or bounded WIDTHxHEIGHT. GIF targets are at most 2048
  per dimension. Decoded frame pixels are bounded to 32 megapixels in aggregate.
- One GIF slot selects exactly one GIF from its upstream attachments. PNG
  storyboards are excluded. Corrupt, static, no-motion, ambiguous or wrong-count
  animations fail. No duplicate or interpolated frames are fabricated.
- A bounded Pillow worker fits an animation proportionally into the requested
  canvas and applies an explicit duration to every existing frame. It preserves
  loop semantics and verifies the encoded frame count and timing. Already
  compliant animations retain their original bytes. The response processing
  projection discloses adaptation; byte identity is not promised after adaptation.
- SVG remains text-model generation only; edits, references and streaming are
  rejected. Size/quality enter the derived prompt. A validated SVG can be fitted
  into the requested canvas without cropping. Physical units use 96 CSS pixels
  per inch; unsupported active XML remains rejected.
- GIF/SVG expose exactly n successful assets or a terminal error, never silent
  partial success. Other raster partial-result behavior remains unchanged.
- image_output_invalid is a delivery error, not an account failure. It does not
  switch accounts or regenerate internally. Direct error responses send
  x-should-retry:false. External gateways must independently honor this code;
  their retry and customer billing behavior is a separate integration check.
- Reported usage is a local estimate based only on delivered assets. Request
  and output logs retain frame settings, processing facts and route events.

## Persistence and frontend impact

No database migration. Task payloads retain frame settings for recovery; stored
assets remain under ImageStorageService ownership. The existing composer adds
format/frame controls and concise limits. It does not invent backend capabilities.

## Acceptance and verification matrix

| Criterion | Verification | Status |
| --- | --- | --- |
| Preserve gallery/raster customizations while merging both releases | merge diff, 118-test regression | passed locally |
| Reject unsupported/invalid parameters before network or admission | unit and HTTP contracts | passed locally |
| Select one animation, preserve motion/alpha/loop, fit canvas/timing | actual Pillow worker fixtures and original customer files | passed locally |
| Fail incorrect frame count/cardinality without regenerating | pipeline, recovery and failure policy tests | passed locally |
| SVG units, prompt, safe XML and target canvas | unit/protocol tests | passed locally |
| Studio desktop/mobile controls and task payload | production build and 11 isolated Edge checks at 1440x1000 / 390x844 | passed locally |
| Legacy frontend runtime suite | npm run test:runtime | unavailable: upstream does not ship web-vue/tests |
| Real upstream non-default generation and gateway refund behavior | external integration | not executed |

Automated checks, browser inspection, user acceptance and publication are distinct.
Local tests and screenshots remain outside committed source. This requirement
will remain pending verification until the required external checks are completed.

## Documentation, ADR and rollback

Update backend-map.md, README.md and CHANGELOG.md. No new ADR is required:
existing lifecycle and storage owners remain authoritative. Roll back code to
pre-merge history without deleting accounts, logs or generated assets. No remote
release, push, deployment or billing change is implied by these local changes.
