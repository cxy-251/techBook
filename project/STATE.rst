项目状态
========

最后更新
--------

2026-07-11

当前阶段
--------

``learning-model-calibration``：仓库已经从技术书生产流水线改为可执行学习系统，正在校准
学习单元模型，尚未开始批量迁移 ``aiBook/docs``。

当前结论
--------

* 仓库只在 ``main`` 工作。
* 面向读者的内容使用 reStructuredText 与 Sphinx。
* ``AGENTS.md`` 是所有新 Agent 的第一入口。
* 仓库的核心产物是 learning track、unit、lab 和 assessment。
* 目标读者是希望从零基础逐步达到独立排错与迁移能力的程序员。
* 开头固定路径目标和阶段，不再提前冻结整本书的全部章节。
* 每个阶段设计一个小批次 unit，每次运行只执行批次中的下一项。
* Linux 原 17 章 frozen plan 已退出活动使用。
* 当前不依赖独立 Skill。
* 当前不发布 GitHub Pages，未来使用独立公共 release 仓库。

已经完成
--------

* 建立 RST、Sphinx、实验、审计、CI 和 release 基础设施。
* 建立跨对话 ``AGENTS.md``、状态、决策和文件职责记录。
* 总结 ``aiBook`` 的九类主要教学失败，并形成迁移规则。
* 建立统一学习设计：预测、证据、推理、变化、误解、答案和迁移任务。
* 定义 ``L1 运行`` 到 ``L5 迁移`` 的能力层级。
* 登记 ``aiBook/docs`` 的七条学习路径。
* 建立 Linux Kernel 路径的四个阶段草案。
* 建立 unit manifest 规范与学习单元 RST 模板。
* 建立 learning model 自动校验工具。
* 将“整本书全部章节提前冻结”决策标记为 superseded。
* 将 Linux 原 17 章计划标记为历史设计，不再控制后续内容。

当前 blocker
------------

* 七条路径尚未完成旧内容库存审计。
* 还没有经过实际阅读验证的黄金 unit。
* unit 的篇幅、解释密度和评估难度尚未由真实样例校准。
* Linux 路径的 ``foundations`` 阶段还没有设计第一批 unit。
* CI 尚未记录新 learning model 的首次完整验证结果。

下一阶段
--------

#. 从 ``aiBook/docs`` 选择三个典型失败案例：语言基础、系统行为和源码级内容各一个。
#. 为三个案例建立 unit manifest，先定义读者前后能力变化。
#. 编写或提取最小示例、真实输出和条件变化。
#. 生成三个黄金 RST unit，重点验证问题动机和答案推理。
#. 实际阅读后记录哪些地方仍然让人困惑，并修订学习设计。
#. 黄金 unit 通过后，为七条路径建立第一批 stage batch。

状态维护规则
------------

每次完成有意义的仓库工作后，更新“已经完成”“当前 blocker”和“下一阶段”。长期方向写入
``project/DECISIONS.rst``；文件职责写入 ``project/REPOSITORY_MAP.rst``。
