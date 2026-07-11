---
name: source-first-technical-book
description: Autonomously produce concise, source-verified technical books in reStructuredText from runnable experiments, real outputs, pinned source versions, and minimal call paths.
---

# Source-First Technical Book

## 目标

在 `techBook` 仓库中持续生成可运行、可验证、可回溯的技术书。正文使用中文 reStructuredText。代码注释使用中文。工作直接提交到 `main`。

## 仓库边界

- `docs/`：只保存 Sphinx 与 RST 正文。
- `labs/`：保存章节实验、测试、命令脚本和真实输出。
- `manifests/books/`：保存书籍范围、当前状态和首要问题。
- `manifests/chapters/`：保存章节证据和验证状态。
- `sources.lock`：保存外部源码、标准和规范的固定版本。
- `templates/`：保存可复制模板，不参与 Sphinx 构建。
- `dist/`：临时 release 快照，不提交。
- `Narrative/`、文学内容、电影内容和系列编年史不进入本仓库。

## 核心规则

1. 一个章节只回答一个可观察问题。
2. 没有实验、源码、命令、测试、规范或真实输出支撑时，停止生成章节。
3. Roadmap 只作为候选问题池。允许删除、合并、拆分和重新排序。
4. 版本敏感结论必须绑定 repository、version、commit、platform、architecture、toolchain 和 config。
5. 代码放在 `labs/`，正文通过 `literalinclude` 引用。正文不复制维护第二份代码。
6. 每段必须产生新的判断。重复定义、重复总结和同义改写必须删除。
7. 禁止使用“本章将”“读完本章”“本章总结”“深入理解”制造结构。
8. 不强制章节长度。问题解决后立即结束。
9. 构建、实验、引用、审计任一失败时，章节状态保持 blocked。
10. 无法验证的结论要删除或明确标记为假设，不能用流畅文字掩盖缺口。

## 开始一本书

1. 阅读 `manifests/books/<book>.toml`。
2. 检查 `sources.lock` 是否已经固定目标源码。
3. 将首个问题改写为可观察问题，例如“用户态 `read()` 如何进入 VFS”。
4. 为问题建立 `labs/<book>/<chapter>/`。
5. 先完成实验，再创建 `docs/books/<book>/chapter-*.rst`。

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

### 1. 定义问题

用一句话描述输入、可观察动作和需要解释的结果。问题中出现多个独立动作时，拆成多个章节。

### 2. 建立最小实验

实验必须：

- 能独立运行；
- 只保留触发当前机制所需代码；
- 包含精确命令；
- 保存预期输出或采集方法；
- 包含一个失败或边界用例；
- 能由测试或脚本判断成功。

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

调用路径不按函数数量追求完整。与问题无关的分支进入专题索引，不在当前章节展开。

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
- 源码符号使用 `:c:func:`、`:cpp:class:`、`:py:func:` 等合适角色；
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

- `docs(<book>): add <question>`
- `lab(<book>): verify <mechanism>`
- `chore: update source lock`
- `refactor(<book>): remove duplicated explanation`

## 章节质量门槛

章节进入 complete 前必须满足：

- 问题可由实验观察；
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

- source contract 未锁定；
- 实验无法执行；
- 输出无法确认；
- 源码符号不存在于固定 commit；
- 一个问题需要跨越多个独立系统；
- 资料只能支持推测；
- 修订循环连续两次没有增加可验证信息。

停止时更新 manifest，记录 blocker、已取得证据和下一条可执行动作。不得用更多文字替代缺失证据。

## Release

私有仓库不发布 Pages。稳定内容通过：

```console
uv run python tools/export_release.py
```

导出到 `dist/release/`。只允许 `release-manifest.toml` 白名单中的文件进入未来公共仓库。Skill、审计记录、草稿和失败实验不进入公共 release。
