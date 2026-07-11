techBook
========

``techBook`` 是面向零基础程序员的可执行技术学习系统。它把 ``aiBook/docs`` 中的技术方向重做为可以预测、观察、解释、修改、排错和迁移的学习路径。

Agent 接续
----------

任何新对话和新 Agent 都必须先读取：

#. ``AGENTS.md``
#. ``project/STATE.rst``
#. ``project/DECISIONS.rst``
#. ``project/LEARNING_DESIGN.rst``
#. ``project/AIBOOK_LESSONS.rst``
#. ``project/CONTENT_SELECTION.rst``
#. ``project/REPOSITORY_MAP.rst``

仓库不依赖聊天记录保存上下文。

当前状态
--------

仓库处于学习模型校准阶段。当前重点是建立语言基础、系统行为和源码阅读三类黄金 unit，尚未开始批量迁移旧内容。

RST 与构建
----------

RST 文件是可直接阅读和修改的源文本，日常写作不要求构建。

Sphinx 只在以下情况手动运行：

* 查看 HTML 阅读效果；
* 检查 toctree、交叉引用和 directive；
* 准备公共 release；
* 排查 RST 结构问题。

GitHub Actions 不会在普通 push 时自动运行。需要完整检查时，在 Actions 页面手动启动 ``verify-manually``。

学习原则
--------

* 一个 unit 只产生一次明确的能力变化。
* 解释之前先让读者预测。
* 结论必须绑定代码、对象、状态、输出或其他可定位证据。
* 至少改变一个条件，检查读者是否真正理解边界。
* 每个问题说明为什么要问，答案说明为什么成立。
* 每个 unit 都需要一个不能直接照抄示例的迁移任务。
* 不写宏大开场、重复总结和百科式铺陈。
* 基础内容先建立行为模型，源码阅读在需要时进入。

学习路径
--------

当前登记的路径来自旧仓库 ``docs``：

* C++ STL；
* Python；
* Graphics；
* Linux Kernel；
* Compiler；
* Mobile OS；
* Web Architecture。

本地可选验证
------------

项目使用 Python 3.12 与 uv。以下命令按需执行，不是每次修改 RST 的必经步骤：

.. code-block:: console

   uv sync --all-groups
   uv run ruff check tools
   uv run python tools/validate_learning_model.py
   uv run python tools/audit_learning_content.py docs
   uv run sphinx-build -W --keep-going -n -b html docs docs/_build/html

仓库边界
--------

* ``main`` 是唯一工作分支。
* 当前私有仓库不启用 GitHub Pages。
* 稳定内容后续导出到独立公共仓库发布。
* 文学、电影、电视剧和游戏编年史不进入本仓库。

主要目录
--------

``project/``
   学习设计、旧仓库经验、当前状态、长期决策和文件职责。

``manifests/tracks/``
   学习路径目标、能力层级、阶段与范围。

``manifests/units/``
   unit 的学习变化、证据、问题来源、评估和完成状态。

``docs/tracks/``
   面向读者的 RST 学习路径与 unit。

``labs/``
   最小示例、变体、测试和真实输出。

``templates/``
   学习单元模板。

``tools/``
   学习模型、内容和 release 验证工具。
