学习单元状态
============

每个正式学习单元可以使用一个简短 TOML 文件记录 Roadmap 覆盖、学习目标、前置能力、事实来源、阅读反馈和当前状态。

TOML 只负责跨对话接续，学习内容本身全部保存在对应 RST 中。

建议字段
--------

.. code-block:: toml

   id = "python-list-append-return"
   track = "python"
   stage = "foundations"
   title = "为什么 list.append() 返回 None？"
   rst = "docs/tracks/python/python-list-append-return.rst"
   status = "designed"

   [scope]
   control_files = ["<aiBook 中的 Roadmap 或生成控制文件路径>"]
   roadmap_items = ["<当前单元覆盖的知识项>"]
   merged_items = []

   [learner]
   prerequisites = ["能创建变量和列表", "知道函数调用的基本写法"]
   before = "容易认为所有方法都会返回修改后的对象"
   after = "能区分原地修改与返回新对象，并避免覆盖原变量"

   [learning_loop]
   opening_problem = "items = items.append(3) 后为什么 items 变成 None？"
   prediction = true
   variation = true
   misconception = true
   transfer_task = true

   [facts]
   primary_sources = ["Python 官方文档的具体链接或位置"]
   implementation_sources = []
   verified_behavior = "实际执行行为记录在 RST"
   legacy_docs_used_as_fact = false

   [evidence]
   kinds = ["runnable-example", "real-output", "official-doc"]
   recorded_in_rst = true
   verification_environment = "Python <version>, <platform>"
   verification_date = "YYYY-MM-DD"

   [review]
   reader_understood_motivation = false
   reader_explained_reasoning = false
   reader_completed_variation = false
   reader_completed_transfer = false
   notes = ""

来源规则
--------

``scope.control_files`` 和 ``scope.roadmap_items`` 说明这个单元为什么存在、需要覆盖什么知识。

``facts.primary_sources``、``facts.implementation_sources`` 和 ``evidence`` 说明技术结论为什么可信。

两类来源不能混用：

* Roadmap 和生成控制文件定义知识需求，不证明技术事实；
* 旧 ``aiBook/docs`` 只能用于分析旧生成失败，不能填入事实来源；
* 官方资料、固定源码和真实行为负责支撑结论。

一个 unit 可以覆盖多个相关 Roadmap 项，也可以只覆盖一个大知识项的某个能力台阶。合并、拆分和延后必须在路径知识库存或 unit 状态中可追踪。

状态
----

``inventory``
   已从 Roadmap 或生成控制文件中识别知识项，还没有形成学习目标。

``designed``
   Roadmap 覆盖、学习变化、前置能力、事实来源、预测、证据和迁移任务已经设计。

``writing``
   正在编写 RST 内容并重新核实事实。

``review``
   等待实际阅读检查，重点检查问题动机、推理链和迁移任务。

``complete``
   真实阅读反馈确认读者能够解释、变化和迁移，并且 Roadmap 覆盖与事实来源已经记录。

完成条件
--------

一个 unit 进入 ``complete`` 前必须确认：

* 能追溯到具体 Roadmap 或生成控制文件中的知识需求；
* Roadmap 项的合并、拆分或延后记录清楚；
* 读者知道为什么现在要解决这个问题；
* 解释出现前存在真实预测；
* 每个核心结论都有一手资料或真实行为支撑；
* 旧 ``docs`` 没有被当作事实来源；
* 实际输出记录了验证环境和日期；
* 未实测内容明确标记为预期结果；
* 答案包含推理过程；
* 常见错误答案说明了错误模型；
* 至少有一次条件变化；
* 至少有一个不能照抄原例子的迁移任务；
* 前置能力已在路径中建立或明确补充；
* 读者实际完成了关键任务，而不是只读完文件。

不使用脚本自动把 unit 标记为完成。状态由 RST 内容和真实阅读记录共同决定。
