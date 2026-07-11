学习单元 manifest
=================

每个正式学习单元使用一个 TOML manifest。manifest 记录学习目标、前置能力、证据、问题来源和
完成标准，不能只记录“文章是否写完”。

建议字段
--------

.. code-block:: toml

   id = "python-list-append-return"
   track = "python"
   stage = "foundations"
   title = "为什么 list.append() 返回 None？"
   status = "designed"

   [learner]
   prerequisites = ["能创建变量和列表", "知道函数调用的基本写法"]
   before = "容易认为所有方法都会返回修改后的对象"
   after = "能区分原地修改与返回新对象，并能避免覆盖原变量"

   [learning_loop]
   opening_problem = "items = items.append(3) 后为什么 items 变成 None？"
   prediction_required = true
   variation_required = true
   misconception_required = true
   transfer_task_required = true

   [evidence]
   kind = ["runnable-example", "real-output", "official-doc"]
   lab = "labs/python/python-list-append-return"

   [assessment]
   questions_have_origin = false
   answers_have_reasoning = false
   wrong_answers_explained = false
   transfer_task_passed = false

   [validation]
   content_audit_passed = false
   rst_passed = false
   learner_check_passed = false

状态
----

``inventory``
   只从旧内容中识别了主题，还没有形成学习目标。

``designed``
   学习变化、前置能力、预测、证据和迁移任务已经设计。

``evidence-pending``
   结构已经确定，真实示例、输出或来源尚未齐全。

``writing``
   正在把已验证的学习设计写成 RST。

``review``
   等待实际阅读检查，重点检查问题动机、推理链和迁移任务。

``complete``
   证据、内容、答案推理和学习完成标准全部通过。

完成条件
--------

一个 unit 进入 ``complete`` 前必须确认：

* 读者知道为什么现在要解决这个问题；
* 解释出现前存在真实预测；
* 每个核心结论都有可定位证据；
* 答案包含推理过程；
* 常见错误答案说明了错误模型；
* 至少有一次条件变化；
* 至少有一个不照抄原示例的迁移任务；
* 前置能力已在路径中建立或明确提供补充单元。
