========================================================================
第 7 模块：自定义节点协议与 WebSocket 通信体系 (07_custom_nodes_and_comms)
========================================================================

.. toctree::
   :maxdepth: 2
   :caption: 模块章节目录

   01_custom_node_protocol_and_registration
   02_v3_api_and_typing_architecture
   03_server_and_rest_api_layer
   04_websocket_streaming_and_client_sync

模块架构概述
============

本模块剖析 ComfyUI 的生态基石与前后端通信底座：动态自定义节点扩展协议与基于 WebSocket 的实时全双工流式通信机制。

ComfyUI 的生态繁荣归功于其简洁而强悍的扩展抽象与异步通信架构：

1. **节点协议标准与注册机制**：解析 ``NODE_CLASS_MAPPINGS``、``INPUT_TYPES`` 与 ``RETURN_TYPES`` 契约规范，以及插件加载器的动态导入与热重载。
2. **V3 API 面向对象节点规范**：剖析新一代面向对象节点架构（``_ComfyNodeInternal`` / ``io.Combo`` / ``V3Data``）与严格的 Schema 动态校验。
3. **aiohttp 服务端与 REST 路由**：深入 ``server.py`` 异步 HTTP 服务实现，解析提示词提交接口（``/prompt``）、队列控制与历史状态查询。
4. **WebSocket 流式事件总线**：解剖基于二进制及 JSON 消息的实时通知协议（``executing`` / ``progress`` / ``executed``），实现毫秒级 UI 状态与图片流式回传。
