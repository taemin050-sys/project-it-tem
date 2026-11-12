# Model glyph matte correction v5

Opt-in matte_style_context produces freeform_model_matte_corrected_v1,
explicitly distinct from pure Freeform and the preserved source-stroke retouch.
A flat monochrome specimen retains native glyph geometry. The model generates
the correction; the server restores source ink color and visible background,
interpolating the background hidden by removed original ink. No font renders.
Busy/low-contrast or non-neutral outputs may fail closed; exact font identity
and occluded background are not automatically proven. Human review is required.

Source/mask/prompt, raw provider output and geometry hashes remain retained.
Each explicit model request has one independent Attempt; no automatic retries.
Source-stroke correction still makes zero new provider calls.
Compatible fallback:d649e26cf9e3cbc6c2de65b5fa71c647344e609e.
Older v1-v4/local-stroke payloads remain byte-compatible; do not roll back new
v5 payloads to unsupported readers. Product remains NOT_RELEASE_READY.
