仓库文件职责
============

本文件说明主要路径当前承担什么职责。新增、删除或改变文件职责时必须同步更新。

根目录
------

``AGENTS.md``
   所有新对话和新 Agent 的第一入口。保存仓库使命、内容来源优先级、Roadmap 使用方式、RST 规则和维护要求。

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
   定义 Roadmap 知识项如何转化为能力台阶，以及预测、证据、推理、条件变化、误解修正和迁移任务组成的学习主链。

``project/AIBOOK_LESSONS.rst``
   区分 ``aiBook`` 生成控制文件和旧正文的价值，记录旧生成流程的失败模式。

``project/CONTENT_SELECTION.rst``
   规定 Roadmap/控制文件盘点、知识库存、阶段小批次和学习单元的规划方式。

``project/REPOSITORY_MAP.rst``
   保存当前文件职责，防止换对话后忘记某个文件为什么存在。

学习状态
--------

``manifests/tracks.toml``
   登记七条学习方向、对应旧 ``docs`` 路径、Roadmap/生成控制文件盘点状态，以及三类来源的职责。

``manifests/tracks/<track>.toml``
   保存某条路径的控制文件路径、Roadmap 知识库存、目标读者、能力层级、暂定阶段、覆盖范围和进度。

``manifests/units/README.rst``
   说明 unit TOML 如何分别记录 Roadmap 覆盖、事实来源、证据、学习变化和阅读状态。

``manifests/units/<unit>.toml``
   每个黄金学习单元或正式学习单元的简短状态记录。只在真实 unit 开始时创建。

RST 内容
--------

``docs/index.rst``
   面向读者的总入口，使用普通 RST 相对链接导航。

``docs/architecture.rst``
   说明路径、学习单元、Roadmap 覆盖、事实证据、评估和状态之间的关系。

``docs/tracks/index.rst``
   学习路径列表。

``docs/tracks/<track>/``
   对应路径的知识库存说明、路径入口与正式学习单元。代码、命令、输出、错误和源码证据直接写在这些 RST 中。

模板
----

``templates/learning-unit.rst``
   学习单元的参考结构。提示记录 Roadmap 覆盖、事实来源和学习主链，不是必须逐标题填满的固定格式。

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

Roadmap 和生成控制文件只负责定义知识需求。代码与证据直接属于对应 RST；技术事实由一手资料和真实行为支撑；旧 ``aiBook/docs`` 只作为失败样本。
