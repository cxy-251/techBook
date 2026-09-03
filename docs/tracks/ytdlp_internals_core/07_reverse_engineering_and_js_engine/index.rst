========================================================================
第 7 模块：逆向对抗、JS 执行引擎与反爬突破 (07_reverse_engineering_and_js_engine)
========================================================================

本模块深入剖析 ``yt-dlp`` 在当代高强度反爬与加密对抗中的核心武器库。重点解析针对 YouTube 等大型流媒体平台的动态 JS 混淆求解、WASM 逆向与设备指纹模拟。

.. toctree::
   :maxdepth: 2
   :caption: 本模块章节导航

   01_js_runtime_bridge
   02_youtube_signature_and_n_sig
   03_wasm_and_dynamic_obfuscation
   04_po_token_and_botguard

模块核心要点
------------

1. **JS 运行时桥接架构**：解剖 `_jsruntime.py` 对 Deno、Node.js、Bun 与 QuickJS 的子进程桥接机制、IPC 通信协议与执行安全性。
2. **YouTube 签名与 n-parameter 逆向算法**：基于 AST 的播放器核心函数定位、操作码模拟执行、`sig` 与 `n` 参数动态解密算法。
3. **WebAssembly (WASM) 逆向与 VM 混淆还原**：WASM 模块反编译、指令模拟执行与控制流平坦化反混淆技术。
4. **PO Token (Proof of Origin) 与 BotGuard 对抗**：Google GVisor / BotGuard 脚本逆向、设备指纹认证与 WebPO / AndroidPO 凭证生成方案。
