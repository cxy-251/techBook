# AGENTS.md

本仓库同时维护两条互不替代的内容线：

1. ``docs/tracks/linux-kernel/``：原有 Linux Kernel 固定源码时间线、回溯审查与后续生产；
2. ``docs/memory/``：与 AIBook 章节一一对应、可以直接记忆的必背课本。

任何新对话都必须先根据目标路径选择对应合同，不得把一条内容线的规则强加给另一条内容线，
也不得依赖聊天记录或上一位 Agent 的口头总结。

全局规则
========

* 用户当前明确指令优先级最高；
* 默认直接在 ``main`` 工作，除非用户明确要求其他分支；
* 只修改当前任务涉及的内容线和必要导航；
* 不以新任务为理由重写、删除或迁移另一条内容线；
* 修改前读取对应合同，修改后检查相对链接、RST 标题和来源记录。

Linux Kernel 源码时间线
=======================

适用路径
--------

以下路径服从原有 Linux Kernel 合同：

::

   docs/tracks/linux-kernel/
   project/STATE.rst
   project/audits/linux-kernel/
   project/LINUX_KERNEL_FORWARD_CHECKPOINT.rst

接入顺序
--------

开始工作前依次完整读取：

#. ``AGENTS.md``；
#. ``project/LINUX_KERNEL_CONTRACT.rst``；
#. ``project/STATE.rst``；
#. ``project/audits/linux-kernel/index.rst``；
#. ``project/STATE.rst`` 指定的当前批次报告、正文和 manifest 片段；
#. 当前批次涉及的固定提交源码。

不要把 README、完整章节目录、全部历史正文或全部旧审计报告一次性装入上下文。它们是导航与
历史，不是当前接续状态。只有当前批次确实需要时才读取。

唯一执行合同
------------

Linux Kernel 的审查、修订与后续生产统一遵守
``project/LINUX_KERNEL_CONTRACT.rst``。当前模式、已验证范围、下一批次和是否允许生产新章，只从
``project/STATE.rst`` 读取。

在回溯审查模式中：

* 从第001章开始按编号顺序审查；
* 每批通常三章；
* 审查与修复在同一批完成；
* 不得跳过未验证章节；
* 不得继续第193章之后的新主线；
* “正文已经存在”不等于“技术内容已经验证”。

固定实现
--------

::

   SeaBIOS commit    = c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf
   SeaBIOS target    = QEMU
   SeaBIOS config    = unmodified defaults for the QEMU target
   QEMU commit       = a759542a2c62f0fd3b65f5a66ad9868201014669
   GNU GRUB release  = 2.14
   GRUB commit       = d38d6a1a9b79427848976f53d474392cd29c2a71
   GRUB target       = i386-pc
   Linux release     = 7.2-rc1
   Linux repository  = gregkh/linux
   Linux commit      = 7404ce51637231382873d0b55edabc2f3b841a9d
   partition table   = MBR
   first partition   = LBA 2048, ext4
   storage           = q35 ICH9 AHCI SATA port 0

权威源码工作树
--------------

正文取证只允许使用以下四个工作树：

::

   /Volumes/LinuxKernel/seabios
   /Volumes/LinuxKernel/qemu
   /Volumes/LinuxKernel/grub
   /Volumes/LinuxKernel/linux-7.2-rc1

不得使用项目内 ``.sources/``、``/Volumes/LinuxKernel/linux`` 或其他副本作为正文证据，也不得自动
克隆、下载、拉取或补齐源码。开始每批工作前必须逐个确认：

* remote 与对应固定仓库一致；Linux 工作树必须存在指向 ``gregkh/linux`` 的 remote；
* ``HEAD`` 与“固定实现”列出的 commit 完全一致；
* ``git status --short`` 没有输出；
* ``git rev-parse --is-shallow-repository`` 返回 ``false``；
* sparse checkout 未启用，也没有活动的 sparse 规则。

任何一项不满足时停止正文生产并报告，不得改用其他源码树绕过。

每批事务
--------

#. 确认分支是 ``main``，工作树没有与当前任务无关的改动；
#. 只读取当前三章、上一章结束边界、下一章入口和必要固定源码；
#. 先建立源码证据和状态连续性，再修改正文；
#. 逐章完成事实、叙事、边界和资料检查；不确定的结论必须查清或阻塞，不能补写；
#. 运行 ``tools/check-linux-kernel-track.sh <审查到的最高章号>``；
#. 写当前批次审计报告，并更新审计索引、``project/STATE.rst`` 和必要 manifest 字段；
#. 复核完整 diff，确保没有越过本批范围或改动用户无关内容；
#. 将本批正文、审计记录和接续状态作为一个原子提交直接提交到 ``main``，随后推送
   ``origin/main``。检查失败或存在未解决技术问题时不得提交为完成。

正文固定格式
------------

正文按源码时间线连续展开。每段交代与当前判断相关的执行者、CPU/mode、关键对象、锁或引用、
状态变化和下一入口。篇幅服从源码边界，不设字数目标，也不以压缩篇幅为进度指标。

每章必须根据本章当前源码边界独立组织叙事。函数名、类型名、字段名、宏、配置项和其他源码
标识保留英文并使用行内代码；普通叙述、条件、状态、动作和因果关系使用完整中文句子。

章末依次使用：

#. ``本章结束状态``；
#. ``关键边界``；
#. ``下一入口``；
#. ``资料``。

资料必须链接到固定提交；关键结论优先使用精确行锚点。详细规则以
``project/LINUX_KERNEL_CONTRACT.rst`` 为准。

必背课本
========

适用路径
--------

以下路径服从必背课本合同：

::

   docs/memory/
   project/MEMORY_CONTENT_CONTRACT.rst

接入顺序
--------

开始工作前依次读取：

#. ``AGENTS.md``；
#. ``project/MEMORY_CONTENT_CONTRACT.rst``；
#. ``docs/memory/index.rst``；
#. 当前书籍的 ``index.rst``；
#. AIBook 中与当前任务对应的原章节；
#. 原章节引用的一手资料中，当前结论确实需要复核的部分。

制作必背课本时不读取 ``project/STATE.rst``、Linux Kernel 审计报告或旧轨道全部正文，除非当前任务
明确要求比较两条内容线。

内容边界
--------

* AIBook 决定书籍、Part、章节号、主题和来源路径；
* 每篇必背正文必须与一个 AIBook 章节明确对应；
* 只写稳定、确定、可直接记忆的知识点；
* 不写问题、练习、作业、互动提示和长篇推导；
* 不把模型自身记忆作为来源；
* 不修改 AIBook 原文；
* 不修改 ``docs/tracks/`` 旧正文；
* 不更新 Linux Kernel 旧轨道的审计状态和游标；
* 每章固定使用“本章必须记住”“必背路径”“必须区分”“一句话结论”“来源”；
* 版本相关或容易失真的技术事实必须复核后再写成可直接背诵的结论。

完整规则只从 ``project/MEMORY_CONTENT_CONTRACT.rst`` 读取。

跨对话边界
============

稳定规则只写入 ``AGENTS.md`` 和两份内容合同。Linux Kernel 动态审计状态继续只写入
``project/STATE.rst``；必背课本的完成范围由各书籍 ``index.rst`` 中已存在的章节链接表示。
下一对话必须重新按目标内容线的接入顺序恢复工作，避免把旧任务状态带入新任务。
