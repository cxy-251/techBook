techBook
========

``techBook`` 是私有的技术书生产仓库。正文使用 reStructuredText，章节从可运行实验、真实输出和固定源码版本出发生成。

仓库定位
--------

* ``main`` 是唯一工作分支。
* 当前仓库只保存技术书、实验、来源锁定和生成 Skill。
* 当前阶段不启用 GitHub Pages。
* 内容稳定后，通过白名单导出到独立公共仓库，再由公共仓库发布 Pages。

写作原则
--------

* 一个章节只解决一个可观察问题。
* 没有实验、源码、命令、测试、规范或真实输出支撑时，不创建章节。
* 示例代码存放在 ``labs/``，正文使用 ``literalinclude`` 引用。
* Roadmap 是候选问题池，可以删除、合并和重新排序。
* 版本敏感结论必须绑定 source、version、commit、平台和工具链。
* 构建、实验或审计失败时，章节保持未发布状态。

本地命令
--------

项目使用 Python 3.12 与 uv：

.. code-block:: console

   uv sync --all-groups
   uv run python tools/audit_chapter.py docs
   uv run sphinx-build -W --keep-going -n -b html docs docs/_build/html
   uv run python tools/export_release.py

目录
----

``docs/``
   Sphinx 与 RST 正文。

``labs/``
   与章节一一对应的最小实验、测试和保存输出。

``manifests/``
   书籍契约与章节状态。

``sources.lock``
   外部源码和规范的确定版本。

``.agents/skills/``
   无人参与的技术书生产规则。

``tools/``
   内容审计与 release 快照导出工具。

``templates/``
   RST 章节模板，不参与 Sphinx 构建。
