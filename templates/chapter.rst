章节标题
========

.. Replace this file name with ``chapter-<question>.rst``.
.. Add a stable label above the title when another chapter needs to reference it.

问题
----

用一句话描述输入、可观察动作和需要解释的结果。

最小实验
--------

说明实验只保留了哪些必要条件。

.. literalinclude:: ../../labs/<book>/<chapter>/src/main.c
   :language: c
   :linenos:

执行与输出
----------

.. code-block:: console

   $ <exact command>
   <real output>

观察
----

只写从输出直接得到的判断。

最短源码路径
------------

#. ``path/to/source.c:function_a``：说明关键输入和传出状态。
#. ``path/to/source.c:function_b``：说明关键判断和下一节点。

解释
----

把实验观察与源码节点逐项对应。每段增加一个新判断。

失败边界
--------

给出一个失败或边界用例，并说明它改变了哪项前提。

检查题
------

#. 根据输出判断当前路径经过了哪个节点。
#. 修改一个输入后，哪项状态会先发生变化？
