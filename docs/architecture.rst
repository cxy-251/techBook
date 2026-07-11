生产架构
========

``techBook`` 将技术书拆成问题、实验、证据、源码路径和正文五类资产。

问题
----

问题必须描述一个可观察动作。Roadmap 只保存候选问题，不规定固定章节数量。

实验
----

实验位于 ``labs/``。代码、命令、测试和输出在这里形成可复用证据。

来源
----

外部源码与规范写入 ``sources.lock``。版本敏感章节在 commit 未锁定时保持 blocked。

正文
----

正文位于 ``docs/books/``。代码通过 ``literalinclude`` 引用，RST 文件只保存解释和交叉引用。

验证
----

GitHub Actions 与本地命令执行 RST 审计、doc8、Sphinx warnings-as-errors 构建和已有实验测试。

发布
----

私有仓库不发布 Pages。稳定内容由 ``tools/export_release.py`` 按白名单生成公共快照。
