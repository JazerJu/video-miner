# API Token Management

API tokens allow agents and CLI clients to access the VidGo API. A token is shown only once after creation. After that, the list shows active token entries and creation times.

## Token management

| Setting | Type | Default | Description |
| --- | --- | --- | --- |
| Generate Token | Button | None | Opens a credentials confirmation dialog. Enter username and password to create a token. |
| Token List | List | Empty | Shows active tokens and creation times. If no token exists, the panel shows No active tokens. |
| Revoke | Button | None | Opens a credentials confirmation dialog. Enter username and password to revoke a token. |
| Username | Text input | Empty | Required for sensitive operation confirmation. |
| Password | Password input | Empty | Required for sensitive operation confirmation. |
| Copy token | Button | None | Copies the full token value after successful creation. |

## API usage

Add this request header when calling the VidGo API:

```http
Authorization: Token <token>
```

## Agent endpoint and media links

Agent tools should use a VidGo web/API base URL such as `http://localhost:8080`, `http://<server-ip>:8080`, or your HTTPS reverse-proxy domain. This base URL is separate from an OpenCode MCP URL such as `http://127.0.0.1:8787/sse`, which only points to the MCP transport.

Summary markdown may contain root-relative image links such as `/media/vidunder/output/.../slide_000.png`. Keep those links unchanged unless you want direct clickable URLs. When needed, prepend the VidGo web/API base URL chosen by the user. For SSH tunnel testing with localhost addresses, forward both the MCP port and the VidGo web/API port, for example `8787` and `8080`.

## How to generate a token

1. Click Generate Token.
2. Enter the current account username and password.
3. Click Confirm.
4. Copy the token immediately and store it safely.

## How to revoke a token

1. Click Revoke in the token list.
2. Re-enter username and password.
3. Click Confirm.
4. Confirm that the token is removed after the list refreshes.

> You cannot view the full token again after closing the creation dialog. If it is lost, revoke the old token and generate a new one.

---

[Back to English docs](../) | [Previous: Media Credentials](../media/) | [Next: Video Understanding](../video-understanding/)
