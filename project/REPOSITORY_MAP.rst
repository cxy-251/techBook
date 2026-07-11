仓库文件职责
============

本文件说明主要路径当前承担什么职责，以及哪些内容属于未来预留。新增、删除或改变文件职责时必须同步更新。

状态说明
--------

``active``
   当前已经参与仓库运行或约束。

``incomplete``
   当前已使用，但关键内容仍未补齐。

``reserved``
   为已经确定的未来流程预留，当前不会主动执行。

根目录
------

``AGENTS.md`` — active
   所有新对话和新 Agent 的第一入口。保存仓库目的、读取顺序、当前阶段、unit 准入条件和维护规则。

``README.rst`` — active
   面向仓库使用者的简要说明。它不替代 ``AGENTS.md``。

``pyproject.toml`` — active
   固定 Python 3.12、Sphinx、doc8、pytest、ruff 和 uv 的基础依赖。

``sources.lock`` — reserved
   只在源码级 unit 需要固定实现、版本和 commit 时使用。普通入门 unit 不要求先锁源码。

``release-manifest.toml`` — reserved
   定义未来公共 release 快照允许导出的白名单。

``.gitignore`` — active
   排除虚拟环境、缓存、Sphinx 构建输出和 release 临时目录。

项目规则
--------

``project/STATE.rst`` — active
   保存当前阶段、完成事项、blocker 和下一步。

``project/DECISIONS.rst`` — active
   保存跨对话长期决策及已废止决策。

``project/LEARNING_DESIGN.rst`` — active
   定义预测、证据、推理、条件变化、误解修正、答案解释和迁移任务组成的学习主链。

``project/AIBOOK_LESSONS.rst`` — active
   记录 ``aiBook`` 的失败模式和迁移时必须避免的问题。

``project/CONTENT_SELECTION.rst`` — active
   规定 track、stage batch 和 unit 的规划方式。不在开头冻结整本书全部章节。

``project/REPOSITORY_MAP.rst`` — active
   保存当前文件职责和预留功能。

学习模型
--------

``manifests/tracks.toml`` — active
   登记七条来自 ``aiBook/docs`` 的学习路径。

``manifests/tracks/<track>.toml`` — incomplete
   保存每条路径的目标读者、能力层级、阶段、范围和状态。当前只有 Linux Kernel 建立了初步阶段。

``manifests/units/README.rst`` — active
   定义 unit manifest 的字段、学习状态和完成标准。

``manifests/units/<unit>.toml`` — reserved
   每个黄金 unit 或正式 unit 的目标、证据、评估和完成状态。

实验与评估
----------

``labs/README.rst`` — active
   定义 unit 实验目录。只有需要运行、编译、trace 或其他可复现证据时才创建 lab。

``labs/<track>/<unit>/`` — reserved
   unit 的最小示例、脚本、测试和短输出。

``assessments/`` — reserved
   未来保存跨 unit 的阶段性能力检查。当前 unit 内评估先保存在 unit 本身和 manifest 中。

RST 内容
--------

``docs/conf.py`` — active
   Sphinx 基础配置，保持离线安全。

``docs/index.rst`` — active
   Sphinx 根入口。

``docs/architecture.rst`` — active
   说明学习路径、unit、证据、评估和发布之间的关系。

``docs/tracks/index.rst`` — active
   面向读者的学习路径目录入口。

``docs/tracks/linux-kernel/index.rst`` — incomplete
   Linux 路径目标、固定阶段和当前设计状态。尚无正式 unit。

模板
----

``templates/learning-unit.rst`` — active
   unit 的默认教学主链。允许按内容删减标题，不能删除预测、证据、推理和迁移。

工具
----

``tools/audit_learning_content.py`` — active
   检查 unit 是否包含预测、证据、推理、条件变化、误解、答案和迁移，并阻止重复段落与宏大套话。

``tools/validate_learning_model.py`` — active
   检查 track、stage 和 unit manifest 的必要字段、唯一 ID 与连续阶段顺序。

``tools/export_release.py`` — reserved
   未来根据白名单生成公共快照。

GitHub Actions
--------------

``.github/workflows/verify.yml`` — active
   只允许在 Actions 页面通过 ``workflow_dispatch`` 手动运行。不会在普通 push 时自动执行或发送失败邮件。
   手动运行时才执行 Python 工具检查、learning model 校验、RST 审计、可用 lab 测试和 Sphinx HTML 预览构建。

RST 与构建关系
-------------

RST 是源文本，可以直接存储、审阅和修改。Sphinx 构建不是日常写作前提，只在以下情况需要：

* 想查看最终 HTML 阅读效果；
* 检查 toctree、交叉引用和 directive；
* 准备公共 release；
* 主动排查 RST 结构错误。

已经删除的旧模型
----------------

以下内容已经从工作树删除，历史仍保存在 Git 中：

* 冻结的 Linux 17 章计划与 book manifest；
* chapter manifest 规范；
* 源码章节模板；
* frozen plan 校验工具；
* ``docs/books`` 旧入口；
* ``source-first-technical-book`` Skill。

删除原因是它们会把仓库重新带回“先冻结目录，再批量填文章”的错误模型。
