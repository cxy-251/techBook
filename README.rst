techBook
========

``techBook`` 当前只写 Linux Kernel 学习内容，面向会基础 C 语法、希望从零建立内核理解和源码阅读能力的程序员。

内容依据
--------

* ``aiBook`` 的 Linux Kernel Roadmap 和生成控制文件说明用户希望获得哪些知识；
* 官方文档、固定版本源码和可确认的系统行为提供技术事实；
* 旧 ``aiBook/docs/LinuxK`` 用于识别原内容为什么过长、前置不足或难以理解。

Roadmap 是知识范围，不采用“一项一章”。当前只写一个学习单元，读完并修订后再决定下一篇。

当前内容
--------

* `Linux Kernel 学习入口 <docs/tracks/linux-kernel/index.rst>`_
* `LK-001：程序输出一行文字时，为什么需要内核？ <docs/tracks/linux-kernel/01-why-program-needs-kernel.rst>`_

学习方式
--------

每篇内容从具体代码或系统现象开始：先预测，再观察证据，随后逐步解释；最后改变一个条件，检查能否把理解迁移到新场景。

项目文件以 reStructuredText 为主。代码、命令、输出和引用资料直接保存在对应 RST 中。

开始工作
--------

新的对话或助手先阅读：

#. ``AGENTS.md``；
#. `当前状态 <project/STATE.rst>`_；
#. `学习设计 <project/LEARNING_DESIGN.rst>`_；
#. `Linux Kernel 学习入口 <docs/tracks/linux-kernel/index.rst>`_；
#. 当前学习单元。
