项目状态
========

最后更新
--------

2026-07-11

当前阶段
--------

``source-contract``：仓库基础结构和 Linux 第一卷内容计划已经固定，正式章节生产尚未开始。

当前结论
--------

* 仓库只在 ``main`` 工作。
* 正文使用 reStructuredText 与 Sphinx。
* 当前私有仓库不发布 GitHub Pages。
* 未来通过独立公共仓库发布稳定 release。
* ``AGENTS.md`` 是所有新 Agent 的第一入口。
* ``project/`` 保存跨对话状态、决策、内容计划规则和文件职责。
* Skill 只负责执行 frozen plan 中已经确定的章节。
* 每次生成内容不重新选题，只检查下一章是否具备执行条件。
* Linux Kernel 第一卷计划已经 frozen，共 17 个固定章节。
* 第一章是 ``LK-BOOT-001``：“ARM64 Linux 内核镜像从哪个入口开始执行？”
* 当前仓库仍不足以直接写正式技术文章。

已经完成
--------

* 创建 Sphinx 基础配置和文档入口。
* 创建 ``docs/books/``、``labs/``、``manifests/``、``templates/`` 和 ``tools/``。
* 创建仓库级 ``AGENTS.md``，规定新 Agent 的读取顺序和章节准入条件。
* 创建 ``project/STATE.rst``、``project/DECISIONS.rst`` 和 ``project/REPOSITORY_MAP.rst``。
* 创建 ``project/CONTENT_SELECTION.rst``，规定内容在书籍开始前一次性固定。
* 创建 Linux 第一卷 plan 索引和三个 Part 文件，冻结 17 章的范围、顺序、依赖和证据类型。
* 创建 ``tools/validate_book_plans.py``，检查计划总数、ID、连续顺序、首章和前置依赖。
* 将计划验证加入 GitHub Actions，防止计划文件缺章或截断后继续生产。
* 将 Linux 第一卷主线固定为 ARM64 启动、初始化、initcall、用户空间 init、``read()`` 与 VFS。
* 将章节生成 Skill 改为只执行 frozen plan，不再临时选题。
* 创建 RST 审计脚本。
* 创建 GitHub Actions 验证工作流。
* 创建未来公共 release 的白名单导出骨架。
* 创建 Linux Kernel 书籍 manifest 和阅读契约。
* 在 ``README.rst`` 中明确当前仍处于基础设施阶段。

当前 blocker
------------

Linux Kernel 的 source contract 尚未完成：

* release 或 tag 未确定；
* exact commit 未确定；
* ARM64 kernel config 未确定；
* compiler/toolchain 未确定；
* runtime 与 trace 环境未确定；
* ``LK-BOOT-001`` lab 尚未建立；
* ``LK-BOOT-001`` chapter manifest 尚未建立；
* GitHub Actions 首次完整验证结果尚未记录。

下一阶段
--------

#. 确定 Linux Kernel 的 release、exact commit、ARM64 config、toolchain 和验证环境。
#. 更新 ``sources.lock`` 与 ``manifests/books/linux-kernel.toml``。
#. 建立 ``labs/linux-kernel/lk-boot-001/``。
#. 准备 Image header、入口反汇编、固定源码符号和可重复的启动观察方法。
#. 创建 ``manifests/chapters/lk-boot-001.toml``。
#. 验证第一章要求的全部 evidence。
#. 所有证据齐全后再写 ``LK-BOOT-001`` 的 RST 正文。

状态维护规则
------------

每次完成有意义的仓库工作后，更新本文件中的“已经完成”“当前 blocker”和“下一阶段”。本文件只描述当前状态，不保存已经失效的详细历史；长期决策记录在 ``project/DECISIONS.rst``。
