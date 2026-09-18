# 小型项目资料库：第一版

面向一个论文项目、约 200 篇资料。SQLite + 本地文件，无独显、向量数据库或新增 Python 依赖。200 是典型规模而非硬上限；测试覆盖 200 条来源登记，不等于已测试 200 篇大 PDF 的阅读速度。

## 本版能做什么

- 归档本地 PDF、DOCX、EPUB、TXT、Markdown、HTML 文件（单文件最多 50 MiB）。
- 文件按 SHA-256 保存，原始输入删除后仍可回溯归档副本。
- 保存方法卡、公式卡和实验草案；引用明确的来源 ID 与版本。
- 回溯实验步骤 → 方法/公式 → 来源文件，检查归档文件是否丢失或改变。
- 关键词搜索元数据与已登记卡片；追加版本，不覆盖历史。
- real/demo 分开保存。新领域库允许真实资料与草案登记，旧真实实验结论限制不变。

**不做：** 自动读完整 PDF、OCR、下载论文或网页、自动抽取公式、验证公式科学适用性、执行实验。这些步骤仍由 Agent 的阅读/搜索工具和研究者完成；本库保存与检查其输入结果。

## 安装与第一个完整例子

按根 README 安装并运行 setup_local.py，再执行：

```bash
python scripts/library_demo.py
```

脚本只写领域库的 demo 命名空间：归档仓库自带教学笔记，建立公式卡和实验草案，然后打印回溯到的文件路径。笔记不是论文，内容与计划只是教学示例；不产生实验结果或真实证据。重复运行读取同一演示记录，不覆盖它。

## 接入自己的资料

1. 在项目根目录创建 inbox，把授权使用的资料复制进去；该目录被 Git 忽略。
2. 在该项目中打开新的 Codex 会话，确保 MCP 有 library_status 等新工具。
3. 使用以下提示：

```text
$research-expert
请为本论文项目建立小型领域知识库。我授权归档 inbox 中的这些资料，
并保存你读取后整理的方法、公式卡和实验草案。
先检查已有库和资料覆盖，说明每份资料实际读到哪里。
公式能定位到具体文献即可，不强制页码。
先给出知识缺口与两条实验思路，不执行实验，也不记录已完成的结果。
```

上传文件如果位于工作区之外，需要先复制到工作区 inbox。register_source 不接受任意外部文件路径。

## 七个工具

| 工具 | 用途 |
| --- | --- |
| library_status | 看是否建库、各类型数量；空库查询不创建文件 |
| register_source | 归档文件及题名/原网址；默认阅读深度 not_assessed |
| search_knowledge | 查询最新来源、方法、公式、草案；query 为空列出，limit 最大 250 |
| get_knowledge | 按 ID 或明确版本读取领域记录 |
| save_knowledge_card | 保存方法或公式草案 |
| save_experiment_plan | 保存每步有依据的实验草案 |
| trace_knowledge | 追溯引用并验证归档文件哈希 |

七个工具 namespace 默认 real。旧工具 get_record/get_provenance 查询的是旧研究状态库，不能用于查询新的领域卡片。

### 来源

register_source 必填 source_id、file_path、title。source_type 为 paper/book/web/user_note；网页还须 origin 原 URL，file_path 指向已保存的本地快照。本工具不抓取网址。

相同内容文件按哈希复用；相同 ID 修改时 expected_version 须是当前版本。改变原文件不会自动改变归档，应重新登记来源版本。页码可不提供。

### 方法/公式卡

save_knowledge_card 参数：card_id、kind(method/formula)、data、sources、expected_version。

data 公共必填文本：title、content、conditions、limitations、basis、rationale。
- basis：direct / adapted / original。
- method 另填 procedure（文本）。
- formula 另填 expression（文本）与 symbols（符号到含义/单位的字典）。
- 可选 locator、reading_note；没有页码不影响保存。
- sources 是非空列表，例如 [{"id":"SRC-001","version":1}]，必须指向同一命名空间的来源对象。

reading_note 是调用者声明的阅读记录，不是系统独立核验。来源归档状态也不会因为有卡片自动升级为“已阅读全文”。

### 实验草案

save_experiment_plan 参数为 plan_id、data、expected_version。
data 必须含 title、question、data_requirements、alternatives、outputs、interpretation_limits（均为文本），以及非空 steps 列表。

每步字段：action、purpose、basis、rationale（文本），refs（非空精确 ID/版本列表）。refs 可指向 source/method/formula，所有路径最终必须回到存在且哈希正确的归档文件。

未实现运行和科学审查，保存结果固定为 draft_unverified，不能表示已完成、已批准或科学有效。对象不会自动执行。

## 更新与备份

新对象 expected_version=0；更新填当前版本。先 get_knowledge 读取和审查，再保存新版本。引用版本不会随来源更新而自动漂移：公式引用 SRC-001@1，即使已有 @2，仍然追溯 @1；需要 Agent 判断是否修订公式卡。

停止 MCP 写入后，完整备份 spatial-unit-kb/data/library。数据库和 files 必须一起备份；只拷贝数据库无法恢复来源文件。所有领域数据被 Git 忽略。不要手工修改 SQLite 或归档文件。

归档和数据库提交不是跨文件系统事务；意外失败可能留下未引用的归档文件，暂不自动清理，不影响已提交引用。哈希用于发现意外更改，不提供抵抗恶意重写的安全保证。
