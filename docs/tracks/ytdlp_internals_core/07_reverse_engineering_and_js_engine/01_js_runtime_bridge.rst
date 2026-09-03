========================================================================================
07.01 外部 JS 运行时架构 (Deno/Node/Bun/QuickJS) 与进程间 IPC 沙箱通信
========================================================================================

.. note:: 前置背景与上下文承接
   在前六个模块中，我们系统性地解剖了 ``yt-dlp`` 从请求分发、网络伪装、提取器抽象、流媒体协议解析到音视频后处理的完整流水线。然而，现代顶级流媒体平台（以 YouTube、TikTok 为代表）为了遏制自动化抓取与保护专有流媒体资产，构建了极其严密的动态 JavaScript 混淆与防篡改签名体系（如 YouTube 播放器脚本中的动态签名变换 ``sig`` 与防限速令牌 ``n-parameter``）。早期工具依赖内置的纯 Python 正则解释器（``jsinterp.py``），但在面对 V8 现代语法、深度控制流平坦化混淆及复杂原型链调用时，解释执行性能低下且极易被语法变异击穿。``yt-dlp`` 研发了革命性的 **外部 JavaScript 运行时桥接架构（``_jsruntime.py`` 与 EJS 挑战求解流水线）**。本节将深度解构其多运行时探测自适应、进程间 IPC 通信、轻量沙箱安全隔离与密码学脚本完整性校验机制。

***
现代流媒体反爬对抗与 JS 执行引擎演进
***

流媒体平台在网页与客户端播放器中大量注入高度混淆的 JavaScript 逻辑，主要涵盖三大核心防御场景：
1. **动态签名变换（Signature Decryption / ``sig``）**：流切片 URL 中的核心认证令牌，由播放器脚本根据动态生成的数组置换、切片、倒序操作进行变换；
2. **下载速度限速对抗（Throttling Parameter / ``n-parameter``）**：视频服务器要求客户端在请求音视频分片时携带经过复杂动态计算的 ``n`` 参数，若计算错误或超时，传输带宽将被服务端降级至 40~50 KB/s；
3. **环境指纹与设备验证（BotGuard / Proof of Origin / WebPO）**：收集浏览器运行时环境特征与硬件指纹生成防机器人令牌。

.. code-block:: text
   :caption: 从 Python 内部解释器到外部原生 JS 运行时的演进

   [传统方案: jsinterp.py (纯 Python AST 模拟)]
   +-------------------------------------------------------------------------------+
   | 缺点:                                                                         |
   | 1. 执行开销巨大: 复杂的数组位运算与大循环在 Python 解释器中耗时数秒           |
   | 2. ECMAScript 规范兼容局限: 难以完美模拟 ES2020+、Proxy、BigInt 及隐式类型转换 |
   | 3. 脆弱性高: 平台微调语法或引入特殊原型链特性即导致 AST 解析崩溃             |
   +-------------------------------------------------------------------------------+
                                          |
                                          v 架构跃迁
   [现代方案: EJS (External JS Challenge Solver) 多运行时桥接引擎]
   +-------------------------------------------------------------------------------+
   | 优势:                                                                         |
   | 1. 原生 V8 / JSC 引擎驱动: 纳秒级 JIT 执行，100% 遵循 ECMAScript 官方规范      |
   | 2. 多运行时自适应降级: Deno -> Bun -> QuickJS -> Node.js 弹性调度            |
   | 3. 最小特权沙箱隔离: 禁用网络访问、文件系统读写，杜绝恶意脚本越权              |
   | 4. 密码学完整性保障: 严格校验求解器脚本 SHA3-512 哈希，防止中间人注入        |
   +-------------------------------------------------------------------------------+

---
多运行时探测与能力矩阵 (_jsruntime.py)
---

``yt_dlp/utils/_jsruntime.py`` 建立了对宿主环境中各类 JavaScript 运行时引擎的抽象层与自适应探测管道。

.. code-block:: text
   :caption: JsRuntime 类继承拓扑与执行优先级

                        +----------------------+
                        |   JsRuntime (ABC)    |
                        +----------+-----------+
                                   |
         +-----------------+-------+---------+-----------------+
         |                 |                 |                 |
         v                 v                 v                 v
   +------------+   +------------+   +---------------+   +------------+
   | DenoJsRT   |   | BunJsRT    |   | QuickJsRT     |   | NodeJsRT   |
   | (V8 引擎)  |   | (JSC 引擎) |   | (C 轻量引擎)  |   | (V8 引擎)  |
   | 优先级:1000|   | 优先级:900 |   | 优先级:850    |   | 优先级:800 |
   +------------+   +------------+   +---------------+   +------------+

运行时核心元数据模型 (JsRuntimeInfo)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

每个探测到的运行时被封装为不可变数据类 ``JsRuntimeInfo``：

.. code-block:: python

   @dataclasses.dataclass(frozen=True)
   class JsRuntimeInfo:
       name: str                  # 运行时标识: 'deno' | 'bun' | 'quickjs' | 'quickjs-ng' | 'node'
       path: str                  # 可执行文件物理绝对路径
       version: str               # 提取出的版本字符串 (如 '2.3.0')
       version_tuple: tuple[int]  # 结构化版本元组，用于版本号比较 (2, 3, 0)
       supported: bool = True     # 是否满足最低受支持版本门槛

多运行时最低版本与能力矩阵
~~~~~~~~~~~~~~~~~~~~~~~~~~

为了保证执行求解脚本时所依赖的 ES 标准特性可用，各运行时定义了明确的版本门槛：

.. list-table:: 支持的 JavaScript 运行时矩阵与版本基线
   :widths: 16 18 16 50
   :header-rows: 1

   * - 运行时名称
     - 底层 JS 引擎
     - 最低版本基线
     - 架构特性与选型考量
   * - **Deno**
     - V8
     - $\ge$ 2.3.0
     - **默认推荐**。具备最完备的原生安全权限控制命令行参数，隔离性最优
   * - **Bun**
     - JavaScriptCore
     - $\ge$ 1.2.11
     - 极速冷启动时间（<10ms），内存开销极低
   * - **QuickJS / QuickJS-ng**
     - QuickJS (C)
     - $\ge$ 2023.12.09 / 0.12.0
     - 极轻量级嵌入式引擎，零外部依赖，适合资源受限环境
   * - **Node.js**
     - V8
     - $\ge$ 22.0.0
     - 全球普及率最高的通用运行时，作为广泛的系统级兜底

可执行文件动态发现算法 (_find_exe)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在复杂环境（如 Windows、pipx 虚拟环境、PyInstaller 单文件打包打包环境）中，可执行文件的定位面临路径穿透与扩展名问题。``_find_exe`` 实现了四级回溯扫描：
1. **Python Scripts 目录优先**：检索 ``sysconfig.get_path('scripts')``（优先命中随环境安装的本地包）；
2. **PyInstaller 冻结包工作目录**：若处于打包环境（``sys.frozen=True``），检索主进程二进制所在目录；
3. **系统环境变量 PATH 与 PATHEXT 枚举**：逐项规范化（``normcase`` / ``realpath``）防重遍历，自动匹配 ``.EXE``、``.CMD``、``.BAT`` 等扩展名。

---
进程间 IPC 沙箱隔离与安全约束
---

在执行外部未知的挑战求解代码时，安全性是首要准则。恶意脚本绝不能利用外部运行时穿透到宿主系统读取凭证文件或发起恶意网络攻击。

Deno 最小特权沙箱约束 (DenoJCP)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``DenoJCP`` 通过向 Deno 子进程传递严格的封闭参数，彻底锁死所有外部访问能力：

.. code-block:: python

   _DENO_BASE_OPTIONS = [
       '--ext=js',                  # 强制以纯 JavaScript 语法解析标准输入
       '--no-code-cache',           # 禁用字节码持久化缓存，防止脏数据污染
       '--no-prompt',               # 禁用交互式权限弹窗提权
       '--no-remote',               # 严格禁止远程网络模块加载与 HTTP 请求
       '--no-lock',                 # 禁用依赖锁定检查
       '--node-modules-dir=none',   # 禁用本地 node_modules 文件探测
       '--no-config',               # 忽略宿主可能存在的 deno.json 配置文件
       '--cached-only',             # 仅允许使用内置/已缓存依赖
   ]

代理与环境变量隔离 (_get_env_options)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当运行时确需执行特定受控请求时，宿主环境变量与代理配置（``HTTP_PROXY``、``HTTPS_PROXY``、``NO_PROXY``）通过专用通道注入，避免泄露用户主进程敏感环境变量。

---
IPC 协议设计与批量解密流 (EJSBaseJCP)
---

``EJSBaseJCP``（``yt_dlp/extractor/youtube/jsc/_builtin/ejs.py``）定义了主 Python 进程与外部 JS 子进程之间的标准通信协议。

标准输入/输出 JSON 协议帧
~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: text
   :caption: IPC JSON 请求与响应协议结构

   [Python -> JS 子进程 (Stdin)]
   {
       "type": "player",
       "player": "<完整 YouTube base.js 播放器脚本文本>",
       "requests": [
           {"type": "n", "challenges": ["X9a_1bC..."]},
           {"type": "sig", "challenges": ["AQAA..."]}
       ],
       "output_preprocessed": true
   }
                               |
                               v 外部 JS 运行时执行 jsc(...) 算法求解
   [JS 子进程 -> Python (Stdout)]
   {
       "type": "success",
       "preprocessed_player": "<预处理与 AST 索引缓存>",
       "responses": [
           {"type": "success", "data": "k8L_2mD..."},
           {"type": "success", "data": "BAAA..."}
       ]
   }

批量聚合求解算法 (_real_bulk_solve)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当一个页面包含数十个自适应流时，为每个流单独启动一个 JS 子进程会导致巨大的进程创建开销（Fork Overhead）。``_real_bulk_solve`` 实现了请求批处理：

.. code-block:: python

   def _real_bulk_solve(self, requests: list[JsChallengeRequest]):
       # 1. 按照 player_url 对所有待解密挑战进行分组聚合
       grouped: dict[str, list[JsChallengeRequest]] = collections.defaultdict(list)
       for request in requests:
           grouped[request.input.player_url].append(request)

       for player_url, grouped_requests in grouped.items():
           # 2. 检查播放器预处理 AST 缓存
           player = self.ie.cache.load(self._CACHE_SECTION, f'player:{player_url}')
           cached = bool(player)
           if not player:
               player = self._get_player(video_id, player_url)

           # 3. 构造单次 IPC 批量请求输入
           stdin = self._construct_stdin(player, cached, grouped_requests)
           # 4. 单次子进程执行获得全部解密结果
           stdout = self._run_js_runtime(stdin)
           output = json.loads(stdout)

           # 5. 分发结果并生成预处理缓存
           ...

无 Stdin 管道环境的文件中继回退 (QuickJS)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

对于轻量级引擎 QuickJS（其命令行不原生支持 Stdin 代码直接交互），``QuickJSJCP`` 采用了安全的临时文件中继方案：

.. code-block:: python

   # 创建带有随机前缀的临时脚本文件
   temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False, encoding='utf-8')
   try:
       temp_file.write(stdin)
       temp_file.close()
       # 通过 --script 参数执行
       cmd = [self.runtime_info.path, '--script', temp_file.name]
       with Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as proc:
           stdout, stderr = proc.communicate_or_kill()
   finally:
       # 无论成功或异常，必须立即原子 unlink 销毁临时文件，防止敏感代码残留
       pathlib.Path(temp_file.name).unlink(missing_ok=True)

---
密码学脚本供应链完整性校验
---

为了防止网络中间人攻击（MITM）或恶意第三方插件篡改求解脚本，``EJSBaseJCP`` 构建了四级代码来源探测与 **SHA3-512** 强哈希校验网关：

.. code-block:: text
   :caption: 四级求解器脚本溯源与完整性校验链

   _iter_script_sources() 优先级枚举
                  |
                  +--> 1. PYPACKAGE: 直接载入已签名的 Python 预编译包 (yt_dlp_ejs)
                  |
                  +--> 2. CACHE: 本地磁盘缓存脚本 (~/.cache/yt-dlp/challenge-solver)
                  |
                  +--> 3. BUILTIN: 源码内嵌 Vendored 脚本 (vendor.load_script)
                  |
                  \--> 4. WEB: 从官方 GitHub Releases 拉取 (受 --remote-components 限制)
                                      |
                                      v 密码学强哈希校验
   +-------------------------------------------------------------------------------+
   | 1. 计算脚本代码哈希: hash = hashlib.sha3_512(script.code.encode()).hexdigest()|
   | 2. 匹配版本: version_tuple(script.version)[:2] == _SCRIPT_VERSION             |
   | 3. 校验允许哈希: hash in _ALLOWED_HASHES[script_type][script_variant]         |
   |    (若哈希不匹配 -> 发出警告并立即清空受污染的本地缓存，阻断恶意执行)          |
   +-------------------------------------------------------------------------------+

---
端到端 JS 挑战求解架构图与源码映射
---

.. code-block:: text
   :caption: 外部 JS 运行时桥接端到端时序流

   YoutubeIE                 JsChallengeDirector             DenoJCP / NodeJCP          外部 Deno 进程
       |                              |                              |                        |
       |-- 需要解密 n / sig 挑战 ---->|                              |                        |
       |                              |-- 查找最高优先级 Provider -->|                        |
       |                              |   (preference=1000)          |                        |
       |                              |                              |-- 校验 Script SHA3-512 |
       |                              |                              |-- 聚合批量 Requests    |
       |                              |                              |-- 构造 IPC Stdin 帧 -->|
       |                              |                              |                        |-- 执行 V8 JIT 求解
       |                              |                              |<-- 捕获 Stdout JSON ---|
       |                              |<-- 返回解密数据结构 ---------|                        \-- 进程退出
       |<-- 交付真实 n/sig 认证参数 --|
       \-- 发起带签名分片 HTTP GET -> CDN 服务器

核心源码行级对照表
~~~~~~~~~~~~~~~~~~

.. list-table:: 外部 JS 运行时桥接引擎核心模块与源码位置
   :widths: 30 26 44
   :header-rows: 1

   * - 核心类 / 函数
     - 所在源文件与行号区间
     - 核心职责与设计要点
   * - ``JsRuntime`` / ``JsRuntimeInfo``
     - ``yt_dlp/utils/_jsruntime.py:45-125``
     - 跨平台 JavaScript 运行时基类、版本探测与能力矩阵
   * - ``_find_exe()``
     - ``yt_dlp/utils/_jsruntime.py:15-44``
     - 针对 Windows PATHEXT、PyInstaller 及虚拟环境的可执行程序发现
   * - ``EJSBaseJCP``
     - ``yt_dlp/extractor/youtube/jsc/_builtin/ejs.py:55-220``
     - JS 挑战求解提供者基类、四级脚本来源与 SHA3-512 完整性防线
   * - ``DenoJCP``
     - ``yt_dlp/extractor/youtube/jsc/_builtin/deno.py:20-100``
     - Deno 运行时沙箱参数编排、代理环境注入与子进程管道管控
   * - ``QuickJSJCP``
     - ``yt_dlp/extractor/youtube/jsc/_builtin/quickjs.py:15-60``
     - QuickJS 临时文件中继执行、原子清理与轻量降级机制
   * - ``JsChallengeDirector``
     - ``yt_dlp/extractor/youtube/jsc/_director.py:30-180``
     - 挑战求解器路由器、优先级调度与批量解密状态机

***
小结与下章导读
***

本节深入解构了 ``yt-dlp`` 在应对高级 Web 反爬中最为关键的底层基石——**外部 JavaScript 运行时架构与 IPC 通信协议**，系统性厘清了：
1. 从脆弱的 Python AST 模拟（``jsinterp.py``）向原生 V8 / JSC 运行时集群（``_jsruntime.py``）的架构演进动因；
2. Deno、Bun、QuickJS、Node.js 的四层自适应探测与版本门槛矩阵；
3. 遵循最小特权原则的 Deno / Bun 沙箱命令行参数隔离体系与代理变量隧道；
4. 基于 Stdin/Stdout JSON 协议的批量聚合求解算法（``_real_bulk_solve``）与 QuickJS 临时文件中继设计；
5. 基于 SHA3-512 强哈希校验与版本锁定的脚本供应链安全防护体系。

在掌握了外部 JS 运行时的基础设施之后，我们将切入整个流媒体逆向领域最著名的攻防战役——在下一节（``07_reverse_engineering_and_js_engine/02_youtube_signature_and_n_sig.rst``）中，我们将深入剖析 **YouTube 播放器脚本逆向技术：AST 语法树静态分析、n-parameter 混淆算法提取与 sig 解密状态机**。
