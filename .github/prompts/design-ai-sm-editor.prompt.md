Here is a cleaner way to structure it so both AI flows feel natural and not like two separate tools crammed into one modal.

## Recommended layout

### 1. Top-level mode switch inside the post modal

At the top of the modal, under title or in the header area, add a clear segmented switch:

* **Create with AI**
* **Edit in editor**

This should be visible immediately when the modal opens.

Behavior:

* **New post modal** opens in **Create with AI** by default
* **Existing post edit modal** opens in **Edit in editor** by default, but user can switch to Create with AI if they want to regenerate from assets/topic

This keeps one modal and one post workflow, instead of splitting into separate screens.

---

### 2. Create with AI mode layout

This mode should feel like a guided generation flow, not a classic editor.

#### Main area

Order of sections:

**A. Input block**

* Post topic - Topic must be ai suggested by ai based on selected seed assets name and descrition and brand data that is already have elsewhere. This is added to as prompt template variables
* post type (Product, Lifestyle, Ad)

**B. Seed assets**

* Selected product / image group / individual images from imaga-picker
* Thumbnails with remove button
* Button: **Select from library**
* Small note: AI uses selected images, image names, and descriptions as source context

**C. Generation options**

* Generate button


#### Primary action

Sticky footer or header action:

* **Generate post**

While generating:

* button shows spinner
* modal sections become read-only
* show progress states such as:

  * Preparing inputs
  * Generating text
  * Generating image
  * Applying result

After generation:

* automatically switch focus to **Edit in editor** mode with generated text and generated image already loaded
* optionally show small success banner: “Draft generated. You can now refine it.”

This is important: **AI generation should lead into editor mode**, not remain a dead-end result screen.

---

### 3. Edit in editor mode layout

This mode should stay close to your first screenshot, but add AI as an assistant layer around the editor instead of making it another separate screen.

#### Left/main area

Keep:

* Title
* Platform tabs
* Content editor
* Shared images / attached images

Enhance content area with AI controls directly above or below the textarea.

#### AI toolbar for text

Add compact action buttons:

* Rewrite
* Improve
* Shorten
* Expand
* Make more engaging
* Adapt to platform
* Add CTA
* Fix grammar

These should work on:

* selected text, if any
* otherwise full text

#### Freeform AI instruction row

Below toolbar:

* input field: **Tell AI what to change**
* action buttons:

  * **Replace selection**
  * **Insert below**
  * **Append to post**

This gives both guided actions and open-ended control.

#### Images area

In editor mode, image AI should also be available but secondary:

* Add images
* Replace image with AI variation
* Generate new image from current post
* Regenerate based on selected seed images

This keeps image generation connected to the post rather than hidden in another workflow.

---

### 4. Best UX for switching between modes

Do not treat the modes as two unrelated tabs with duplicated state.

Instead:

* **Create with AI** = generation setup
* **Edit in editor** = manual refinement and AI-assisted editing

Both modes should work on the **same draft state**:

* same title
* same platforms
* same images
* same generated content

So when user switches modes:

* nothing is lost
* topic/instructions remain
* generated assets remain
* editor content stays in sync

---

## Suggested modal structure

### Header

* Modal title
* mode switch: **Create with AI | Edit in editor**
* actions on right:

  * Cancel
  * Save Draft
  * Schedule
  * Primary action changes by mode:

    * **Generate** in AI mode
    * no extra primary button in editor mode, or use **Apply AI** only when relevant

---


---



### From the editor screen

Current screen is clean, but AI is not visible.

Improve by:

* adding AI toolbar near content box
* adding freeform AI instruction field under the editor
* allowing selected-text actions
* optionally adding a small “AI suggestions” drawer below content

---

## Recommended interaction flow

### Flow A: new post

1. User opens new post modal
2. Default mode is **Create with AI**
3. User selects images/product, enters topic
4. Clicks **Generate**
5. Spinner/progress shown
6. Generated text and image are inserted into draft
7. UI shifts to **Edit in editor**
8. User fine-tunes, saves, or schedules

### Flow B: editing existing post

1. User opens edit modal
2. Default mode is **Edit in editor**
3. User edits text manually
4. Uses AI toolbar or freeform instruction to improve parts of text
5. Optionally switches to **Create with AI** to regenerate image or rebuild draft from assets/topic

---


## Main design principle

The best version is:

**AI generation creates the first draft. Editor AI refines the draft.**

That makes the product easy to understand:

* one mode to create
* one mode to improve

Not two separate products inside one modal.

Use alpine js for reactivnes
Update social media model to store seed images and topics
Use nano banana to generate images.
Use openai to generate text.
Store prompts in exsiting /prompts folder.
Add brand data and image name and desctition to prompts.
