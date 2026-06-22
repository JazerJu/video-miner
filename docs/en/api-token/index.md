# API Token Management

API tokens allow agents and CLI clients to access the Video-Miner API. A token is shown only once after creation. After that, the list shows identifiable token entries and creation times.

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

Add this request header when calling the Video-Miner API:

```http
Authorization: Token <token>
```

## Using Video-Miner in OpenCode MCP

On Linux or Mac, edit `~/.config/opencode/opencode.jsonc`:

```jsonc
{
  "mcp": {
    // other MCP servers
    "video-miner": {
      "type": "remote",
      "url": "http://127.0.0.1:8787/sse",
      "headers": {
        "Authorization": "Bearer <Your token>"
      },
      "enabled": true
    }
  }
}
```

## Agent endpoint and media links

Agent tools should use an accessible Video-Miner Web/API address such as `http://localhost:8080`, `http://<server-ip>:8080`, or an HTTPS reverse-proxy domain. This address is separate from the OpenCode MCP address. For example, `http://127.0.0.1:8787/sse` only points to the MCP transport entry.

> The default Docker container starts both the Video-Miner Web/API service (WSGI) and the MCP service (ASGI).

When you get a video summary through MCP, the returned Markdown may contain relative links such as `![](/media/vidunder/output/.../slide_000.png)`. The matching web URL is `http://<server-ip>:<server-port>/media/vidunder/output/.../slide_000.png`.

## How to "Generate Token"

1. Click Generate Token.
2. Enter the current account username and password.
3. Click Confirm.
4. Copy the token immediately and store it safely.

## How to "Revoke Token"

1. Click Revoke in the token list.
2. Re-enter username and password.
3. Click Confirm.
4. Confirm that the token is removed after the list refreshes.

> You cannot view the full token again after closing the creation dialog. If it is lost, revoke the old token and generate a new one.

---

[Back to English docs](../) | [Previous: Media Credentials](../media/) | [Next: Video Understanding](../video-understanding/)
