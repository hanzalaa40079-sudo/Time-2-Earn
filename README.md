
# Time 2 Earn V2 🎬

Free/self-hosted Long Video → Shorts → captions → metadata → publishing starter.

## New in V2
- YouTube OAuth "Connect YouTube" screen
- Facebook Page connection fields
- Free local automatic title/description/hashtags generation
- One-click publish all
- YouTube privacy selector
- Preview/edit metadata before publishing

## Free setup
1. Install Python 3.10+.
2. Install FFmpeg and make sure `ffmpeg` is on PATH.
3. `pip install -r requirements.txt`
4. `streamlit run app.py`

## YouTube connection
Create a Google Cloud project, enable YouTube Data API v3, create OAuth credentials
for a Desktop app, download the JSON and rename it `client_secret.json`.
Run Time 2 Earn and click Connect YouTube.

The app requests only the YouTube upload OAuth scope. Google requires OAuth for
actions that modify the authenticated channel. See official documentation:
https://developers.google.com/youtube/v3/docs/videos/insert
https://developers.google.com/youtube/v3/guides/authentication

IMPORTANT: New/unverified YouTube API projects may have uploads restricted to private
until Google's API audit/review requirements are met. Do not assume a new API project
can immediately publish publicly.

## Facebook Page connection
The app supports direct Page video upload using a Page ID and Page access token.
Create/configure your own Meta app and obtain a Page access token through Meta's
official authorization flow. The Graph API version can be changed with the
META_GRAPH_VERSION environment variable.

Do NOT paste your Facebook password into the app.

## No paid AI API
Whisper runs locally. The title/description/hashtag generator is a free local
keyword heuristic, not a paid LLM. It can be upgraded later to a local LLM if
your computer can handle it.

## Legal/copyright
Only use videos you own or have permission to download, edit and republish.
Platform APIs and terms still apply.
