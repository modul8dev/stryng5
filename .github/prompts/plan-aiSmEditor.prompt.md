## Plan: AI-Powered Social Media Post Editor

Transform the existing social media post composer modal into a dual-mode editor: **Create with AI** (guided generation from seed assets/topic) and **Edit in editor** (current editor + AI toolbar). Both modes share the same draft state. New posts default to AI mode; existing posts default to editor mode.

---

### Phase 1: Model & Database Changes

1. Add fields to `SocialMediaPost`: `topic` (CharField), `post_type` (choices: product/lifestyle/ad), `ai_instruction` (TextField)
2. Add `SocialMediaPostSeedImage` model (FK to post + FK to Image + sort_order)
3. Run migrations
4. Update `SocialMediaPostForm` for new fields

### Phase 2: Prompt Templates

5. Create `webapp/prompts/social_media_generate.py` — text generation prompt with brand data + image descriptions + topic + post type as template variables
6. Create `webapp/prompts/social_media_topic.py` — topic suggestion prompt from seed assets + brand context
7. Create `webapp/prompts/social_media_edit.py` — dictionary of action-to-prompt mappings (rewrite, improve, shorten, expand, make engaging, adapt to platform, add CTA, fix grammar, freeform)

### Phase 3: AI Service Layer

8. Create `webapp/social_media/ai_services.py` with functions:
   - `suggest_topic(brand, seed_images)` → str (OpenAI)
   - `generate_post_text(brand, topic, post_type, seed_images, platforms)` → str (OpenAI)
   - `generate_post_image(brand, topic, post_type, seed_images, user)` → Image instance (Gemini `gemini-3.1-flash-image`)
   - `edit_text(action, text, brand, ...)` → str (OpenAI)
9. Add `google-genai` to `requirements.txt`

### Phase 4: API Endpoints

10. Add 3 POST endpoints to `social_media/urls.py`:
    - `ai/suggest-topic/` — returns `{"topic": "..."}`
    - `ai/generate/` — returns `{"text": "...", "image": {"id": N, "url": "..."}}`
    - `ai/edit-text/` — returns `{"text": "..."}`
11. Implement views in `social_media/views.py` — all `@login_required`, `@require_POST`, return `JsonResponse`

### Phase 5: Template Rework

12. Update `post_form.html` header with segmented mode switch ("Create with AI" | "Edit in editor")
13. Add **Create with AI** panel: topic field (auto-suggested), post type selector, seed asset picker (reuses image_picker), Generate button with progress states
14. Enhance **Edit in editor** panel: AI toolbar above textarea (Rewrite, Improve, Shorten, Expand, Make engaging, Adapt to platform, Add CTA, Fix grammar) + freeform instruction row below textarea with Replace/Insert/Append buttons
15. Both modes share same form draft state — switching is purely visual

### Phase 6: JavaScript Updates

16. Extend `postComposer` Alpine data in `social_media.js`:
    - `mode` ('ai'/'editor'), `topic`, `postType`, `seedImages`, `generating`, `generationStep`, `aiProcessing`
17. Add methods: `switchMode()`, `suggestTopic()` (auto on seed change), `generatePost()` (→ populate text + image → switch to editor), `aiEditAction()`, `aiCustomInstruction()`
18. Seed image picker handling (separate from shared images)

### Phase 7: Save Flow Updates

19. Update `post_create`/`post_edit` views to save topic, post_type, seed images *(depends on Phase 1)*
20. Add seed image JSON sync in JS (same pattern as platform_override_media_json)

---

### Relevant Files

**Modify:**
- `webapp/social_media/models.py` — new fields + SeedImage model
- `webapp/social_media/views.py` — AI endpoints + updated save flow
- `webapp/social_media/forms.py` — new form fields
- `webapp/social_media/urls.py` — AI routes
- `webapp/social_media/admin.py` — SeedImage inline
- `webapp/social_media/templates/social_media/post_form.html` — dual-mode UI
- `webapp/static/js/social_media.js` — extended Alpine component
- `requirements.txt` — add google-genai

**Create:**
- `webapp/prompts/social_media_generate.py`
- `webapp/prompts/social_media_topic.py`
- `webapp/prompts/social_media_edit.py`
- `webapp/social_media/ai_services.py`

**Reference:**
- `webapp/brand/models.py` — Brand fields for prompt context
- `webapp/media_library/models.py` — Image/ImageGroup for seed data
- `webapp/prompts/brand_extract.py` — existing prompt pattern

---

### Verification

1. Open new post modal → defaults to "Create with AI" mode
2. Select seed images → topic auto-suggests via API
3. Click Generate → spinner + progress steps → text + image generated → auto-switch to editor
4. In editor: select text → click "Shorten" → AI rewrites selection in-place
5. Type custom instruction → "Replace selection" → AI applies it
6. Switch modes without losing any data
7. Save/schedule works from both modes
8. Open existing post → defaults to "Edit in editor"

---

### Decisions

- **Image gen**: Gemini (`gemini-3.1-flash-image`) via `google-genai` package
- **Text gen**: OpenAI (existing)
- **Topics**: On-the-fly when seed assets change or user start to type in topic field (debounced)
- **No streaming**: Full result, stepped spinner progress states
- **Seed images ≠ shared images**: Seeds are AI input context; shared images are what gets posted. Generated output goes to shared images.
- **Generated images**: Saved as Images in media_library, added to post's shared media
