# API 令牌

API 令牌用于 Agent 和 CLI 访问 Video-Miner API。令牌只在创建后显示一次，之后列表中只显示可识别的令牌条目和创建时间。

## 令牌管理

| 设置 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| 生成令牌 | 按钮 | 无 | 打开凭据确认弹窗，输入用户名和密码后创建新令牌。 |
| 令牌列表 | 列表 | 空 | 显示活跃令牌和创建时间。没有令牌时显示暂无活跃令牌。 |
| 吊销 | 按钮 | 无 | 打开凭据确认弹窗，输入用户名和密码后吊销令牌。 |
| 用户名 | 文本输入 | 空 | 敏感操作确认时填写。 |
| 密码 | 密码输入 | 空 | 敏感操作确认时填写。 |
| 复制令牌 | 按钮 | 无 | 令牌生成成功后复制完整令牌值。 |

## API 使用方式

请求 Video-Miner API 时，在请求头中加入：

```http
Authorization: Token <token>
```

## 在Opencode中使用 Video-Miner MCP

以Linux/Mac系统为例，编辑`~/.config/opencode/opencode.jsonc`：

```
{
    "mcp":{
        (...), # 其他mcp
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

## Agent 地址与媒体链接

Agent 工具应使用 Video-Miner Web/API 的可访问地址，例如 `http://localhost:8080`、`http://<server-ip>:8080` 或 HTTPS 反向代理域名。这个地址和 OpenCode MCP 地址不是同一个概念；例如 `http://127.0.0.1:8787/sse` 只表示 MCP transport 入口。

> 默认的Docker 容器会启动 Video-Miner Web/API(wsgi) 和 MCP(asgi) 两个服务。

使用MCP获取视频的摘要时，返回的 Markdown 中可能包含 `![](/media/vidunder/output/.../slide_000.png)` 这样的相对链接,对应的网络Url为`http://<server-ip>:<server-port>/media/vidunder/output/.../slide_000.png`.

## 如何"生成令牌"

1. 点击生成令牌。
2. 输入当前账户的用户名和密码。
3. 点击确认。
4. 立即复制弹窗中的令牌并保存到安全位置。

## 如何"吊销令牌"

1. 在令牌列表中点击吊销。
2. 重新输入用户名和密码。
3. 点击确认。
4. 列表刷新后确认令牌已移除。

> 令牌生成后无法再次查看完整值。如果丢失，请吊销旧令牌并生成新令牌。


---

[返回中文文档首页](../) | [上一节：媒体凭据](../media/) | [下一节：视频理解](../video-understanding/)
