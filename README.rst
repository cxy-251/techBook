techBook
========

``techBook`` 是一个面向零基础程序员的可执行技术学习仓库。它把 ``aiBook/docs`` 中的技术方向
重新设计为 learning track、unit、lab 和 assessment，目标是让读者从“看懂句子”走到能够预测、
解释、修改、排错和迁移。

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

仓库处于学习模型校准阶段。当前不批量生成文章，也不把旧 ``aiBook`` 章节直接改写进来。

下一步是制作三个黄金学习单元：语言基础、系统行为和源码阅读各一个。样例通过实际阅读检查后，
再为七条技术路径设计第一批 unit。

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

本地验证
--------

项目使用 Python 3.12 与 uv：

.. code-block:: console

   uv sync --all-groups
   uv run ruff check tools
   uv run python tools/validate_learning_model.py
   uv run python tools/audit_chapter.py docs
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
