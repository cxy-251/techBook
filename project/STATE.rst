项目状态
========

最后更新
--------

2026-07-11

当前阶段
--------

``foundation``：仓库基础结构已经建立，正式章节生产尚未开始。

当前结论
--------

* 仓库只在 ``main`` 工作。
* 正文使用 reStructuredText 与 Sphinx。
* 当前私有仓库不发布 GitHub Pages。
* 未来通过独立公共仓库发布稳定 release。
* ``AGENTS.md`` 是所有新 Agent 的第一入口。
* 当前仓库内容不足以直接写正式技术文章。
* Linux Kernel 是首本候选书，首个候选问题是“用户态 ``read()`` 如何进入 VFS”。

已经完成
--------

* 创建 Sphinx 基础配置和文档入口。
* 创建 ``docs/books/``、``labs/``、``manifests/``、``templates/`` 和 ``tools/``。
* 创建仓库级 ``AGENTS.md``。
* 创建章节生成 Skill，并将其定位为 ``AGENTS.md`` 下的详细执行协议。
* 创建 RST 审计脚本。
* 创建 GitHub Actions 验证工作流。
* 创建未来公共 release 的白名单导出骨架。
* 创建 Linux Kernel 书籍 manifest 和阅读契约。

当前 blocker
------------

Linux Kernel 的 source contract 尚未完成：

* release 或 tag 未确定；
* exact commit 未确定；
* ARM64 kernel config 未确定；
* compiler/toolchain 未确定；
* runtime 与 trace 环境未确定；
* 第一个 lab 尚未建立；
* 第一个 chapter manifest 尚未建立；
* GitHub Actions 首次完整验证结果尚未记录。

下一阶段
--------

#. 确定 Linux Kernel 的 release、exact commit、ARM64 config、toolchain 和验证环境。
#. 更新 ``sources.lock`` 与 ``manifests/books/linux-kernel.toml``。
#. 建立 ``labs/linux-kernel/read-enters-vfs/``。
#. 编写最小用户态 ``read()`` 程序、执行脚本和验证测试。
#. 采集真实输出，并确认固定 commit 中的最短源码路径。
#. 创建对应 chapter manifest。
#. 所有证据齐全后再写第一篇 RST 正文。

状态维护规则
------------

每次完成有意义的仓库工作后，更新本文件中的“已经完成”“当前 blocker”和“下一阶段”。本文件只描述当前状态，不保存已经失效的详细历史；长期决策记录在 ``project/DECISIONS.rst``。
