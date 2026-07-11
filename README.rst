techBook
========

``techBook`` 是面向零基础程序员的技术学习仓库。它保留 ``aiBook`` 文章生成控制文件中真正想学习的知识，重新设计为可以直接阅读的 reStructuredText（RST）学习资料。

内容从哪里来
------------

``aiBook`` 中不同文件承担不同作用：

* Roadmap、Roadmap 配套规范和文章生成控制文件决定需要学习哪些知识；
* 官方文档、标准、固定版本源码和真实运行行为决定技术事实；
* 旧 ``aiBook/docs`` 只用于分析原内容为什么过长、难读和学不会。

Roadmap 是知识范围，不是章节目录。一个 Roadmap 条目可以被合并、拆分、调整顺序或延后，但不能在没有记录的情况下丢失用户真正想获得的知识。

旧正文默认不复制、不缩写、不逐章改写。旧正文中的代码、链接、输出、源码路径和技术结论必须重新核实。

项目目标
--------

读者完成一个学习单元后，应当能够：

* 预测一个具体例子或现象；
* 根据代码、对象、状态和输出解释原因；
* 改变条件后重新判断；
* 识别常见错误理解；
* 把理解迁移到未见过的问题。

仓库形式
--------

* 项目规则和正式内容以 RST 为主；
* ``AGENTS.md`` 保存跨对话执行规则；
* 少量 TOML 只记录 Roadmap 来源、知识覆盖、学习路径、单元和进度；
* 代码、命令和输出直接写在对应 RST 文件中；
* 仓库不使用 Python 工具、Sphinx、GitHub Actions、CI、构建系统、发布脚本或独立 Skill；
* RST 源文件就是最终阅读内容。

开始工作
--------

任何新对话或新助手必须先阅读：

#. ``AGENTS.md``；
#. `当前状态 <project/STATE.rst>`_；
#. `长期决策 <project/DECISIONS.rst>`_；
#. `学习设计 <project/LEARNING_DESIGN.rst>`_；
#. `从 aiBook 得到的经验 <project/AIBOOK_LESSONS.rst>`_；
#. `学习内容规划规则 <project/CONTENT_SELECTION.rst>`_；
#. `仓库文件职责 <project/REPOSITORY_MAP.rst>`_。

仓库不依赖聊天记录保存上下文。

当前状态
--------

仓库处于 Roadmap 和生成控制文件盘点阶段。当前先确认每条路径真正想获得的知识，以及旧生成流程把这些知识扩充成了什么；盘点完成后再制作语言基础、系统行为和源码阅读三类黄金学习单元。

学习路径
--------

当前登记的方向来自 ``aiBook`` 的知识规划：

* C++ STL；
* Python；
* Graphics；
* `Linux Kernel <docs/tracks/linux-kernel/index.rst>`_；
* Compiler；
* Mobile OS；
* Web Architecture。

完整路径入口见 `学习路径 <docs/tracks/index.rst>`_。

学习原则
--------

* 一个学习单元只产生一次明确的能力变化；
* 解释之前先让读者预测；
* 每个结论绑定可定位的代码、对象、状态、输出或源码；
* 至少改变一个条件，检查读者是否理解边界；
* 每个问题说明为什么要问，答案说明为什么成立；
* 每个学习单元包含一个不能直接照抄原例子的迁移任务；
* 不写宏大开场、重复总结和百科式铺陈；
* 基础内容先建立行为模型，确有需要时再进入源码。

文件组织
--------

::

   AGENTS.md
   README.rst
   project/
     STATE.rst
     DECISIONS.rst
     LEARNING_DESIGN.rst
     AIBOOK_LESSONS.rst
     CONTENT_SELECTION.rst
     REPOSITORY_MAP.rst
   docs/
     index.rst
     architecture.rst
     tracks/
   manifests/
     tracks.toml
     tracks/
     units/
   templates/
     learning-unit.rst

``project/`` 保存跨对话规则与状态，``docs/`` 保存面向读者的 RST，``manifests/`` 使用少量 TOML 记录控制文件来源、知识覆盖和学习进度。
