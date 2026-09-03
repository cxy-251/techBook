========================================================================================
07.03 WebAssembly (WASM) 逆向分析、动态混淆与 VM 虚拟机反混淆还原
========================================================================================

.. note:: 前置背景与上下文承接
   在前一节中，我们深入剖析了 YouTube 网页播放器中基于 JavaScript AST 静态分析与 EJS 沙箱的签名（``sig``）及防限速（``n-parameter``）求解流水线。然而，随着 Web 技术与反爬对抗的持续升级，主流流媒体平台（如 Bilibili、TikTok、AbemaTV、各大版权保护点播平台）逐步放弃了单纯依靠明文 JavaScript 混淆的防御策略，全面转向 **WebAssembly (WASM)** 二进制模块以及 **自定义虚拟机（Custom Bytecode VM / Control Flow Flattening）** 加固方案。WASM 抹去了高级语言的高层语法树结构，仅暴露出平坦的线性内存与低层堆栈机字节码；而 JS 虚拟机混淆则通过自定义操作码分发器彻底粉碎了控制流逻辑。本节将全面解构 WASM 模块运行机制、线性内存交互模型、动态 Hook 逆向范式、JS 自定义 VM 反平坦化以及 ``yt-dlp`` 应对二进制加固的工业级求解流水线。

***
WebAssembly (WASM) 体系架构与流媒体加固模型
***

WebAssembly (WASM) 是一种基于堆栈式虚拟机的紧凑二进制指令集标准（W3C 规范）。流媒体平台利用 C/C++/Rust 或 Go 编写核心认证算法，并将其编译为 ``.wasm`` 二进制文件在浏览器中运行：

.. code-block:: text
   :caption: WebAssembly 模块与宿主 JavaScript 双向交互架构

   +-------------------------------------------------------------------------------+
   | 宿主浏览器 / JS 运行时 (V8 / JavaScriptCore / Deno / Node.js)                   |
   | +---------------------------------------------------------------------------+ |
   | | JavaScript 胶水层 (Glue Code)                                             | |
   | | - WebAssembly.instantiate(wasmBytes, importObject) 实例化                 | |
   | | - 字符串 UTF-8 编码 -> 写入 WASM 线性内存 (Linear Memory)                 | |
   | | - 调用导出函数 exports._encrypt(ptr, len) -> 触发二进制计算               | |
   | | - 从线性内存指针读取密文数据 -> 转换为 JS 字符串 / Base64                 | |
   | +---------------------------------------------------------------------------+ |
   +---------------------------------------+---------------------------------------+
                                           |
                                           | 共享线性内存 (WebAssembly.Memory, 64KB/Page)
                                           v
   +-------------------------------------------------------------------------------+
   | WASM 二进制模块 (Module)                                                      |
   | +-----------------+ +-----------------+ +-----------------+ +---------------+ |
   | | Type Section    | | Import Section  | | Function Section| | Table Section | |
   | | (函数签名定义)  | | (宿主导入 API)  | | (内部函数索引)  | | (间接调用表)  | |
   | +-----------------+ +-----------------+ +-----------------+ +---------------+ |
   | +-----------------+ +-----------------+ +-----------------+ +---------------+ |
   | | Memory Section  | | Global Section  | | Export Section  | | Code Section  | |
   | | (堆内存空间)    | | (全局变量池)    | | (导出函数符号)  | | (堆栈机器字节)| |
   | +-----------------+ +-----------------+ +-----------------+ +---------------+ |
   +-------------------------------------------------------------------------------+

WASM 反爬加固的核心安全特性
~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. **语法结构高度平坦化**：WASM 丢弃了所有局部变量名、函数名与对象属性名（仅保留有限的导出符号），静态代码退化为纯粹的底层操作码序列（如 ``i32.add``、``i64.load``、``call_indirect``）；
2. **线性内存地址隔离**：WASM 无法直接访问浏览器的 DOM、BOM 或 JavaScript 全局变量，所有数据交换必须通过字节数组指针在连续物理内存块中传递；
3. **原生执行速度与复杂度**：由于运行在底层 JIT/AOT 编译器之上，平台可以在 WASM 内部执行高达数百万次的大规模混淆迭代、魔改密码学哈希（如非标 SM3/SM4、加盐 SHA-256）与矩阵变换，而不会引起前端卡顿。

---
WASM 线性内存交互模型与动态 Hook 逆向范式
---

逆向分析 WASM 模块无需暴力还原每一行 C 源码，关键在于理清其 **线性内存指针传递模型（Pointer Protocol）** 与 **导入/导出表边界**。

1. 内存管理与字符串传递机制
~~~~~~~~~~~~~~~~~~~~~~~~~~~

WASM 导出的加密函数通常接收内存偏移量（``offset`` / ``pointer``）与字节长度（``length``），而非 JavaScript 原生对象：

.. code-block:: text
   :caption: WASM 线性内存读写与指针调用时序

   JS 运行时                                          WASM 线性内存 (64KB Pages)
       |                                                         |
       |-- 1. 调用 exports.malloc(length) 申请缓冲区 ----------->|
       |<-- 返回内存指针 ptr (例如 0x10040) ---------------------|
       |                                                         |
       |-- 2. new Uint8Array(memory.buffer, ptr, length).set() ->| 将原始待签名字符串写入内存
       |                                                         |
       |-- 3. 调用 exports.sign_payload(ptr, length) ----------->| 执行二进制变换与哈希计算
       |<-- 返回输出密文指针 out_ptr (例如 0x100a0) -------------|
       |                                                         |
       |-- 4. 从 memory.buffer 读取 out_ptr 对应字节切片 ------->|
       \-- 完成字符串还原并释放内存 exports.free(ptr) ----------|

2. 导入对象 (importObject) 动态 Hook 与环境探测欺骗
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了检测运行环境是否为真实浏览器，WASM 通常会通过 ``importObject.env`` 导入一系列 JavaScript 辅助函数，用以读取时间戳、系统熵源或执行反调试。

``yt-dlp`` 及相关解密流水线通过在加载 WASM 时注入伪造的 ``importObject``，实现对底层行为的全面监控与欺骗：

.. code-block:: javascript
   :caption: WASM 导入表拦截与环境桩代码注入 (EJS / JSBridge)

   const memory = new WebAssembly.Memory({ initial: 256, maximum: 512 });
   const importEnv = {
       env: {
           memory: memory,
           // 1. 拦截高精度时间戳获取，锁定随机性
           emscripten_get_now: () => Date.now(),
           // 2. 模拟高保真伪随机数生成器 (规避真随机数导致的结果不可复现)
           crypto_get_random: (ptr, len) => {
               const view = new Uint8Array(memory.buffer, ptr, len);
               for (let i = 0; i < len; i++) view[i] = (i * 37 + 13) & 0xFF;
           },
           // 3. 拦截控制台日志与反调试探针
           emscripten_notify_memory_growth: (index) => {},
           abort: (errCode) => { throw new Error(`WASM abort called with code: ${errCode}`); }
       }
   };

   // 实例化 WASM 模块
   const wasmModule = await WebAssembly.instantiate(wasmBuffer, importEnv);
   const instance = wasmModule.instance;

3. 三大 WASM 逆向破译工程路径
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在实际流媒体引擎研发中，面对不同复杂度的 WASM 模块，通常采取三级分层破译策略：

.. list-table:: WASM 逆向破译策略与性能/维护权衡
   :widths: 20 40 40
   :header-rows: 1

   * - 策略名称
     - 实现原理与技术链
     - 适用场景与工程优劣
   * - **路径 1: 运行时黑盒 RPC 调度**
     - 抓取原始 ``.wasm`` 字节码，在 Node.js / Deno 沙箱中通过标准 API 实例化并调用导出函数
     - **优势**：免逆向算法细节，100% 还原行为；**劣势**：需依赖外部 JS 运行时与额外网络/本地文件加载
   * - **路径 2: 内存 Dump 与算法 Python 化**
     - 使用 ``wasm2wat`` 反编译为 S-表达式汇编，定位核心 S-Box 与位运算，用纯 Python 重写
     - **优势**：零外部依赖，毫秒级执行；**劣势**：算法更新时需重新静态逆向反编译
   * - **路径 3: 汇编重构与符号执行**
     - 借助 Ghidra / Binary Ninja WASM 插件反编译为 C 伪代码，提取常量表与魔改哈希向量
     - **优势**：彻底消除死代码与冗余控制流；**劣势**：逆向成本极高，适用于核心高频平台

---
JavaScript 自定义虚拟机 (Custom VM) 混淆逆向与反平坦化
---

除 WASM 之外，以 **控制流平坦化（Control Flow Flattening）** 与 **自定义字节码虚拟机（Custom Bytecode VM）** 为代表的 JS 高级混淆，是另一大阻碍自动化提取的工业级防御手段。

1. 自定义 JS 虚拟机的核心构造
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

自定义虚拟机混淆器会将真实的业务代码编译为私有字节码序列，并在前端注入一个解释器核心（Dispatcher Loop）：

.. code-block:: text
   :caption: 自定义 JS 虚拟机执行与控制流平坦化拓扑

   原始线性控制流 (如 a = x + y; if (a > 10) return b;)
                        |
                        v 虚拟机编译器 (VM Compiler) 混淆转换
   +-------------------------------------------------------------------------------+
   | 1. 私有字节码流 (Bytecode Array):                                             |
   |    [0x3A, 0x01, 0x02, 0x8F, 0x10, 0x4C, 0x00, 0xFF, ...]                      |
   +---------------------------------------+---------------------------------------+
                                           |
                                           v 注入前端 JS 虚拟机执行引擎
   +-------------------------------------------------------------------------------+
   | 2. 虚拟机分发主循环 (Virtual Dispatcher Loop):                                |
   |    while (true) {                                                             |
   |        var opcode = bytecode[vpc++];                                          |
   |        switch (opcode) {                                                      |
   |            case 0x3A: // VIRTUAL_ADD (从虚拟栈弹出两数相加并压栈)             |
   |                vstack.push(vstack.pop() + vstack.pop()); break;               |
   |            case 0x8F: // VIRTUAL_JUMP_IF_GREATER                              |
   |                if (vstack.pop() > 10) vpc = target; break;                    |
   |            case 0xFF: // VIRTUAL_HALT                                         |
   |                return vstack.pop();                                           |
   |        }                                                                      |
   |    }                                                                          |
   +-------------------------------------------------------------------------------+

2. 基于 AST 的控制流反平坦化 (De-flattening)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

控制流平坦化通过引入虚假状态变量（State Variable）将原本清晰的 `if-else` 和循环结构打碎为嵌套在大 `switch-case` 内的平坦基本块（Basic Blocks）。

反平坦化算法通过静态遍历 AST 树重建控制流图（CFG）：

.. code-block:: text
   :caption: AST 控制流图 (CFG) 重建与块拓扑消除

   平坦化结构 (Flat Switch):
   var state = 0;
   while (state !== 99) {
       switch(state) {
           case 0: stmt1; state = 2; break;
           case 1: stmt3; state = 99; break;
           case 2: stmt2; state = 1; break;
       }
   }
              |
              v 静态符号追踪 (Symbolic State Tracking) 与基本块拓扑排序
   还原后结构 (Structured AST):
   stmt1;
   stmt2;
   stmt3;

3. 纯 Python AST 虚拟机解释器 (jsinterp.py 扩展机制)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``yt-dlp`` 的 ``JSInterpreter`` 针对平台常见的平坦化状态机设计了高效的上下文缓存与短路求值：

.. code-block:: python

   # yt_dlp/jsinterp.py 内部操作码分发与作用域解析模型
   class JSInterpreter:
       def interpret_statement(self, stmt, local_vars, allow_recursion=100):
           if allow_recursion <= 0:
               raise ExtractorError('Recursion limit reached in JS interpreter')
           
           # 1. 识别并提取平坦化分发器中的 SwitchStatement
           if stmt.startswith('switch'):
               discriminant, cases = self._parse_switch_cases(stmt)
               target_val = self.interpret_expression(discriminant, local_vars)
               # 2. 命中目标 Case 分支并执行，跳过无效死代码分支
               for case_val, body in cases:
                   if case_val == target_val or case_val == 'default':
                       return self.interpret_statement(body, local_vars, allow_recursion - 1)
           
           # 3. 递归解释赋值、三元运算与原生对象方法
           return self._eval_expression(stmt, local_vars)

---
典型流媒体平台加固对抗实战案例
---

1. Bilibili Wbi 鉴权与 S-Box 字符映射表混淆
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Bilibili 在自适应视频流 URL 中部署了 **WBI 动态签名机制**。其核心并不直接使用硬编码密钥，而是通过 ``img_key`` 与 ``sub_key`` 经过特定置换表（Mixin Key S-Box）重组生成临时密钥，再对所有请求参数按字典序排序后计算加盐 MD5：

.. code-block:: python
   :caption: Bilibili WBI 签名重组与纯 Python 算法复现 (yt_dlp/extractor/bilibili.py)

   # WBI 固化置换映射表 (S-Box 索引拓扑)
   MIXIN_KEY_ENC_TAB = [
       46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
       27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
       37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
       22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
   ]

   def _get_wbi_keys(self):
       # 1. 从导航接口或网页配置中提取 img_url 与 sub_url
       img_key = self._extract_key_from_url(img_url)
       sub_key = self._extract_key_from_url(sub_url)
       raw_key = img_key + sub_key
       
       # 2. 根据 S-Box 字符置换生成 32 位混合密钥 (Mixin Key)
       mixin_key = ''.join(raw_key[n] for n in MIXIN_KEY_ENC_TAB)[:32]
       return mixin_key

   def _sign_wbi_params(self, params, mixin_key):
       # 3. 注入当前 Unix 时间戳并按键名字典序排序
       params['wts'] = int(time.time())
       sorted_params = '&'.join(f'{k}={urllib.parse.quote(str(v), safe="")}' 
                                for k, v in sorted(params.items()))
       # 4. 计算加盐哈希作为 w_rid 鉴权令牌
       params['w_rid'] = hashlib.md5((sorted_params + mixin_key).encode()).hexdigest()
       return params

2. TikTok / 短视频平台 VM-Bogus 算法逆向与 RPC 桥接
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

针对短视频平台极其复杂的 VM 虚拟化加密（例如 X-Bogus / MSToken 签发）：
* 平台虚拟机包含多达 60+ 个自定义操作码，涵盖大量针对字符串的位循环移位、RC4 动态变种加密与浏览器 Canvas/WebGL 指纹采样；
* ``yt-dlp`` 采取 **解耦式外部 JS 运行时桥接架构**，在隔离的 Node.js/Deno 子进程中加载封装后的纯净 JS 虚拟机上下文，以亚毫秒级延迟产出合法签名，兼顾了极致性能与对抗敏捷度。

---
端到端 WASM 与 VM 反混淆执行时序图
---

.. code-block:: text
   :caption: 二进制加固与 VM 反混淆端到端处理全景

   Extractor._real_extract()
               |
               v 判定加固形态 (WASM 二进制 vs JS 自定义 VM)
   +-------------------------------------------------------------------------------+
   | [分支 A: WebAssembly 二进制加固]      | [分支 B: JS 自定义 VM / 平坦化加固]     |
   |                                       |                                       |
   | 1. 尝试静态算法 Python 还原:          | 1. 尝试纯 Python AST 解释:            |
   |    - 查找已知 S-Box / 算法常数        |    - JSInterpreter 递归下降解释       |
   |    - 纯 Python 极速本地计算           |    - 自动消除死代码与平坦化 Switch    |
   |                                       |                                       |
   | 2. 若算法频繁动态变异 -> 降级为 RPC:  | 2. 若 VM 过度复杂 -> 降级为外部运行时: |
   |    - 提取 .wasm 模块二进制数据        |    - 调度 _jsruntime (Deno / Node.js) |
   |    - WebAssembly.instantiate 实例化   |    - 注入全局 BOM/DOM 虚拟桩环境      |
   |    - 线性内存写入与导出函数 Hook 调用 |    - JIT 原生执行并返回计算令牌       |
   +---------------------------------------+---------------------------------------+
                                           |
                                           v
   +-------------------------------------------------------------------------------+
   | 3. 将计算得到的签名令牌 (如 w_rid, x_bogus, token) 注入自适应流媒体请求 URL    |
   | 4. 交付 Downloader 发起无阻断高速切片抓取                                     |
   +-------------------------------------------------------------------------------+

核心源码行级对照表
~~~~~~~~~~~~~~~~~~

.. list-table:: WASM 与动态反混淆相关核心模块与源码位置
   :widths: 30 26 44
   :header-rows: 1

   * - 核心类 / 函数
     - 所在源文件与行号区间
     - 核心职责与设计要点
   * - ``JSInterpreter``
     - ``yt_dlp/jsinterp.py:125-450``
     - 抽象语法树解释器、Switch 状态机调度、弱类型运算模拟
   * - ``BiliBiliIE._get_wbi_keys()``
     - ``yt_dlp/extractor/bilibili.py:280-320``
     - WBI S-Box 字符置换映射表计算与加盐 MD5 签名生成
   * - ``_jsruntime.py``
     - ``yt_dlp/networking/_jsruntime.py:1-240``
     - 外部 JS/WASM 运行时子进程管道管理与 IPC 数据序列化
   * - ``TikTokBaseIE._sign()``
     - ``yt_dlp/extractor/tiktok.py:150-210``
     - 移动端/Web 端复杂虚拟机签名算法调度与参数注入

***
小结与下章导读
***

本节深入剖析了现代流媒体反爬对抗的深水区——**WebAssembly (WASM) 逆向与 JavaScript 自定义虚拟机反混淆**，明确了：
1. WASM 堆栈机模型、线性内存（Linear Memory）指针传递协议与导入/导出符号边界；
2. 宿主环境桩注入（Mocking ``importObject``）与伪随机/时间戳拦截技术；
3. 自定义 JS 虚拟机的操作码分发循环（Dispatcher Loop）与基于 AST 的控制流反平坦化算法；
4. Bilibili WBI 与主流短视频平台在静态算法还原与外部运行时 RPC 调度之间的工程选型。

在突破了播放器签名、防限速参数与二进制虚拟机加固之后，流媒体巨头（尤其是 Google / YouTube）部署了当前安全防御体系的终极防线——**基于设备硬件与浏览器内核签名的 Proof of Origin (PO Token) 与 BotGuard/GVisor 虚拟机系统**。在全书最后一节（``07_reverse_engineering_and_js_engine/04_po_token_and_botguard.rst``）中，我们将深入解构 **Google BotGuard 字节码解释器逆向、WebPO 与 Android Attestation (GMS 硬件级凭证) 模拟以及 PO Token 动态协商全生命周期**。
