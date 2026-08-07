第042章：Module Object、sys.modules 与 Import Cache
===================================================

核心知识点
----------

* module object 是模块代码执行后的运行时状态容器；``module.__dict__`` 保存模块全局 namespace。
* 模块中定义的函数，其 ``__globals__`` 通常指向所属 module 的 namespace；函数读取全局名字时回到这份字典。
* module object 还保存 ``__name__``、``__package__``、``__loader__``、``__spec__``、``__file__``、``__cached__`` 等导入元数据。
* ``sys.modules`` 是解释器级 module cache，完整模块名映射到 module object；正常导入首先检查这个缓存。
* 首次导入包含“搜索、创建、缓存、执行”；后续缓存命中主要复用现有 module object，并在调用方执行新的名字绑定。
* 导入系统会在模块顶层代码执行前把 module object 放入 ``sys.modules``；循环导入因此能取得同一个对象，也会看到尚未完整填充的 namespace。
* partially initialized module 的关键证据是：``sys.modules`` 中存在 module，但目标属性尚未进入 ``module.__dict__``。
* ``from module import name`` 会把 ``name`` 当前指向的对象直接绑定到调用方；后续 module 对同名变量重新绑定，不会自动修改已经流出的旧引用。
* ``importlib.reload(module)`` 通常复用同一个 module object，并重新执行模块代码；新的定义会覆盖 namespace 中同名绑定。
* reload 不会自动更新其它模块此前通过 ``from x import Y`` 得到的旧对象，也不会让旧 class instance 自动变成新 class instance。
* 删除 ``sys.modules[name]`` 后再次导入通常走新的模块创建流程，可能产生与旧对象并存的新 module identity。
* 重新导入后，同名 class/function 可能具有不同 identity；``isinstance``、注册表、序列化、单例和插件状态都可能受影响。
* ``importlib.invalidate_caches()`` 处理 finder/path 搜索缓存，不负责重新执行 module，也不负责替换 ``sys.modules`` 中的对象。
* 内存或热更新问题应同时追踪 module object、module namespace 和已经流出到其它地方的对象引用。

关键路径
--------

模块对象状态链：

::

   create module object
       ↓
   initialize import metadata
       ↓
   sys.modules[name] = module
       ↓
   execute top-level code in module.__dict__
       ↓
   functions/classes keep references to module namespace
       ↓
   other modules may copy references out

Reload 路径：

::

   existing module object
       ↓
   resolve module spec/loader
       ↓
   execute source again in existing module.__dict__
       ↓
   overwrite/recreate selected bindings
       ↓
   external old references remain unchanged

概念辨析
--------

* **module object 与源码文件**：源码文件是可能的来源；module object 才是运行时导入结果。
* **module namespace 与函数 globals**：函数定义后通常继续引用所属 module 的同一全局 namespace。
* **``sys.modules`` 与 path cache**：``sys.modules`` 缓存 module identity；finder/path cache 缓存搜索结果或搜索器。
* **缓存复用与局部 import binding**：模块对象可以复用多次，但每次 import statement 仍可在不同作用域建立新的名字绑定。
* **半初始化与未找到模块**：半初始化表示对象已经创建并缓存；``ModuleNotFoundError`` 通常表示搜索阶段没有得到目标模块。
* **reload 与 fresh import**：reload 倾向复用 module object；删除 ``sys.modules`` 后重新导入可能创建新 module object。
* **重新执行代码与更新外部引用**：重新执行只改变 module namespace 中的新绑定，已经被其它对象持有的旧引用仍然存在。

本章结论
--------

理解 Python 导入缓存的关键是把 module identity 和 namespace binding 分开。``sys.modules`` 决定导入时优先复用哪个 module object，模块代码则不断向该对象的 ``__dict__`` 写入和重新绑定名字。循环导入暴露半初始化 namespace，reload 暴露旧引用与新绑定并存，删除缓存重导入则可能产生新的 module identity。排查热更新和导入状态时，应同时检查 ``sys.modules[name] is module``、``module.__dict__`` 当前内容，以及外部是否还持有旧 class/function/module 引用。