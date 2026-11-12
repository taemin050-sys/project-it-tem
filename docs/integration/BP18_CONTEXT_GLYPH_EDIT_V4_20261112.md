# Context crop glyph repair v4

Opt-in `preserve_style_context=true` retains v1/v2/v3 request compatibility.
A deterministic square crop around the deliberate native ROI is magnified to
1024×1024 for the image provider. Only the returned ROI is projected back;
outside native source pixels remain exact. No font overlay is performed.

Actual source PNG, alpha mask PNG, prompt bytes and a content SHA manifest are
persisted before billable dispatch. Raw output, transformed-input geometry and
manifest SHA remain in the candidate Receipt. This is not a visual-quality PASS;
spelling, font/style and seams require actual inspection and human acceptance.

Compatible fallback implementation:98a83150f5d6d094f98fc435a7ce385e6dbe14e0.
After v4 admission do not roll back to e17d3308; its reader does not support v4.
No budget/actor/model expansion, automatic paid retries or release acceptance.
