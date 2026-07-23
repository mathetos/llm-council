# Google-Extended product token (common crawlers)

- URL: https://developers.google.com/search/docs/crawling-indexing/google-common-crawlers
- Accessed: 2026-07-23
- Relevance to decision class: high

## Extractable claims

1. Google-Extended is a robots.txt product token (not a separate crawl user-agent) controlling whether crawled content may be used for training future Gemini models and for grounding in Gemini Apps / Vertex AI grounding products. (evidence)
2. Google-Extended does not impact a site’s inclusion in Google Search and is not used as a ranking signal in Google Search. (evidence)
3. Search generative AI feature appearance is managed separately (Search Console Search generative AI control / snippet controls), not by Google-Extended alone. (inference from pairing with GSC control docs)

## Notes

Common retired-practice trap: blocking Google-Extended expecting AI Overviews opt-out. Keep as constraint in packet.
