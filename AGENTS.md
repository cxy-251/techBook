# AGENTS.md

## 1. 作用

本文件是 `cxy-251/techBook` 的仓库级操作入口。任何新对话、新 Agent 或新自动任务都必须假设自己看不到历史聊天，并从本文件恢复上下文。

仓库内规则的读取顺序：

1. `AGENTS.md`
2. `project/STATE.rst`
3. `project/DECISIONS.rst`
4. `project/CONTENT_SELECTION.rst`
5. `project/REPOSITORY_MAP.rst`
6. 当前书籍的 `manifests/books/<book>.toml`
7. 当前书籍的 `manifests/books/<book>-plan.toml`
8. `sources.lock`
9. 需要生成章节时再读取 `.agents/skills/source-first-technical-book/SKILL.md`

`AGENTS.md` 是仓库行为的最高优先级。Skill 只提供章节生产的详细执行流程，不能替代仓库状态、固定内容计划和长期决策记录。

## 2. 当前阶段

仓库目前处于 **基础设施与来源锁定阶段**，尚不具备直接生成正式技术文章的条件。

当前已经具备：

- RST 与 Sphinx 基础结构；
- 书籍、实验、来源和章节 manifest 的目录边界；
- 固定内容计划规则；
- Linux Kernel 第一卷 frozen plan；
- RST 审计脚本；
- GitHub Actions 验证入口；
- 未来公共 release 的白名单导出骨架。

当前仍然缺少：

- 已锁定的 Linux release 和 exact commit；
- 确定的 ARM64 kernel config；
- 确定的 compiler/toolchain；
- 可复现的运行与 trace 环境；
- 第一个真实 lab；
- 第一个章节 manifest；
- 真实命令输出和源码符号验证。

这些条件补齐前，不得生成完整章节正文。

## 3. 工作分支

- 只在 `main` 分支工作。
- 不创建功能分支和 PR，除非用户以后明确修改该规则。
- 每次提交只包含一个清晰目标。

## 4. 新 Agent 启动步骤

1. 读取本文件和 `project/STATE.rst`。
2. 检查 `project/DECISIONS.rst`，不得重新讨论已经确定的决策。
3. 读取 `project/CONTENT_SELECTION.rst`，理解固定计划与执行检查的区别。
4. 查看 `project/REPOSITORY_MAP.rst`，理解当前文件与预留功能。
5. 查看目标书籍 manifest、frozen plan 和 `sources.lock`。
6. 按 frozen plan 找到顺序最靠前且未完成的章节。
7. 确认当前任务属于来源锁定、实验、正文、审计或 release 中哪一类。
8. 完成工作后更新 `project/STATE.rst`。
9. 产生新的长期决策时更新 `project/DECISIONS.rst`。
10. 新增、删除或改变文件职责时更新 `project/REPOSITORY_MAP.rst`。

任何 Agent 都不得依赖聊天记忆补全仓库未记录的信息。

## 5. 内容计划

- 一本书开始前必须建立完整 plan，并将其状态固定为 `frozen`。
- frozen plan 固定 Part、章节 ID、问题、顺序、学习结果、前置依赖和证据类型。
- 每次生成内容时不重新选题、不评分、不随机挑选。
- Agent 只执行 frozen plan 中顺序最靠前且前置条件满足的章节。
- 当前章节被 blocked 时默认停止，不得自行跳到后续章节。
- 修改目录必须通过显式 plan revision，增加版本并记录原因。
- 普通章节生产 Agent 没有自行修改 frozen plan 的权限。

## 6. 正式章节准入条件

创建 `docs/books/<book>/chapter-*.rst` 前必须同时满足：

- 当前书籍存在 frozen plan；
- 当前章节是 frozen plan 中规定的下一章；
- 书籍 manifest 的 source contract 已完整填写；
- `sources.lock` 已固定 source version 与 exact commit；
- 对应 `labs/<book>/<chapter>/` 已存在；
- 实验具有精确执行命令；
- 真实输出已经保存或可重复采集；
- 最短源码路径中的符号已经在固定 commit 中确认；
- 对应章节 manifest 已建立；
- 失败或边界用例已经定义。

缺少任何一项时，只能完善来源或实验，不能用解释性文字代替证据。

## 7. 内容规则

- 一个章节只回答 frozen plan 中规定的一个可观察问题。
- 代码、脚本、测试和短输出放在 `labs/`。
- RST 通过 `literalinclude` 引用代码，不复制第二份代码。
- 旧 Roadmap 只在规划阶段作为主题库存，不控制章节生产。
- 不写“本章将”“读完本章”“本章总结”“深入理解”。
- 问题解决后立即结束，不设最低字数。
- 版本敏感结论必须绑定 source、version、commit、architecture、config、toolchain 和 runtime。
- 无法验证的内容保持 blocked 或 evidence-pending。

## 8. Skill 的定位

`.agents/skills/source-first-technical-book/SKILL.md` 仍然保留，作用是：

- 按 frozen plan 执行已经确定的章节；
- 提供从实验、源码路径、RST、审计到提交的详细步骤；
- 让支持 Skill 的 Agent 可以直接调用统一流程；
- 避免把大量章节生成细则全部塞进根 `AGENTS.md`。

仓库接续依靠 `AGENTS.md`、`project/` 和 manifests。即使某个 Agent 不支持 Skill，也必须能依靠这些文件继续工作。

## 9. 私有开发与公共发布

- 当前仓库是私有开发仓库。
- 当前不配置 GitHub Pages。
- 未来建立独立公共 release 仓库。
- `tools/export_release.py` 与 `release-manifest.toml` 只负责生成发布快照。
- Skill、内部状态、决策记录、草稿和失败实验不进入公共 release。

## 10. 每次工作结束必须留下的记录

至少更新以下一项：

- `project/STATE.rst`：完成了什么、当前 blocker、下一步；
- `project/DECISIONS.rst`：新增长期决策及原因；
- `project/REPOSITORY_MAP.rst`：文件职责或预留功能发生变化；
- 相关 book/chapter manifest：状态和证据发生变化；
- plan revision：只有用户明确改变范围或证据证明计划错误时创建。

这样后续对话只读取仓库即可恢复工作，不需要聊天记录。
