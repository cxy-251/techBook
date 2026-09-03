========================================================================================
07.02 YouTube 播放器脚本逆向：AST 语法树静态分析、n-parameter 算法提取与 sig 解密
========================================================================================

.. note:: 前置背景与上下文承接
   在前一节中，我们深入剖析了 ``yt-dlp`` 革命性的外部 JavaScript 运行时架构（``_jsruntime.py`` 与 EJS 沙箱通信管道）。然而，拥有高性能 JS 执行环境只是求解反爬挑战的第一步。如何从 YouTube 极其庞大且频繁动态混淆的网页播放器脚本（``base.js``，体积通常超过 2.5MB）中，精准定位并提取出核心的动态签名置换算法（``sig``）与防限速令牌（``n-parameter``），是流媒体逆向工程领域最核心的攻防焦点。本节将深度解构 YouTube 双重认证令牌体系、纯 Python AST 模拟解释器（``jsinterp.py``）、基于 Meriyah 语法树模式匹配的 EJS 求解引擎（``yt.solver.core.js``）以及基于置换序列投影的高性能查表缓存算法。

***
YouTube 双重认证令牌体系与对抗全景
***

YouTube 为了防止第三方客户端脱机批量抓取视频并防御未经授权的 CDN 流量盗刷，在自适应流媒体切片 URL 中部署了两套相互独立又相互依存的密码学/混淆验证机制：

.. code-block:: text
   :caption: YouTube 双重流媒体认证令牌体系架构

   自适应流媒体请求 URL (未解密状态):
   https://rr---sn-xxxx.googlevideo.com/videoplayback?expire=...&id=...&itag=251&n=X9a_1bC4dEf&signatureCipher=s=AQAA...&sp=sig&url=https%3A%2F%2F...
                                                 |                                   |
                                                 v                                   v
   +----------------------------------------------------------------+   +----------------------------------------------------------------+
   | 1. 防限速令牌 (Throttling Parameter: n)                        |   | 2. 动态签名解密 (Signature Decryption: sig)                    |
   | - 作用: 动态流速门禁与带宽控制                                 |   | - 作用: 分片 URL 访问权限密码学校验                            |
   | - 表现: 若请求缺失 n 或 n 值计算错误，CDN 强制将传输速度        |   | - 表现: 原始 URL 被封装在 signatureCipher 中，必须通过特定的  |
   |         断崖式限制在 40~50 KB/s；计算正确则全速突发 (100MB/s+) |         数组逆序/切片/对调操作恢复原始 sig 并追加到查询参数    |
   +----------------------------------------------------------------+   +----------------------------------------------------------------+

播放器脚本与 signatureTimestamp (sts) 绑定
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当客户端调用 InnerTube API 请求视频流元数据时，必须在请求体 ``playbackContext.contentPlaybackContext`` 中声明当前使用的播放器签名时间戳 ``signatureTimestamp``（简称 ``sts``，通常为一个 5 位整数，如 ``20245``）：

.. code-block:: python

   # yt_dlp/extractor/youtube/_video.py
   def _extract_signature_timestamp(self, video_id, player_url, ytcfg=None, fatal=False):
       # 1. 从 ytcfg 中提取 STS 字段
       sts = traverse_obj(ytcfg, ('STS', {int_or_none}))
       if sts:
           return sts
       # 2. 从 player base.js 脚本中正则匹配
       if code := self._load_player(video_id, player_url, fatal=fatal):
           sts = int_or_none(self._search_regex(
               r'(?:signatureTimestamp|sts)\s*:\s*(?P<sts>[0-9]{5})', code,
               'JS player signature timestamp', group='sts', fatal=fatal))
       return sts

服务端在收到带有 ``sts`` 的 API 请求后，会使用对应版本播放器的算法对当前视频流生成加密的 ``s`` 与混淆的 ``n``。如果客户端在下载时使用的解密逻辑与 API 声明的 ``sts`` 所属版本不匹配，请求将被 CDN 直接返回 HTTP 403 拒绝访问。

---
经典纯 Python AST 解释器解密机制 (jsinterp.py)
---

在早期的逆向对抗中，``yt-dlp`` 与 ``youtube-dl`` 主要通过内置的轻量级 JavaScript 解释器 ``JSInterpreter``（``yt_dlp/jsinterp.py``）在纯 Python 环境中静态模拟 JS 执行。

1. 签名解密函数入口与辅助置换对象定位
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

签名解密函数是一个接受单个字符串参数并返回置换后字符串的顶级函数。``_extract_signature_function`` 通过多组鲁棒的正规表达式扫描 ``base.js``：

.. code-block:: text
   :caption: 签名解密主函数典型源码形态 (混淆后)

   var FEa = function(a) {
       a = a.split("");
       EEa.sH(a, 2);      // 操作 1: 切片/位移 (splice)
       EEa.JV(a, 34);     // 操作 2: 索引对调 (swap)
       EEa.rK(a, 4);      // 操作 3: 字符序列翻转 (reverse)
       EEa.JV(a, 61);     // 操作 4: 索引对调 (swap)
       return a.join("");
   };

   var EEa = {
       sH: function(a, b) { a.splice(0, b); },
       JV: function(a, b) { var c = a[0]; a[0] = a[b % a.length]; a[b % a.length] = c; },
       rK: function(a) { a.reverse(); }
   };

2. 三大基本置换算子的抽象代数定义
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

尽管混淆变量名每日更新，但 YouTube 签名的核心变换严格由以下三类基本算子复合而成：

.. math::

   \begin{aligned}
   \mathcal{R}(A) &: A \leftarrow [A_{n-1}, A_{n-2}, \dots, A_0] \quad (	ext{Reverse}) \
   \mathcal{S}_k(A) &: A \leftarrow [A_k, A_{k+1}, \dots, A_{n-1}] \quad (	ext{Splice / Slice } k) \
   \mathcal{T}_k(A) &: A_0 \leftrightarrow A_{k \pmod n} \quad (	ext{Swap with index } k)
   \end{aligned}

3. JSInterpreter 递归解释器内部构造
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``JSInterpreter`` 并不依赖重量级编译器，而是通过词法切分符 ``_separate`` 与递归下降状态机执行 AST 解释：
* **作用域链管理（``LocalNameSpace``）**：基于 ``collections.ChainMap`` 模拟 JavaScript 词法作用域与变量提升；
* **操作符语义模拟（``_OPERATORS``）**：实现 JavaScript 特有的弱类型隐式类型转换（如 ``int_to_int32``、``_js_bit_op``、``_js_ternary``）；
* **对象与原型链映射**：拦截原生 Array 方法（``split``、``join``、``reverse``、``slice``、``splice``、``push``、``pop``）并映射为 Python 底层 ``list`` 高效就地操作。

---
现代 EJS 静态 AST 模式匹配与求解引擎 (yt.solver.core.js)
---

随着 YouTube 引入防限速 ``n-parameter``，其变换逻辑变得极其复杂——包含嵌套大循环、动态类型强制转换、深度递归函数调用及多重控制流平坦化混淆。纯 Python 解释执行单次计算耗时高达 200ms~1000ms，在解析包含数十个自适应流的视频时会引发严重的性能瓶颈与超时。

``yt-dlp`` 引入了基于 **Meriyah**（极速 ECMAScript 解析器）与 **Astring**（AST 代码生成器）的纯静态分析求解引擎 **EJS**（``yt.solver.core.js``）。

.. code-block:: text
   :caption: EJS 静态 AST 解析与求解器合成流水线

   原始 YouTube 播放器脚本 base.js (~2.5MB)
                        |
                        v meriyah.parse(data)
   +-------------------------------------------------------------------------------+
   | 1. 全局 AST 树语法解析与清洗 (modifyPlayer):                                  |
   |    - 定位并提取核心闭包函数体 block                                           |
   |    - 剔除无副作用的 DOM 操作与冗余事件监听器，保留赋值与计算表达式            |
   +---------------------------------------+---------------------------------------+
                                           |
                                           v 模式匹配搜索 (extract & matchesStructure)
   +-------------------------------------------------------------------------------+
   | 2. 结构化特征定位:                                                            |
   |    - 搜索包含关键验证断言的 AST 节点 (如 arguments: ['alr', 'yes'])          |
   |    - 提取匹配的 FunctionDeclaration 或 AssignmentExpression 节点              |
   +---------------------------------------+---------------------------------------+
                                           |
                                           v 求解器代码生成 (createSolver & makeSolver)
   +-------------------------------------------------------------------------------+
   | 3. 沙箱环境重构与求解闭包注入:                                                |
   |    - 前置注入虚拟 BOM/DOM 环境 (window, document, location, XMLHttpRequest)   |
   |    - 动态组装高阶求解函数: ({sig, n}) => { ... }                              |
   |    - 构造 multiTry 熔断调度器 (多候选分支交叉比对)                            |
   +-------------------------------------------------------------------------------+
                        |
                        v 交付外部 JS 运行时 (Deno/Node/Bun) 原生 JIT 执行

1. AST 结构模式匹配器 (matchesStructure)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

EJS 定义了声明式的 AST 结构树匹配规则，以解耦对具体变量名的依赖：

.. code-block:: javascript

   const identifier = {
     or: [
       {
         type: 'ExpressionStatement',
         expression: {
           type: 'AssignmentExpression',
           operator: '=',
           left: { or: [{ type: 'Identifier' }, { type: 'MemberExpression' }] },
           right: { type: 'FunctionExpression', async: false },
         },
       },
       { type: 'FunctionDeclaration', async: false, id: { type: 'Identifier' } },
       // 匹配 var xxx = function(...) 声明
     ],
   };

2. 虚拟宿主环境注入与原型链探测 (createSolver)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

为了欺骗 ``base.js`` 中的防调试与反爬环境探测代码，EJS 在 AST 顶部无缝拼接了标准的全局虚拟对象桩（Stubs）：

.. code-block:: javascript

   const setupNodes = meriyah.parse(`
       if (typeof globalThis.location === "undefined") {
           globalThis.location = new URL("https://www.youtube.com/watch?v=yt-dlp-wins");
       }
       if (typeof globalThis.document === "undefined") {
           globalThis.document = Object.create(null);
       }
       if (typeof globalThis.window === "undefined") {
           globalThis.window = globalThis;
       }
   `).body;

在执行 ``n`` 参数求解时，EJS 通过探测返回对象的原型链（``Object.getPrototypeOf(url)``），动态枚举并触发被平坦化混淆的变换方法：

.. code-block:: javascript

   function createSolver(expression) {
       return generateArrowFunction(`
           ({sig, n}) => {
               const url = (${astring.generate(expression)})("https://youtube.com/watch?v=yt-dlp-wins", "s", sig ? encodeURIComponent(sig) : undefined);
               url.set("n", n);
               const proto = Object.getPrototypeOf(url);
               const keys = Object.keys(proto).concat(Object.getOwnPropertyNames(proto));
               for (const key of keys) {
                   if (!["constructor", "set", "get", "clone"].includes(key)) {
                       url[key](); // 触发动态解密变换
                       break;
                   }
               }
               const s = url.get("s");
               return {
                   sig: s ? decodeURIComponent(s) : null,
                   n: url.get("n") ?? null,
               };
           }
       `);
   }

3. 多求解器结果交叉验证与熔断 (multiTry)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

当混淆脚本中存在多个看似合法的候选解密函数时，``multiTry`` 将所有提取出的求解器并行执行。若所有候选均抛出异常，则抛出 ``no solutions``；若多个求解器输出了不一致的计算结果，则立即触发 ``invalid solutions`` 熔断报警，防止向 CDN 发送脏数据导致 IP 被封控。

---
批量挑战求解流水线与置换投影查表优化
---

在提取包含 30+ 自适应流的视频时，若对每个流的 URL 单独执行解密，开销巨大。``yt-dlp`` 设计了优雅的 **两阶段批量收集与置换投影查表** 架构。

1. 第一阶段：挑战元数据两阶段批量收集
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

在 ``_extract_formats_and_subtitles`` 中，提取器首先执行快速扫描，将所有格式的加密需求聚合成集合：

.. code-block:: python

   # 收集所有独特的 n 参数与签名长度
   for streaming_data in traverse_obj(player_responses, (..., 'streamingData', {dict})):
       for fmt_stream in traverse_obj(streaming_data, (('formats', 'adaptiveFormats'), ..., {dict})):
           if not fmt_stream.get('url'):
               sc = urllib.parse.parse_qs(fmt_stream.get('signatureCipher'))
               if s_challenge := traverse_obj(sc, ('s', 0)):
                   s_challenges.add(len(s_challenge))  # 仅记录签名长度特征！
           if n_challenge := traverse_obj(fmt_url, ({parse_qs}, 'n', 0)):
               n_challenges.add(n_challenge)

2. 签名置换操作的数学投影与 $O(1)$ 查表优化
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

由于对相同长度的字符串，签名解密函数的执行路径和置换步骤是完全同构的。为了彻底消除对每个流重复执行 JS 解密的开销，``yt-dlp`` 提出了 **恒等序列变换投影算法**：

.. math::

   \mathbf{I}_L = [0, 1, 2, \dots, L-1]

1. 构造长度为 $L$ 的有序整数序列（字符表示：``''.join(map(chr, range(L)))``）；
2. 仅将该基准序列传入 JS 解密函数计算一次，输出变换后的置换索引映射表 $\mathbf{P}_L$；
3. 将 $\mathbf{P}_L = [	ext{ord}(c) 	ext{ for } c 	ext{ in } 	ext{result}]$ 写入磁盘缓存（``sigfuncs`` 命名空间）；
4. 对于后续任意真实加密签名 $S$（长度为 $L$），直接利用 Python 列表推导式在内存中以 $O(1)$ 复杂度瞬间完成置换：

.. code-block:: python

   def solve_sig(s, spec):
       # spec 为预先计算并缓存的置换索引列表 [15, 0, 2, 83, ...]
       return ''.join(s[i] for i in spec)

这一设计使得整个视频所有音视频格式的签名解密开销从数百毫秒降至微秒级！

3. 动态 URL 重写与参数拼装
~~~~~~~~~~~~~~~~~~~~~~~~~~

解密完成后，URL 重组流水线完成最终参数组装：

.. code-block:: python

   # 1. 恢复原始 URL 并附加解密后的 signature
   if encrypted_sig:
       spec = self._load_player_data_from_cache('sigfuncs', player_url, len(encrypted_sig), use_disk_cache=True)
       fmt_url += '&{}={}'.format(
           traverse_obj(sc, ('sp', -1)) or 'signature',
           solve_sig(encrypted_sig, spec))

   # 2. 原地替换混淆的 n 参数
   if n_challenge:
       n_result = self._load_player_data_from_cache('n', player_url, n_challenge)
       fmt_url = update_url_query(fmt_url, {'n': n_result})

   # 3. 注入 GVS WebPO Token (若策略要求)
   if po_token:
       fmt_url = update_url_query(fmt_url, {'pot': po_token})

---
端到端逆向解密架构图与源码映射
---

.. code-block:: text
   :caption: YouTube 签名与 n 参数端到端逆向求解全景

   YoutubeIE._real_extract()
             |
             v 获取 player_url (base.js) 并提取 sts (signatureTimestamp)
   +-------------------------------------------------------------------+
   | 1. 构造 InnerTube API 请求:                                       |
   |    - 注入 sts -> playbackContext.contentPlaybackContext           |
   |    - 获得包含 signatureCipher 与 n-parameter 的 streamingData     |
   +---------------------------------+---------------------------------+
                                     |
                                     v _extract_formats_and_subtitles()
   +-------------------------------------------------------------------+
   | 2. 收集挑战元数据:                                                |
   |    - s_challenges.add(len(encrypted_sig))                         |
   |    - n_challenges.add(n_param)                                    |
   +---------------------------------+---------------------------------+
                                     |
                                     v solve_js_challenges() -> JsChallengeDirector
   +-------------------------------------------------------------------+
   | 3. EJS / JSInterpreter 求解:                                      |
   |    - 静态 AST 分析提取解密算法 (yt.solver.core.js)                |
   |    - 原生 JS 运行时批量执行计算                                   |
   |    - 计算并缓存基准置换序列 spec: [ord(c) for c in result]        |
   +---------------------------------+---------------------------------+
                                     |
                                     v URL 参数重组与分片下载
   +-------------------------------------------------------------------+
   | 4. 组装最终 CDN 请求:                                             |
   |    - 查表计算: solve_sig(encrypted_sig, spec)                     |
   |    - 参数覆写: update_url_query(url, {'n': n_result, 'pot': pot}) |
   |    - 交付 Downloader 发起高带宽无限速 HTTP GET                    |
   +-------------------------------------------------------------------+

核心源码行级对照表
~~~~~~~~~~~~~~~~~~

.. list-table:: YouTube 签名与 n-sig 逆向解密核心模块与源码位置
   :widths: 30 26 44
   :header-rows: 1

   * - 核心类 / 函数
     - 所在源文件与行号区间
     - 核心职责与设计要点
   * - ``JSInterpreter``
     - ``yt_dlp/jsinterp.py:125-450``
     - 纯 Python 实现的 JavaScript AST 解释器、作用域与操作符模拟
   * - ``yt.solver.core.js``
     - ``yt_dlp/extractor/youtube/jsc/_builtin/vendor/yt.solver.core.js:1-260``
     - 基于 Meriyah/Astring 的 AST 模式匹配器、BOM 桩注入与求解器生成
   * - ``_extract_signature_timestamp()``
     - ``yt_dlp/extractor/youtube/_video.py:2229-2265``
     - 从 ytcfg / player 脚本中提取 ``sts`` 绑定时间戳
   * - ``solve_js_challenges()``
     - ``yt_dlp/extractor/youtube/_video.py:3390-3440``
     - 挑战批量聚合、调度外部求解器与置换序列缓存
   * - ``solve_sig()``
     - ``yt_dlp/extractor/youtube/_video.py:3380-3385``
     - 恒等序列投影查表算法，实现 $O(1)$ 微秒级字符串重构
   * - ``_extract_formats_and_subtitles()``
     - ``yt_dlp/extractor/youtube/_video.py:3360-3700``
     - `signatureCipher` 解析、`n` 参数提取、URL 重写与格式组装

***
小结与下章导读
***

本节全面剖析了流媒体反爬对抗领域最具代表性的核心战役——**YouTube 播放器脚本逆向与双重认证解密**，深入阐明了：
1. 防限速令牌（``n-parameter``）与访问签名（``sig``）在 CDN 流量调度与权限控制中的作用机理；
2. ``signatureTimestamp``（``sts``）在版本绑定与防降级中的核心约束；
3. 纯 Python 静态解释器 ``JSInterpreter`` 对作用域链、基本置换算子（Reverse/Splice/Swap）的模拟实现；
4. 现代 EJS 引擎基于 Meriyah 语法树模式匹配（``matchesStructure``）、沙箱桩环境注入与多解交叉验证（``multiTry``）的高效求解逻辑；
5. 恒等置换投影查表算法（``solve_sig``）在多流场景下的极致性能优化。

然而，随着 Web 技术的发展，越来越多的流媒体平台（如哔哩哔哩、TikTok、各类版权 DRM 平台）开始将核心防爬加固逻辑迁移至 **WebAssembly（WASM）** 二进制指令集与复杂的虚拟化解释器（VM Obfuscation）中。在下一节（``07_reverse_engineering_and_js_engine/03_wasm_and_dynamic_obfuscation.rst``）中，我们将深入解构 **WebAssembly (WASM) 逆向分析技术、内存导出函数 Hook、动态指令混淆与自定义虚拟机（Custom VM）反混淆还原流水线**。
