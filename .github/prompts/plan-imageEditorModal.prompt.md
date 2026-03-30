# Plan: Image Editor Modal

**TL;DR**: Extend the `media_library` app with an image editor modal for AI-powered image creation and editing. Alpine.js manages all in-session state (no DB persistence for sessions). Generated images are saved as `Image` records with a new `generated` type into the media library. Entry points: media library list and social media post composer.

---

**Phase 1: Models & Migration** *(media_library only)*

1. `webapp/media_library/models.py` — add `ImageType` TextChoices (`manual` / `generated`, default `manual`) to `Image`; add `GENERATED` to `ImageGroup.GroupType`
2. Run `makemigrations media_library` + `migrate`

**Phase 2: Views & URLs** *(media_library app)*

3. `webapp/media_library/views.py` — add two new views:
   - `image_editor_modal` (GET) — renders modal; optional `?image_id=` for edit mode; validates ownership; passes `source_image` JSON to template
   - `image_editor_generate` (POST) — JSON body `{prompt, attachment_ids, seed_image_id, group_id|null}`; validates ownership; calls AI service; lazily creates `ImageGroup` (type=`generated`) if `group_id` is null; returns `{image:{id,url}, group_id}`
4. `webapp/media_library/urls.py` — add routes `'image-editor/'` (name `image_editor_modal`) and `'image-editor/generate/'` (name `image_editor_generate`) inside the existing `app_name='media_library'` urlconf

**Phase 3: AI Service**

5. `webapp/social_media/ai_services.py` — add `generate_editor_image(prompt, input_images, brand, user, output_group)`: injects brand context (name, colors, style guide) into the prompt; opens input images as PIL; calls Gemini `gemini-3.1-flash-image-preview`; saves result as `Image(image_type='generated')` into `output_group`; returns the `Image` instance

**Phase 4: Modal Template**

6. `webapp/media_library/templates/media_library/image_editor_modal.html` — standalone fragment (no `{% extends %}`):
   - `<div x-data="imageEditor({...})">` wrapping the full modal
   - **Left canvas**: full-size preview of `currentResult`; history strip of thumbnails at the bottom
   - **Right sidebar**: attached images strip with stable `#N` badge + seed indicator + remove per image; "Add images" button; `{% cotton "ai_textarea" actions="rewrite,improve,shorten,expand" custom_instruction=True auto_hide=True result_mode="replace" %}` wrapping a `<textarea x-model="prompt">`; "Generate" button; "Save / Use result" button
   - Bootstrap data via `json_script` tags for `source_image` (when in edit mode)

**Phase 5: JavaScript**

7. `webapp/static/js/image_editor.js` — `Alpine.data('imageEditor', (config) => ({...}))` with state: `attachedImages[]`, `nextBadge`, `seedImageId`, `prompt`, `generating`, `currentResult`, `history[]`, `groupId`, `error`. Methods: `init()`, `openPicker()`, `pickerAccepted(e)`, `removeAttachment(id)`, `setSeed(id)`, `generate()` (async POST), `selectHistoryItem(run)`, `save()` (calls `up.layer.accept({value:{imageId,imageUrl}})`)
8. `webapp/templates/base.html` — add `<script src="{% static 'js/image_editor.js' %}">` before the Alpine CDN `<script defer>`

**Phase 6: Entry Points**

9. `webapp/media_library/templates/media_library/image_group_list.html` — "Create new image" button in header → `up-href="{% url 'media_library:image_editor_modal' %}"`, `up-mode="modal"`, `up-history="false"`, `up-on-accepted="up.reload('.image-group-list')"`
10. `webapp/media_library/templates/media_library/image_group_grid.html` — edit icon overlay on each image thumbnail → same but with `?image_id={{ image.id }}`
11. `webapp/social_media/templates/social_media/post_form.html` — "Open image editor" button near seed images section; accepted image is pushed into `seedImages` via `up:layer:accepted` handler in `postComposer`

---

## Relevant Files

- `webapp/media_library/models.py` — model changes
- `webapp/media_library/views.py` — two new views
- `webapp/media_library/urls.py` — two new routes
- `webapp/social_media/ai_services.py` — new AI function
- `webapp/templates/base.html` — JS include
- `webapp/media_library/templates/media_library/image_group_list.html` + `image_group_grid.html` — entry points
- `webapp/social_media/templates/social_media/post_form.html` — composer entry point
- NEW: `webapp/media_library/templates/media_library/image_editor_modal.html`
- NEW: `webapp/static/js/image_editor.js`

---

## Verification

1. `/media-library/` → "Create new image" opens editor modal (empty state)
2. Edit icon on an existing image → editor opens with that image pre-loaded as seed #1
3. "Add images" in modal → image picker opens; selected images get stable `#N` badges, picking more appends without resetting existing badges
4. Enter prompt + click Generate → spinner shows; image appears in canvas; history strip updates with thumbnail
5. Click a history thumbnail → canvas switches to that image, prompt is refilled with that run's prompt
6. "Save / Use result" → modal closes; media library refreshes showing the new generated image with `image_type=generated`
7. From post composer → "Open image editor" → generate → result auto-added to `seedImages`

---

## Further Considerations

1. **Picker accepted behavior**: When the image picker is opened from the editor and images are confirmed, do they *replace* any previously attached images or get *appended*? The plan above appends (stable badge numbers). If replace is preferred, the `pickerAccepted` logic changes to rebuild from scratch.
2. **Empty group cleanup**: A new `ImageGroup` (type=`generated`) is created lazily on first generation. If the user opens the editor and never generates, no orphan group is created. If they generate and then discard results, the group and its images persist in the media library — this is intentional.