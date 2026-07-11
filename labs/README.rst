实验资产
========

每个需要可运行证据的 unit 在 ``labs/<track>/<unit>/`` 下保存独立实验。

建议结构：

.. code-block:: text

   labs/<track>/<unit>/
   ├── README.rst
   ├── src/
   ├── tests/
   ├── scripts/
   └── output/

``README.rst`` 记录学习目标、读者需要预测的结果、环境、精确命令、条件变体和成功判据。

``src/``
   最小示例与变体代码。

``tests/``
   检查示例行为和迁移任务所需的自动测试。

``scripts/``
   构建、执行、采集日志或 trace 的可重复命令。

``output/``
   只保存 unit 实际引用的短输出。大型 trace、缓存和构建产物不提交。

实验目录必须能在不阅读 RST 正文的情况下独立运行。面向读者的 unit 通过相对路径
``literalinclude`` 引用这里的代码。

一个 lab 不只是证明结论，还应当支持：

* 解释前的预测；
* 一个最小正常案例；
* 至少一个条件变化；
* 一个典型错误或边界；
* 一个独立迁移任务。
