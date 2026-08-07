第001章：Python 执行模型
========================

核心知识点
----------

代码块是执行单位
   Python 以 code block 组织编译和执行。模块顶层、函数体、类体、交互式输入以及传给 ``eval()``、``exec()`` 的代码，都可能形成独立代码块。

执行上下文承载运行环境
   代码块执行时需要当前 frame、local namespace、global namespace、builtins namespace、异常状态和控制权返回位置。相同源码放入不同上下文，名字解析和绑定结果可能不同。

``code object``、function object 与 frame 分工不同
   ``code object`` 描述可执行代码；function object 连接代码、globals、默认参数和 closure；frame 表示某一次正在进行或被暂停的执行，保存局部状态、指令位置和调用关系。

模块、函数和类的执行时机不同
   模块顶层在加载或导入时顺序执行；``def`` 先创建函数对象，函数体只在调用时执行；class body 在执行到 ``class`` 语句时立即运行，所得 namespace 随后用于创建 class object。

普通名字按作用域分类后查找
   函数中的普通名字通常沿 local、enclosing、global、builtins 查找。编译器会先把名字分类为 local、free、cell 或 global，运行期 frame 再按分类访问对应存储位置。

类 namespace 不是函数闭包作用域
   class body 的绑定会成为类属性来源，但定义在类体中的方法或推导式不会把 class namespace 当作 enclosing function scope。类属性应通过类或实例的 attribute lookup 访问。

frame 生命周期可能超过一次普通调用
   函数返回后 frame 通常退出调用栈；traceback、生成器、协程、调试器或 ``inspect`` 仍可能持有它，使局部对象和执行状态继续存活。

关键路径
--------

源码进入运行时：

::

   源码文本
   → 按 code block 编译为 code object
   → 创建或取得 execution context
   → 建立 frame
   → 按名字分类访问 locals、closure、globals、builtins
   → 执行语句并产生返回、异常或暂停
   → frame 退出调用栈或被其它对象继续持有

函数调用路径：

::

   求值得到 function object
   → 求值实参对象
   → 创建调用 frame 并绑定形参
   → 执行对应 code object
   → 调用嵌套函数时压入新 frame
   → 返回值或异常把控制权交回调用方 frame

概念辨析
--------

* **``code object`` 与 function object**：前者保存已编译代码及静态元数据；后者把代码与 globals、defaults、closure 等调用环境连接起来。
* **function object 与 frame**：函数对象可以被调用多次；每次调用通常产生独立 frame，保存该次执行的动态状态。
* **namespace 与 scope**：namespace 是名字到对象的映射；scope 是源码中能够直接读取某组绑定的文本范围。
* **名字绑定与名字查找**：绑定决定名字写入哪个 namespace；查找决定读取时从哪些位置取得对象。
* **class namespace 与 enclosing scope**：class namespace 形成类属性；enclosing scope 只来自词法嵌套的函数作用域。

本章结论
--------

阅读 Python 执行过程时，应先定位代码块，再区分 ``code object``、function object 和 frame，随后沿 namespace 与调用栈追踪名字、状态和控制权；涉及 traceback、生成器或协程时，还要检查 frame 是否在离开调用栈后继续被持有。
