# OpenAI crawlers overview + publishers FAQ

- URL: https://developers.openai.com/api/docs/bots
- FAQ: https://help.openai.com/en/articles/12627856-publishers-and-developers-faq (updated ~2026-07)
- Accessed: 2026-07-23
- Relevance to decision class: high

## Extractable claims

1. OAI-SearchBot is for surfacing sites in ChatGPT search features; sites opted out of OAI-SearchBot will not be shown in ChatGPT search answers (may still appear as navigational links). (evidence)
2. GPTBot is for crawling content that may be used to train OpenAI generative foundation models; settings are independent of OAI-SearchBot. (evidence)
3. ChatGPT-User is for user-initiated fetches and is not used to determine Search appearance; manage Search with OAI-SearchBot. (evidence)
4. robots.txt changes for search eligibility can take ~24 hours to adjust. (evidence)
5. Publishers allowing OAI-SearchBot can track ChatGPT referral traffic; ChatGPT includes `utm_source=chatgpt.com` on referral URLs. (evidence)
6. For Atlas/agent readiness, OpenAI recommends WAI-ARIA accessibility practices (roles/labels/states) so agents can interpret interactive elements. (evidence)

## Notes

Core ChatGPT visibility control is OAI-SearchBot allow + crawlable content, not GPTBot.
