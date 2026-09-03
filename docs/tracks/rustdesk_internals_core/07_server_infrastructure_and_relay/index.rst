====================================================
模块 07：服务端架构与中继调度
====================================================

本模块深入剖析 RustDesk 服务端体系：注册与 ID 服务器（hbbs）架构、中继服务器（hbbr）高并发转发流水线，以及自建服务集群的高可用调度策略。

.. toctree::
   :maxdepth: 2
   :numbered:

   01_hbbs_id_server_internals
   02_hbbr_relay_server_pipeline
   03_cluster_routing_and_failover
