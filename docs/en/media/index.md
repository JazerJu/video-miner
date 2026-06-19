# Media Credentials

Media Credentials configure platform login data, browser cookies, the shared proxy, and yt-dlp dependency status. These settings affect Bilibili, YouTube, Podcast downloads, and proxy switches for LLM requests.

## Bilibili credentials

| Setting | Type | Default | Description |
| --- | --- | --- | --- |
| Bilibili Login SESSDATA | Password input | Empty | Used to log in to Bilibili for HD videos and subtitles. |
| Copy | Button | None | Copies the current SESSDATA value. |
| Save and validate | Button | None | Saves and validates the Bilibili session. A valid result can show account name, UID, and expiration time. |
| Login status | Status message | Not configured | Shows not configured, configured, valid, invalid, or expired. |

## YouTube cookies.txt

| Setting | Type | Default | Description |
| --- | --- | --- | --- |
| cookies.txt upload | File upload | Not uploaded | Uploads a browser-exported YouTube `cookies.txt` file for videos that require login. |
| Overwrite upload | File upload | None | If a cookies file already exists, uploading a new file replaces it. |
| File info | Hover tooltip | None | Shows modified time and file size. |

## Network Proxy Settings

| Setting | Type | Default | Description |
| --- | --- | --- | --- |
| Proxy Server Address | Text input | Empty | Shared proxy address, such as `http://host.docker.internal:7890`. Leave blank to disable proxy. |
| Use proxy for streaming downloads | Checkbox | Off | Sends YouTube and Podcast downloads through the proxy. |
| Use proxy for Bilibili downloads | Checkbox | Off | Sends Bilibili downloads through the proxy. |
| Use proxy for subtitle splitting | Checkbox | Off | Sends Split LLM requests through the proxy. |
| Use proxy for subtitle translation | Checkbox | Off | Sends Translate LLM requests through the proxy. |

## yt-dlp management

| Setting | Type | Default | Description |
| --- | --- | --- | --- |
| yt-dlp Version | Status display | Backend detected value | Shows the current yt-dlp version. |
| EJS Script | Status display | Backend detected value | Shows yt-dlp EJS support status. |
| Node.js Runtime | Status display | Backend detected value | Shows whether Node.js is available and its version. |
| Node Requirement | Status display | Backend detected value | Shows the required Node.js version. |
| Install yt-dlp dependencies | Button | None | Installs `yt-dlp[default]`, `yt-dlp-ejs`, `pycryptodomex`, `brotli`, and related dependencies. |
| Check and upgrade yt-dlp | Button | None | Checks the latest version and upgrades yt-dlp and dependencies. |
| Refresh Status | Button | None | Reloads yt-dlp management status. |

## How to get Bilibili SESSDATA

1. Log in to Bilibili in your browser.
2. Open the browser developer tools.
3. Find Bilibili cookies in the application or storage panel.
4. Copy the value named `SESSDATA`.
5. Paste it into the settings panel and click Save and validate.

## How to prepare YouTube cookies.txt

1. Log in to YouTube in your browser.
2. Install the Get cookies.txt LOCALLY browser extension.
3. Export `cookies.txt`.
4. Upload the file in Media Credentials.

> Docker deployments can also configure proxy with the `HTTPS_PROXY` environment variable. The proxy address in this panel is the application-level shared proxy.

---

[Back to English docs](../) | [Previous: Transcription Engine](../transcription/) | [Next: API Token Management](../api-token/)
