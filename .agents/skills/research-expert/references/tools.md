# 本机工具与边界

项目根为当前克隆目录。Python 使用用户选定的环境；安装与配置见根 README。
MCP 配置 ID：`research-kb`。工具显示前缀由宿主决定，以实际发现的工具为准。

## 工具选择

| 用途 | MCP 工具 |
|---|---|
| 当前研究状态、开放问题 | get_current_state、get_open_questions |
| 指定对象或证据版本 | get_record、get_evidence |
| 来源链与原文件新鲜度 | get_provenance、check_source_freshness |
| 历史决策、研究记忆 | get_decisions、get_research_memory、search_research_memory |
| 文本证据检索 | find_evidence（关键词 AND 子串匹配，无向量模型） |
| 存储校验 | validate_state |
| 不写入地验证提议 | validate_proposal |
| 已授权的 demo 批次提交 | commit_demo_proposal |

默认读取 namespace=real；demo 必须显式说明。所有工具仅访问配置中的固定库，不接受任意 store 路径。

真实库：`spatial-unit-kb/data/real_summary`；demo：`spatial-unit-kb/local_tools/data/demo_working`。

## 提议对象

`proposals` 是列表，每项字段严格为 id、kind、data、refs、scope、category、expected_version。
新对象 expected_version=0；修订用当前版本。refs 的每项为明确的 id/version；data 必需字段见 `spatial-unit-kb/phase1a/store.py` 的 FIELDS/ROLES。不要猜测字段。

先 validate_proposal，获得 proposal_sha256；保持原批次不变再在用户授权范围内调用 commit_demo_proposal，传入 validated_sha256。该值是批次一致性校验，不是用户授权证明。提交时再次校验版本，过期则重新读取后处理，不能强行改数字覆盖。

真实库的写入不经此 MCP 暴露。不要为了满足请求把 real 改为 demo 后声称已记录真实结论。

## 只读 CLI 后备

```sh
python spatial-unit-kb/local_tools/research_kb.py --store spatial-unit-kb/data/real_summary --namespace real state
python spatial-unit-kb/local_tools/research_kb.py --store spatial-unit-kb/data/real_summary --namespace real list --kind OpenQuestion
python spatial-unit-kb/local_tools/research_kb.py --store spatial-unit-kb/data/real_summary --namespace real provenance RS-SUMMARY-001
```

该后备不是 MCP 已加载证明。不要直接编辑 records.json，也不要为查询安装依赖。
