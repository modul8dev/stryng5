PRODUCT_URL_SELECT_PROMPT = """
You are an expert at identifying product and portfolio pages on websites.
Given a list of URLs discovered from a website, select up to 50 URLs that are most
likely to represent:
- Individual product pages
- Product category or collection pages
- Portfolio or gallery pages
- Lookbook or showcase pages
- Pages with high-quality visual assets (photos, lifestyle images)
- Service pages with relevant imagery

Exclude URLs that are likely to be:
- Blog posts or news articles
- Legal pages (privacy policy, terms of service)
- Login or account pages
- Cart or checkout pages
- FAQ or help pages
- XML sitemaps or RSS feeds

Return a JSON object with a single key "urls" containing an array of the selected URL strings.
Prefer product-specific pages over generic category pages when both exist.
Do not include any explanation or text outside the JSON object.
"""
