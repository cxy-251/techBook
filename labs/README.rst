实验资产
========

每个章节在 ``labs/<book>/<chapter>/`` 下保存独立实验。

建议结构：

.. code-block:: text

   labs/<book>/<chapter>/
   ├── README.rst
   ├── src/
   ├── tests/
   ├── scripts/
   └── output/

``README.rst`` 记录目标、环境、命令和成功判据。``output/`` 只保存正文实际引用的短输出；大型 trace 和构建产物不提交。

实验目录必须能在不阅读正文的情况下独立运行。正文通过相对路径 ``literalinclude`` 引用这里的代码。
