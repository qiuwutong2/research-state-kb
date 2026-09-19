# 验证范围

公开版测试只使用程序构造的合成记录。真实命名空间的接口测试在临时目录中使用合成摘要，属于软件夹具，运行结束后清理，不进入实际研究库。

- phase1a：版本、精确引用、哈希链、批次回滚、两类判断分离、旧格式只读。
- local_tools：CLI、搜索、来源追溯、提交预览和摘要白名单/新鲜度。
- mcp_server：官方 SDK 启动 STDIO 子进程；工具发现、读取、错误处理、demo 提交和重启持久化。

CI 配置面向 Windows 和 Ubuntu；远端实际结果以 GitHub Actions 为准。
软件测试不构成科研盲测或真实机制认证。

本地验收（Windows / Python 3.11）：31 项测试通过（17 存储、12 CLI/导入、2 MCP）。全新临时目录初始化通过；重复初始化拒绝覆盖配置；没有生成真实库。远端 CI 尚未运行。

小项目资料库验收：42 项本地测试通过（17 存储、22 CLI/资料库/摘要、3 MCP），含 200 条来源登记、文件损坏/缺失、旧版本回溯、无依据步骤拒绝、MCP 重启读取。教学脚本重复运行通过。200 条登记不等于真实全文阅读性能基准。

路线网页验收：17 存储 + 33 本地工具/HTTP + 4 MCP = 54 项测试。涵盖分支与汇合、追加保护、固定来源版本、逐参数差异、状态产物要求、角色/命名空间检查、252 节点完整返回和只读 HTTP。Edge 浏览器验证节点选择、比较、文件内嵌、真实/演示隔离、390px 与桌面布局；未测其他浏览器 PDF 插件兼容性。

## Knowledge map validation (2026-09-19)

Current full suite: 59 tests passed locally (17 state, 38 local tools, 4 MCP). MCP discovery exposes 26 tools. Knowledge-map tests cover classifications, stale writes, namespace isolation, exact historical versions, no inherited labels, more than 250 records and revision changes through HTTP.

Headless Edge checks passed: 10-node/four-domain demo, domain filtering, search, file iframe preview, namespace switching, 390px layout without page overflow and no JavaScript errors. A separate temporary database was updated while its browser page stayed open; the new source appeared automatically without manual refresh. Private project records and generated screenshots are not published.
