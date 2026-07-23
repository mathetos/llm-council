# Perplexity crawlers

- URL: https://docs.perplexity.ai/docs/resources/perplexity-crawlers
- Accessed: 2026-07-23
- Relevance to decision class: high

## Extractable claims

1. PerplexityBot is designed to surface and link websites in Perplexity search results; it is not used to crawl content for AI foundation models. (evidence)
2. To appear in Perplexity search results, allow PerplexityBot in robots.txt and permit published IP ranges (WAF allowlisting may be required). (evidence)
3. Perplexity-User fetches pages for user questions; generally ignores robots.txt because the fetch is user-requested; also not used for foundation-model training. (evidence)
4. robots.txt setting changes may take up to 24 hours to reflect. (evidence)
5. Official IP JSON endpoints are the source of truth for WAF rules and are updated regularly. (evidence)

## Notes

Decide/kill for Perplexity visibility often fails at WAF even when robots.txt allows the bot.
