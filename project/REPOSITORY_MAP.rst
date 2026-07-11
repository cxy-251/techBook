仓库文件职责
============

本文件说明主要路径当前承担什么职责。新增、删除或改变文件职责时必须同步更新。

根目录
------

``AGENTS.md``
   所有新对话和新 Agent 的第一入口。保存仓库使命、读取顺序、内容规则和维护要求。

``README.rst``
   面向仓库使用者的项目说明和导航入口。

``.gitignore``
   只忽略操作系统产生的无关文件。

项目规则
--------

``project/STATE.rst``
   保存当前阶段、已完成事项、现存问题和下一步。

``project/DECISIONS.rst``
   保存跨对话长期决定以及已经废止的旧设计。

``project/LEARNING_DESIGN.rst``
   定义预测、证据、推理、条件变化、误解修正、答案解释和迁移任务组成的学习主链。

``project/AIBOOK_LESSONS.rst``
   记录 ``aiBook`` 的失败模式，以及迁移旧内容时必须避免的问题。

``project/CONTENT_SELECTION.rst``
   规定 track、阶段小批次和学习单元的规划方式。

``project/REPOSITORY_MAP.rst``
   保存当前文件职责，防止换对话后忘记某个文件为什么存在。

学习状态
--------

``manifests/tracks.toml``
   登记来自 ``aiBook/docs`` 的七条学习方向和当前状态。

``manifests/tracks/<track>.toml``
   保存某条路径的目标读者、能力层级、阶段顺序、范围和进度。

``manifests/units/README.rst``
   说明 unit TOML 如何记录学习变化、证据、评估和阅读状态。

``manifests/units/<unit>.toml``
   每个黄金学习单元或正式学习单元的简短状态记录。只在真实 unit 开始时创建。

RST 内容
--------

``docs/index.rst``
   面向读者的总入口，使用普通 RST 相对链接导航。

``docs/architecture.rst``
   说明路径、学习单元、证据和评估之间的关系。

``docs/tracks/index.rst``
   学习路径列表。

``docs/tracks/<track>/``
   对应路径的说明与正式学习单元。代码、命令、输出、错误和源码证据直接写在这些 RST 中。

模板
----

``templates/learning-unit.rst``
   学习单元的参考结构。它只提示学习主链，不是必须逐标题填满的固定格式。

仓库明确不包含
--------------

当前工作树不保留以下内容：

* Python 脚本和 ``pyproject.toml``；
* Sphinx 配置和 HTML 构建；
* GitHub Actions、CI 或其他自动检查；
* 独立 Skill；
* release 导出脚本和发布配置；
* 全局 source lock；
* 独立 lab、assessment 或构建产物目录；
* 冻结整本书的章节计划。

代码与证据直接属于对应 RST；源码级单元需要的版本信息也记录在当前 RST 和 unit TOML 中。