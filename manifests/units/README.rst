学习单元状态
============

每个正式学习单元可以使用一个简短 TOML 文件记录学习目标、前置能力、证据类型、阅读反馈和当前状态。
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

   [evidence]
   kinds = ["runnable-example", "real-output", "official-doc"]
   recorded_in_rst = true

   [review]
   reader_understood_motivation = false
   reader_explained_reasoning = false
   reader_completed_variation = false
   reader_completed_transfer = false
   notes = ""

状态
----

``inventory``
   只从旧内容中识别了主题，还没有形成学习目标。

``designed``
   学习变化、前置能力、预测、证据和迁移任务已经设计。

``writing``
   正在编写 RST 内容。

``review``
   等待实际阅读检查，重点检查问题动机、推理链和迁移任务。

``complete``
   真实阅读反馈确认读者能够解释、变化和迁移。

完成条件
--------

一个 unit 进入 ``complete`` 前必须确认：

* 读者知道为什么现在要解决这个问题；
* 解释出现前存在真实预测；
* 每个核心结论都有可定位证据；
* 答案包含推理过程；
* 常见错误答案说明了错误模型；
* 至少有一次条件变化；
* 至少有一个不能照抄原例子的迁移任务；
* 前置能力已在路径中建立或明确补充；
* 读者实际完成了关键任务，而不是只读完文件。

不使用脚本自动把 unit 标记为完成。状态由 RST 内容和真实阅读记录共同决定。