techBook
========

``techBook`` 是面向零基础程序员的技术学习仓库。它把 ``aiBook/docs`` 中的技术方向重新设计为
可以直接阅读的 reStructuredText（RST）学习资料。

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
* 少量 TOML 只记录学习路径、单元和进度；
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

仓库处于学习模型校准阶段。当前不批量迁移旧内容，先制作三个黄金学习单元：语言基础、系统行为和
源码阅读各一个。样例经过实际阅读检查后，再为各条学习路径设计第一批内容。

学习路径
--------

当前登记的方向来自 ``aiBook/docs``：

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

``project/`` 保存跨对话规则与状态，``docs/`` 保存面向读者的 RST，``manifests/`` 使用少量 TOML
记录路径和学习单元进度。