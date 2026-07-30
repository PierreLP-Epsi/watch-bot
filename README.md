# Cybersecurity + AI watch bot → Discord

Automatically posts new articles from several sources
(general cybersecurity, CVE/CERT, AI news) to a Discord
channel, once a day.

## Setup (10-15 minutes, one time only)

### 1. Create the Discord webhook
1. In your Discord server, go to the channel where you want to receive the watch.
2. Click the channel's gear icon → **Integrations** → **Webhooks** → **Create Webhook**.
3. Copy the **webhook URL** (keep it secret, never share it publicly).

### 2. Create the GitHub repo
1. Go to https://github.com/new, create a repo (public or private, doesn't matter), e.g. `watch-bot`.
2. Upload all the files from this folder to the repo (`watch_bot.py`, `requirements.txt`,
   `.github/workflows/watch.yml`, `README.md`), keeping the folder structure.

### 3. Add the webhook as a secret
1. In the GitHub repo → **Settings** → **Secrets and variables** → **Actions**.
2. Click **New repository secret**.
3. Name: `DISCORD_WEBHOOK_URL`
4. Value: paste the webhook URL copied in step 1.

### 4. Test manually
1. Go to the repo's **Actions** tab.
2. Select the **"Cybersecurity watch -> Discord"** workflow.
3. Click **Run workflow** (button on the right) to run it once.
4. Check that the messages arrive in your Discord channel.

From then on, the bot runs **on its own, once a day at 7am UTC**,
with no need to keep a computer turned on.

## Customization

- **Change the run time**: edit the `cron` line in
  `.github/workflows/watch.yml`. Format: `minute hour day month weekday`
  (always UTC). E.g. `0 6 * * *` = 6am UTC every day.
- **Add/remove sources**: edit the `FEEDS` dictionary at the top of
  `watch_bot.py`. Just a name + an RSS feed URL is enough.
- **Run several times a day**: add more `cron` lines under `schedule:`.

## Sources included by default

| Source | Topic |
|---|---|
| The Hacker News | General cybersecurity |
| BleepingComputer | General cybersecurity |
| CERT-FR (ANSSI) | Official French alerts |
| CISA Advisories | CVE / vulnerabilities (US) |
| Krebs on Security | General cybersecurity |
| Schneier on Security | General cybersecurity |
| SANS Internet Storm Center | General cybersecurity |
| Cisco Talos Intelligence | General cybersecurity |
| The Record | General cybersecurity |
| NCSC UK | Official UK alerts |
| OpenAI News | AI & security |
| Anthropic News | AI & security |
| Google DeepMind Blog | AI & security |
| Google AI Blog | AI & security |
| Claude Blog | AI & security |
| Cursor Blog | AI & security |
| Cloudflare Blog | AI & security |
| Hugging Face - Blog | AI & security |
| Mistral AI | AI & security |
| Korben | French tech / hacking (general, not security-only) |
| ZATAZ | French cybersecurity news |
| Undernews | French cybersecurity news |

> **Anthropic News** and **Claude Blog** have no official RSS feed
> (`anthropic.com/news/rss.xml` and `claude.com/blog` both return nothing
> usable). Both are generated unofficially by the
> [ai-rss-feeds](https://github.com/leontloveless/ai-rss-feeds) project, which
> scrapes the respective pages hourly — same for **Cursor Blog**
> (`cursor.com/rss.xml` exists but serves the HTML app shell, not real RSS).
> These can break silently if the source page's layout changes — the bot
> already skips a broken feed gracefully without affecting other sources (see
> "Feed failure notifications" below), but keep this dependency in mind if
> articles from these three ever stop showing up.
>
> **Google DeepMind Blog**, **Cloudflare Blog**, **Hugging Face - Blog**, and
> **Mistral AI** use each vendor's own official RSS feed. Note the Cloudflare
> feed (`blog.cloudflare.com/rss/`) covers the *entire* blog, not just AI
> posts.
>
> **Korben** is a general French tech/hacking blog, not security-specific —
> expect more noise (gadgets, tips, general tech news) mixed in with the
> occasional cybersecurity/AI article.

You can add other health/CVE-specific feeds if you find some
(many medical device vendors publish RSS advisories).

## Example output

New articles are batched into **digest messages** of up to 5 articles each
(one Discord embed per article), rather than one Discord message per
article — this keeps a run with many new articles from flooding the
channel. Each embed looks like this:

> **[Anthropic confirms Claude is down worldwide](https://www.bleepingcomputer.com/news/anthropic-claude-outage/)**
> Anthropic has confirmed a worldwide outage affecting Claude...
>
> Tags: Artificial Intelligence, Technology
>
> Source: BleepingComputer · 30/07/2026 10:15

which corresponds to this payload sent to the Discord webhook (see
`build_embed()` and `send_digest()` in `watch_bot.py`):

```json
{
  "embeds": [
    {
      "title": "Anthropic confirms Claude is down worldwide",
      "url": "https://www.bleepingcomputer.com/news/anthropic-claude-outage/",
      "description": "Anthropic has confirmed a worldwide outage affecting Claude...",
      "color": 2856665,
      "footer": { "text": "Source: BleepingComputer" },
      "timestamp": "2026-07-30T10:15:00+00:00",
      "fields": [
        { "name": "Tags", "value": "Artificial Intelligence, Technology" }
      ]
    }
  ]
}
```

Notes:
- The `fields` block only appears when the source feed's RSS `<category>`
  tags are populated for that article. Most feeds don't set this — of the 22
  sources configured, only **BleepingComputer**, **OpenAI News**, and
  **Cloudflare Blog** currently do.
- `description` is built from the feed's raw summary with HTML tags
  stripped and entities unescaped (`strip_html()`), then truncated to 300
  characters — otherwise a feed embedding `<p>`/`<a>`/`<img>` tags in its
  description would show up as literal markup in Discord.

### Feed failure notifications

If a feed fails to fetch or parse (timeout, invalid XML, network error), the
bot no longer just logs it to the GitHub Actions output and moves on
silently — it also posts a single dedicated Discord message at the end of
the run listing every feed that failed and why, e.g.:

> ⚠️ 2 feed(s) failed this run
> - **Cisco Talos Intelligence**: HTTPSConnectionPool(...): Read timed out
> - **Korben**: invalid or empty feed

Other feeds are unaffected — one broken source never blocks the rest.

## Technical notes

- The state (which articles have already been sent) is stored in `state.json`,
  automatically committed to the repo by the workflow — no need for an
  external database.
- On the very first run, only the last 3 articles of each feed
  are sent (to avoid a flood of dozens of messages at once).
- Each feed is fetched with a 15-second timeout (`FEED_FETCH_TIMEOUT` in
  `watch_bot.py`) so a slow or hanging server can't stall the whole run.

## Running the tests

`test_watch_bot.py` covers the pure logic (HTML stripping, state
deduplication/capping, digest batching, embed building) with no network
calls involved:

```bash
pip install -r requirements.txt
python3 -m unittest test_watch_bot.py -v
```
