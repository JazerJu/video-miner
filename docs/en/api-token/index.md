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
