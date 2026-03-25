# Plan: Brand App with Website Scraping & Onboarding

Create a new `brand` Django app with a OneToOne Brand model per user, a sidebar entry, a brand detail screen with a "Scrape from Website" button that opens a modal, scrapes the site via Firecrawl + OpenAI, optionally imports Shopify products, and extracts images/logo. Add a post-signup onboarding page that offers the same scrape flow (skippable).

---

### Phase 1: Brand App Scaffolding

**Step 1 — Create Django app & model**
- `startapp brand` inside `webapp/`
- `Brand` model: `user` (OneToOneField → AUTH_USER_MODEL), `website_url` (URLField), `name` (CharField 255), `summary` (TextField), `language` (CharField 100), `style_guide` (TextField), `logo` (ImageField → `brand/logos/%Y/%m/`), `created_at`, `updated_at`

**Step 2 — Register app & URLs**
- Add `'brand'` to `INSTALLED_APPS` in [webapp/core/settings.py](webapp/core/settings.py)
- Create [webapp/brand/urls.py](webapp/brand/urls.py) with `app_name='brand'`: routes for detail (`''`), scrape modal (`'scrape-modal/'`), onboarding (`'onboarding/'`)
- Include in [webapp/core/urls.py](webapp/core/urls.py): `path('brand/', include('brand.urls'))`

**Step 3 — Add sidebar entry**
- In [webapp/templates/base.html](webapp/templates/base.html), add "Brand" link under "Main" section with `up-follow` and a brand icon SVG

---

### Phase 2: Brand Detail Screen

**Step 4 — Brand detail view & template**
- `brand_detail` view: `@login_required`, `get_or_create` Brand for user
- Template shows brand fields in card layout, with "Scrape from Website" button (`up-layer="new" up-mode="modal" up-history="false"`)
- Empty state if no data yet, encouraging scrape

**Step 5 — Brand edit form**
- `BrandForm` ModelForm for inline editing on detail page
- Fields: name, website_url, summary, language, style_guide, logo

---

### Phase 3: Scrape Flow (Modal + Backend)

**Step 6 — Scrape URL modal**
- Template with URL input, spinner pattern (reuse from [shopify_import.html](webapp/media_library/templates/media_library/shopify_import.html))
- On success: `_accept_layer_response()` (close modal + reload detail)

**Step 7 — Scrape backend logic** (`_scrape_brand_data(user, url)`)
- **7a**: Firecrawl `fc.scrape(url, formats=['markdown', 'html'])` — get markdown for OpenAI, HTML for images
- **7b**: OpenAI extraction — send markdown with structured prompt → extract `name`, `summary`, `language`, `style_guide`, `logo_url` as JSON
- **7c**: Logo — download identified logo URL → save to Brand `logo` ImageField
- **7d**: Import all images — reuse `_import_url_images()` from [media_library/views.py](webapp/media_library/views.py)
- **7e**: Shopify check — call `_import_shopify_products()` from [media_library/views.py](webapp/media_library/views.py); skip silently if not Shopify
- **7f**: Save all extracted data to Brand model

---

### Phase 4: Onboarding After Signup

**Step 8 — Onboarding page**
- Full-page layout (extends [base_auth.html](webapp/accounts/templates/account/base_auth.html), not base.html — no sidebar)
- Welcome message + same URL input/scrape form + Skip button → redirect to `/`

**Step 9 — Custom allauth adapter**
- [webapp/brand/adapter.py](webapp/brand/adapter.py): override `get_signup_redirect_url()` → redirect to `/brand/onboarding/` for new users without brand data
- Add `ACCOUNT_ADAPTER = 'brand.adapter.BrandAccountAdapter'` to settings

**Step 10 — Onboarding POST handler**
- On scrape success: redirect to `/`
- On error: re-render with error
- Skip: plain link to `/`

---

### Phase 5: Dependencies & Wiring

**Step 11** — Add `openai` to [requirements.txt](requirements.txt), install. Use `OPENAI_API_KEY` env var.

**Step 12** — Add `webapp/static/js/brand.js` if needed (spinner likely handled by inline onclick pattern). Load in [base.html](webapp/templates/base.html).

---

### Relevant Files
- [webapp/media_library/views.py](webapp/media_library/views.py) — reuse `_import_shopify_products()` and `_import_url_images()`
- [webapp/core/settings.py](webapp/core/settings.py) — INSTALLED_APPS, ACCOUNT_ADAPTER
- [webapp/core/urls.py](webapp/core/urls.py) — include brand URLs
- [webapp/templates/base.html](webapp/templates/base.html) — sidebar nav, JS loading
- [webapp/accounts/templates/account/base_auth.html](webapp/accounts/templates/account/base_auth.html) — onboarding layout base

### Verification
1. `makemigrations brand && migrate` — no errors
2. Sidebar: "Brand" link visible, active state works
3. `/brand/` — empty state for new user, populated for scraped brand
4. Scrape modal: enter URL → spinner → brand data populated
5. Shopify URL → product ImageGroups created in media library
6. Any URL → ImageGroup created with scraped images
7. Logo extracted and displayed on brand detail
8. New signup → onboarding page → scrape or skip → dashboard
9. Returning user with brand → goes straight to dashboard
10. Invalid URL / missing API keys → appropriate errors shown

### Decisions
- **1:1 Brand** per user (OneToOneField, get_or_create)
- **Separate fields**: `language` (CharField) + `style_guide` (TextField)
- **Logo**: ImageField on Brand (not FK to media_library)
- **Onboarding**: full-page post-signup redirect via custom allauth adapter
- **Synchronous scrape** (no Celery) — same spinner pattern as existing imports
- **OpenAI model**: `gpt-4o-mini` for structured extraction (JSON mode)
- **Reuse** `_import_shopify_products` and `_import_url_images` from media_library directly

### Further Considerations
1. **Logo extraction strategy**: (A) ask firecrawl.scrape("URL", formats=["markdown", "branding"]) to identify logo URL from content then response.data.branding.logo. 
2. **Brand sidebar placement**: After Overview