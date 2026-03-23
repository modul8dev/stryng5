# Project Guidelines

## Architecture
- Django project root is `webapp/` (contains `manage.py` and project settings in `core/`).
- `accounts` defines the custom user model (`accounts.CustomUser`); always use `get_user_model()` in app code.
- Shared templates live in `webapp/templates/` (`base.html` + `includes/`), with app templates under `webapp/<app>/templates/<app>/`.
- Frontend styling uses Tailwind + DaisyUI. Source CSS is `webapp/static/css/src/input.css`; generated CSS is `webapp/static/css/src/output.css`.

## Build And Test
- Python dependencies (workspace root): `pip install -r requirements.txt`
- Python dependencies are installed directly into the workspace, not in a virtualenv or container. Use `pip list` to verify installed packages.
- New Python dependencies should be added to `requirements.txt` and installed in the workspace environment.
- Django commands (from `webapp/`):
	- `python manage.py migrate`
	- `python manage.py runserver`
- Frontend dependencies (workspace root): `npm install`
- Tailwind watcher (workspace root): `npm run watch:css`
- Do not write or run tests

## Conventions
- Keep route ownership at app level: define routes in `home/urls.py` (or app-specific `urls.py`) and include from `core/urls.py`.
- Preserve existing Unpoly navigation attributes (`up-nav`, `up-follow`, `up-main`) in template updates.
- Use app-local templates and static assets instead of adding one-off files in unrelated directories.
- When fragment is to be rendered in a modal, use `up-mode="modal"` and `up-history="false"` on the trigger link to prevent URL changes.

## Pitfalls
- Most Django commands fail if run from the workspace root; run them from `webapp/`.
- README examples may imply different paths; trust repository layout (`webapp/manage.py`) when in doubt.
- unpoly.compiler cannot be located in fragment since unpoly does not execute scritp tags in fragments. If you need to use unpoly.compiler, you must include it in the base template and ensure it is available globally.