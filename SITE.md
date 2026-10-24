# gd site：静态站点发布

`gd site` 把单个文件或静态文件目录发布到 GD 兼容站点。已验证的 ChatGPT Site：<https://gd-static-publisher.liaoxingyu44.chatgpt.site/>。同一命令也可发布到 `gd site serve` 提供的自有 HTTP 服务。普通 ChatGPT Site 或普通网页地址如果没有 GD 的写入接口，不能只凭网址发布。

## 本地配置

站点列表及写入密钥保存在当前用户的 `~/.gd/sites.json`，不在仓库中。可用 `GD_SITE_CONFIG` 或 `gd site --config <路径>` 指定其他本地配置文件。`gd site list` 不输出密钥。站点地址或类型变更后，需要重新执行 `login`，避免把旧密钥发给新地址。不要提交或分享 `sites.json`。

本机已配置名为 `chatgpt` 的站点，且已保存写入密钥。从 `gd` 仓库根目录运行以下命令；`docs/index.html` 是已发布的 GD 站点页面源文件：

```powershell
gd site list
gd site publish .\docs --site chatgpt
gd site publish .\index.html --as index.html --site chatgpt
```

`publish` 会逐个上传文件，再请求其公开地址的 `HEAD`，核对 `X-GD-SHA256`。`/` 对应站点内的 `index.html`。单个文件最大 20 MB；目录发布跳过隐藏文件、`.git`、`.venv`、`node_modules` 等目录，并拒绝符号链接。发布只新增或覆盖本次文件，不会自动删除站点上的旧文件；多文件发布也不是一次原子切换。

配置另一座已部署 GD 发布器 Worker 的 ChatGPT Site：

```powershell
gd site add another --provider chatgpt --url https://example.chatgpt.site
gd site login another
gd site publish .\dist --site another
```

`login` 在终端隐藏输入；如果经标准输入管道提供密钥，也不会把它写入命令行参数。站点公开浏览不需密钥，写入请求需密钥。ChatGPT Site 的站点代码、R2 绑定和运行时 `GD_PUBLISH_TOKEN` 须先通过 Sites 工作流部署；后续页面内容可由 `gd site publish` 直接更新。

## 自有服务器

`gd site serve` 提供与 ChatGPT Site 相同的 `PUT /__gd/publish/<路径>` 写入接口和公开 `GET/HEAD` 静态文件服务。它默认监听本机 `127.0.0.1:8765`，适合由 HTTPS 反向代理接入；不会自行配置公网 DNS、TLS 证书或开机常驻。示例：

```powershell
New-Item -ItemType Directory -Path D:\sites\public -Force
gd site add myserver --provider self --url https://example.com --root D:\sites\public
gd site login myserver
gd site serve --site myserver --host 127.0.0.1 --port 8765
```

另一个终端执行 `gd site publish .\dist --site myserver`。当 `https://example.com` 的反向代理把请求转给 `127.0.0.1:8765` 时，同一公开地址可完成上传回读；仅在本机调试时，`--url` 可写成 `http://127.0.0.1:8765`。服务器目录应放在受控位置，不要把凭证或源码目录设为站点根目录。

## 与 OSS 的关系

`gd oss` 继续用于对象存储和备份。OSS 默认域名对 HTML 可能返回强制下载响应头，因此直接浏览 HTML 使用 `gd site` 对接的站点。此电脑访问 OSS 若受 APNetwork 路径影响，可运行 `gd oss --direct-wlan ...`；站点发布是 HTTPS 请求，不使用该 OSS 专用选项。
