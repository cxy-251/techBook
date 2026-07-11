仓库文件职责
============

本文件说明主要路径当前承担什么职责。新增、删除或改变职责时必须同步更新。

状态说明
--------

``active``
   当前参与仓库运行或约束。

``incomplete``
   已开始使用，关键内容仍未补齐。

``reserved``
   已确定未来会使用，当前不会主动执行。

根目录
------

``AGENTS.md`` — active
   所有新对话和 Agent 的第一入口，保存仓库目的、学习规则、读取顺序和维护要求。

``README.rst`` — active
   面向仓库使用者的简要说明。完整规则仍以 ``AGENTS.md`` 和 ``project/`` 为准。

``pyproject.toml`` — active
   固定 Python、Sphinx、doc8、pytest、ruff 和 uv 的基础依赖。

``sources.lock`` — incomplete
   固定需要源码级证明的外部实现与规范。基础 unit 不要求全部使用源码锁。

``release-manifest.toml`` — reserved
   未来公共 release 快照白名单。当前私有仓库不发布 Pages。

项目规则
--------

``project/STATE.rst`` — active
   当前阶段、已完成事项、blocker 和下一步。

``project/DECISIONS.rst`` — active
   跨对话长期决策，也记录已被取代的旧决策。

``project/LEARNING_DESIGN.rst`` — active
   定义零基础读者模型、能力层级、学习循环、问题设计和完成标准。

``project/AIBOOK_LESSONS.rst`` — active
   记录旧 ``aiBook`` 的失败模式和迁移时必须采用的修正规则。

``project/CONTENT_SELECTION.rst`` — active
   定义 track contract、stage batch 和每次执行之间的关系。

``project/REPOSITORY_MAP.rst`` — active
   当前文件职责和预留功能。

学习路径 manifest
-----------------

``manifests/tracks.toml`` — active
   登记从 ``aiBook/docs`` 继承的七条技术学习路径及其审计状态。

``manifests/tracks/<track>.toml`` — incomplete
   保存目标读者、入口层级、最终能力、阶段顺序、范围和排除项。

``manifests/tracks/linux-kernel.toml`` — incomplete
   Linux 路径当前只固定四个学习阶段，第一批 unit 尚未设计。

学习单元 manifest
-----------------

``manifests/units/README.rst`` — active
   定义 unit manifest、状态和完成条件。

``manifests/units/<unit>.toml`` — reserved
   正式 unit 的学习变化、预测、证据、问题来源、评估和完成状态。

实验与评估
----------

``labs/README.rst`` — active
   定义最小示例、条件变体、测试和短输出的保存方式。

``labs/<track>/<unit>/`` — reserved
   unit 的代码、命令、测试和真实输出。

``assessments/`` — reserved
   黄金 unit 验证后，用于保存独立任务、评分标准和读者反馈记录。

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
   每次推送 ``main`` 时验证 Python 工具、learning model、RST、已有 lab 测试和 Sphinx 构建。
   不部署 Pages。

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
