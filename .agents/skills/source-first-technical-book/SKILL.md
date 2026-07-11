---
name: source-first-technical-book
description: Autonomously execute frozen technical-book plans and produce concise, source-verified reStructuredText chapters from runnable experiments, real outputs, pinned source versions, and minimal call paths.
---

# Source-First Technical Book

## 目标

在 `techBook` 仓库中按照已经冻结的书籍计划，持续生成可运行、可验证、可回溯的技术书。正文使用中文 reStructuredText。代码注释使用中文。工作直接提交到 `main`。

## 使用前提

调用本 Skill 前必须已经读取：

1. `AGENTS.md`；
2. `project/STATE.rst`；
3. `project/DECISIONS.rst`；
4. `project/CONTENT_SELECTION.rst`；
5. 当前书籍 manifest；
6. 当前书籍 frozen plan；
7. `sources.lock`。

本 Skill 不负责临时选题。它只执行 frozen plan 中顺序最靠前且尚未完成的章节。

## 仓库边界

- `docs/`：只保存 Sphinx 与 RST 正文。
- `labs/`：保存章节实验、测试、命令脚本和真实输出。
- `manifests/books/`：保存书籍范围、固定计划和当前状态。
- `manifests/chapters/`：保存章节证据和验证状态。
- `sources.lock`：保存外部源码、标准和规范的固定版本。
- `templates/`：保存可复制模板，不参与 Sphinx 构建。
- `dist/`：临时 release 快照，不提交。
- `Narrative/`、文学内容、电影内容和系列编年史不进入本仓库。

## 核心规则

1. 一个章节只回答 frozen plan 中规定的一个可观察问题。
2. 不重新选择、评分、扩展或重排章节。
3. 没有实验、源码、命令、测试、规范或真实输出支撑时，停止生成章节。
4. 版本敏感结论必须绑定 repository、version、commit、platform、architecture、toolchain 和 config。
5. 代码放在 `labs/`，正文通过 `literalinclude` 引用。正文不复制维护第二份代码。
6. 每段必须产生新的判断。重复定义、重复总结和同义改写必须删除。
7. 禁止使用“本章将”“读完本章”“本章总结”“深入理解”制造结构。
8. 不强制章节长度。计划问题解决后立即结束。
9. 构建、实验、引用、审计任一失败时，章节状态保持 blocked。
10. 无法验证的结论要删除或明确标记为假设，不能用流畅文字掩盖缺口。

## 定位当前章节

1. 阅读 `manifests/books/<book>-plan.toml`。
2. 确认计划状态为 `frozen`。
3. 按 `order` 找到最靠前且未完成的章节。
4. 检查其 `prerequisites` 是否全部完成。
5. 检查书籍 source contract 与 `sources.lock`。
6. 条件不足时更新 blocker 并停止，不得跳到后续章节。
7. 条件齐全时，为该固定章节建立 `labs/<book>/<chapter>/`。

书籍 source contract 至少包含：

- upstream repository
- release 或 tag
- exact commit
- architecture
- build config
- compiler/toolchain
- runtime environment

任一字段缺失时，源码级章节不得进入 writing 状态。

## 章节生产流程

### 1. 读取固定问题

直接使用 frozen plan 中的 chapter id、question、outcome、prerequisites 和 required_evidence。只能把问题改写为实验说明，不能改变问题范围。

若实际证据证明计划问题无效或不可分割，停止当前章节并提出 plan revision。普通章节生产过程不能自行修改计划。

### 2. 建立最小实验

实验必须：

- 能独立运行；
- 只保留触发当前机制所需代码；
- 包含精确命令；
- 保存预期输出或采集方法；
- 包含一个失败或边界用例；
- 能由测试或脚本判断成功；
- 覆盖 plan 中列出的 required_evidence。

### 3. 执行并保存证据

保存以下证据中的适用项：

- 编译器输出；
- 程序 stdout/stderr；
- `strace`、`ftrace`、`perf`、调试器或反汇编输出；
- 失败用例输出；
- 固定源码文件和符号；
- 官方标准或规范位置。

禁止编造命令输出。当前环境无法执行时，章节保持 evidence-pending。

### 4. 提取最短源码路径

只记录解释实验所需的函数和数据结构。每个节点必须说明：

- 文件和符号；
- 接收的关键输入；
- 做出的关键判断；
- 传给下一节点的状态。

调用路径不按函数数量追求完整。与当前固定问题无关的分支不扩写成新章节；它们只能记录为未来 plan revision 的输入。

### 5. 写 RST

章节顺序固定为：

1. 问题；
2. 最小实验；
3. 执行命令与真实输出；
4. 观察结果；
5. 最短源码路径；
6. 解释；
7. 失败边界；
8. 两到三个检查题。

允许删除不适用的小节。禁止增加泛化的“背景”“意义”“总结”。

RST 要求：

- 代码使用 `.. literalinclude::`；
- 命令和真实输出使用 `.. code-block:: console`；
- 可执行交互使用 `.. doctest::`；
- 源码符号使用合适的 Sphinx 角色；
- 交叉引用使用稳定 label；
- 不使用 Markdown fenced code block；
- 不写 YAML front matter。

### 6. 审计

执行：

```console
uv run python tools/audit_chapter.py docs
uv run doc8 --max-line-length 100 docs README.rst labs manifests/chapters/README.rst
uv run sphinx-build -W --keep-going -n -b html docs docs/_build/html
```

存在实验测试时继续执行：

```console
uv run pytest
```

### 7. 提交

全部验证通过后直接提交到 `main`。提交信息使用：

- `docs(<book>): add <chapter-id>`
- `lab(<book>): verify <chapter-id>`
- `chore: update source lock`
- `refactor(<book>): remove duplicated explanation`

完成后同步更新 chapter manifest、book plan 中的章节状态和 `project/STATE.rst`。

## 章节质量门槛

章节进入 complete 前必须满足：

- 章节来自当前 frozen plan；
- 前置章节已完成；
- 问题可由实验观察；
- plan 要求的证据全部存在；
- 代码文件真实存在；
- 命令可复制；
- 输出来源明确；
- 源码 commit 已锁定；
- 最短路径中的符号可在该 commit 定位；
- 每个核心判断都有证据；
- 没有重复段落；
- 没有未解释的大型概念树；
- Sphinx warnings-as-errors 构建通过。

## 停止条件

遇到以下情况立即停止扩写当前章节：

- frozen plan 不存在；
- 当前章节不是计划中的下一章；
- source contract 未锁定；
- 前置章节未完成；
- 实验无法执行；
- 输出无法确认；
- 源码符号不存在于固定 commit；
- 计划问题与实际源码范围冲突；
- 资料只能支持推测；
- 修订循环连续两次没有增加可验证信息。

停止时更新 manifest，记录 blocker、已取得证据和下一条可执行动作。不得用更多文字替代缺失证据，也不得临时选择其他章节。

## Release

私有仓库不发布 Pages。稳定内容通过：

```console
uv run python tools/export_release.py
```

导出到 `dist/release/`。只允许 `release-manifest.toml` 白名单中的文件进入未来公共仓库。Skill、审计记录、草稿和失败实验不进入公共 release。
