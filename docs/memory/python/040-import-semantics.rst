第040章：Import Semantics
=========================

核心知识点
----------

* ``import`` 的语义可以拆成两步：先搜索/获得 module object，再把结果绑定到当前 namespace。
* module object 是模块运行时状态容器；顶层赋值、函数、类和导入结果都写入 ``module.__dict__``。
* package 本质上也是 module object；带有 ``__path__`` 的 module 具有 package 语义，可继续搜索子模块。
* ``sys.modules`` 是导入系统的第一层缓存，键为 fully qualified module name，值通常是 module object。
* 首次加载时，模块对象会先写入 ``sys.modules``，再执行模块顶层代码；这一顺序使递归导入能够收敛，也产生半初始化模块状态。
* 模块首次成功加载后，再次导入通常复用同一 module object，模块顶层代码不会自动重新执行。
* ``import app.service`` 通常在当前作用域绑定 ``app``；``from app.service import value`` 则直接绑定 ``value`` 当前指向的对象。
* 父包与子模块之间存在对象连接：成功导入 ``app.service`` 后，父包 ``app`` 通常会出现 ``service`` 属性，并指向 ``sys.modules['app.service']``。
* relative import 依赖 package context，核心元数据是 ``__package__`` 与 ``__spec__``；文件系统相邻关系本身不是相对导入的解析依据。
* 包内模块直接按文件路径执行时常缺失正确 package context；通过 ``python -m package.module`` 运行更符合 import machinery 的名字模型。
* 导入系统会协调同一模块的初始化，使并发首次导入通常只执行一份模块初始化；该锁只保护导入状态，不替代应用级副作用的并发控制。
* 循环导入的核心风险不是“模块不存在”，而是“module object 已经存在，但目标名字尚未绑定”。
* 加载失败时，失败模块自身通常会从 ``sys.modules`` 移除；此前已成功加载的依赖模块可能继续保留。
* 删除 ``sys.modules`` 项后重新导入可能产生新的 module object；旧 module、旧 class、旧 function 仍可能被其它引用持有。

关键路径
--------

首次导入主路径：

::

   import package.module
       ↓
   resolve fully qualified name
       ↓
   lookup sys.modules
       ↓ miss
   locate loading plan
       ↓
   create module object
       ↓
   initialize import metadata
       ↓
   insert into sys.modules
       ↓
   execute module top-level code
       ↓
   populate module.__dict__
       ↓
   bind child module on parent package
       ↓
   bind requested name in caller namespace

循环导入状态：

::

   module A cached before execution completes
       ↓
   A imports B
       ↓
   B imports/reads A
       ↓
   B receives the same A module object
       ↓
   requested A attribute may not exist yet
       ↓
   partially initialized module failure

概念辨析
--------

* **module 与 namespace**：module 是对象；``module.__dict__`` 是它保存全局绑定的 namespace。
* **module 与 package**：package 仍是 module；``__path__`` 让它能作为子模块搜索边界。
* **搜索与名字绑定**：搜索/加载决定得到哪个对象；import statement 再决定当前作用域绑定什么名字。
* **缓存命中与重新执行**：命中 ``sys.modules`` 通常复用对象，不等于再次运行顶层代码。
* **``import x.y`` 与 ``from x.y import z``**：前者保留模块层级访问，后者把属性当前值直接绑定到调用方。
* **相对导入与文件路径**：相对导入以 package name 为基准，不以“当前文件旁边有什么文件”为基准。
* **循环导入与模块缺失**：循环导入中模块往往已存在；缺的是尚未执行到的 namespace binding。
* **导入锁与业务锁**：导入锁协调 module initialization；文件、网络、注册表等业务副作用仍需自己的同步和幂等设计。

本章结论
--------

Python 导入语义可以压缩为“模块名 → module object → ``sys.modules`` 状态 → 顶层执行 → namespace → 当前名字绑定”。排查导入问题时，先确认完整模块名和 module identity，再检查 ``sys.modules``、模块是否执行完成、当前调用方到底绑定了 module 还是 module attribute。循环导入、重复导入、相对导入和热重载问题都可以沿这条对象与状态链定位。