仓库文件职责
============

本文件说明主要路径当前承担什么职责。新增、删除或改变文件职责时必须同步更新。

根目录
------

``AGENTS.md``
   所有新对话和新 Agent 的第一入口。只保存稳定接入顺序、固定实现与最短执行规则。

``README.rst``
   面向仓库使用者的项目说明和导航入口。

``.gitignore``
   忽略操作系统文件和项目内固定源码缓存 ``.sources/``。

项目规则
--------

``project/STATE.rst``
   Linux Kernel唯一动态接续状态，保存当前模式、已验证游标、下一批、阻塞与精确读取清单。

``project/LINUX_KERNEL_CONTRACT.rst``
   Linux Kernel回溯审查和后续生产的唯一质量合同，固定证据、叙事、批次、状态与提交门。

``project/LINUX_KERNEL_FORWARD_CHECKPOINT.rst``
   冻结回溯审查开始前第193章的历史前向终点；只供审查完成后对照，不是当前执行依据。

``project/audits/linux-kernel/index.rst``
   轻量批次审计账本。

``project/audits/linux-kernel/<range>.rst``
   单批固定源码证据、问题、修复、连续性与验证结果。

``project/DECISIONS.rst``
   保存跨对话长期决定以及已经废止的旧设计。

``project/LEARNING_DESIGN.rst``
   定义 Roadmap 知识项如何转化为能力台阶，以及预测、证据、推理、条件变化、误解修正和迁移任务组成的学习主链。

``project/AIBOOK_LESSONS.rst``
   区分 ``aiBook`` 生成控制文件和旧正文的价值，记录旧生成流程的失败模式。

``project/CONTENT_SELECTION.rst``
   规定 Roadmap/控制文件盘点、知识库存、阶段小批次和学习单元的规划方式。

``project/REPOSITORY_MAP.rst``
   保存当前文件职责，防止换对话后忘记某个文件为什么存在。

学习状态
--------

``manifests/tracks.toml``
   登记七条学习方向、对应旧 ``docs`` 路径、Roadmap/生成控制文件盘点状态，以及三类来源的职责。

``manifests/tracks/<track>.toml``
   保存某条路径的控制文件路径、Roadmap 知识库存、目标读者、能力层级、暂定阶段、覆盖范围和进度。

``manifests/units/README.rst``
   说明 unit TOML 如何分别记录 Roadmap 覆盖、事实来源、证据、学习变化和阅读状态。

``manifests/units/<unit>.toml``
   每个黄金学习单元或正式学习单元的简短状态记录。只在真实 unit 开始时创建。

RST 内容
--------

``docs/index.rst``
   面向读者的总入口，使用普通 RST 相对链接导航。

``docs/architecture.rst``
   说明路径、学习单元、Roadmap 覆盖、事实证据、评估和状态之间的关系。

``docs/tracks/index.rst``
   学习路径列表。

``docs/tracks/<track>/``
   对应路径的知识库存说明、路径入口与正式学习单元。代码、命令、输出、错误和源码证据直接写在这些 RST 中。

模板
----

``templates/learning-unit.rst``
   学习单元的参考结构。提示记录 Roadmap 覆盖、事实来源和学习主链，不是必须逐标题填满的固定格式。

工具
----

``tools/check-linux-kernel-track.sh``
   只读检查001到指定审查游标的文件唯一性、章末结构、固定commit和退役版本标签；
   同时报告全局重复编号。它不判断技术事实。

本地固定源码缓存
----------------

``.sources/<repository>/``
   按需缓存QEMU、SeaBIOS、GRUB与Linux固定提交。目录不进入Git；使用前核对remote、HEAD
   和工作树，稀疏检出缺少文件时按当前批次补齐。

仓库明确不包含
--------------

当前工作树不保留以下内容：

* Python 脚本和 ``pyproject.toml``；
* Sphinx 配置和 HTML 构建；
* GitHub Actions、CI 或自动技术事实判定；
* 独立 Skill；
* release 导出脚本和发布配置；
* 提交到Git的全局 source lock或外部源码副本；
* 独立 lab、assessment 或构建产物目录；
* 冻结整本书的章节计划。

Roadmap 和生成控制文件只负责定义知识需求。代码与证据直接属于对应 RST；技术事实由一手资料和真实行为支撑；旧 ``aiBook/docs`` 只作为失败样本。
