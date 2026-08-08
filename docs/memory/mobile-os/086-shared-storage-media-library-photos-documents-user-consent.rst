第086章：Shared Storage, Media Library, Photos, Documents, User Consent
======================================================================

核心知识点
----------

* Shared Storage 承载用户可见、可能跨 App 使用的数据；风险来自集合可枚举、元数据可推断、授权范围扩大和数据长期残留。
* 媒体库不是裸目录，而是系统维护的用户数据集合；照片、视频、音频通常通过媒体索引、picker、PhotoKit/MediaStore 等入口访问。
* 用户“选择一个文件/几张照片”和“允许访问整个集合”是不同授权级别；前者应优先用于单项任务。
* 读取、写入、导出、删除、元数据访问和持久访问是不同能力，不能用一个“存储权限”概括。
* Android 主要使用 Photo Picker、MediaStore、Storage Access Framework、``content://`` URI 与 persistable URI grant。
* Apple 主要使用 Photos/PhotosUI、Document Picker、Files、security-scoped URL 与 bookmark。
* 用户同意的稳定语义是：系统把一次明确选择转换成有限、可撤销、可追踪的资源访问能力，而不是把整个文件系统交给 App。

关键路径
--------

::

   App request
     → System Picker / Media Library API
     → User selection or permission grant
     → URI / asset identifier / URL
     → Provider / Photos service / document service
     → read / edit / export
     → persist grant / bookmark when needed
     → revoke / move / delete handling

从相册选图并导出 PDF：

::

   Photo Picker
     → selected media handles
     → App processing
     → Create Document / Files save location
     → write PDF
     → user-visible file remains outside App private container

概念辨析
--------

* **Shared storage vs App-specific storage**：共享数据属于用户空间并可能跨 App；app-specific 数据默认只属于当前 App，卸载语义也不同。
* **Collection access vs item access**：集合访问允许枚举持续变化的数据集；单项访问只暴露用户明确选择的对象，权限面更小。
* **Media library vs document model**：媒体库按照片、视频、音频等集合与元数据组织；普通文档更适合 picker、provider 和文件协调模型。
* **Permission vs consent token**：权限可能开放一类能力；picker 返回的 URI、URL 或 bookmark 表示对具体对象的用户授权。
* **Export vs internal save**：导出把结果交给用户管理，生命周期不再与 App 私有容器绑定。

本章结论
--------

共享存储的核心是最小暴露：优先让用户选择具体对象，仅在产品确实需要批量管理时申请集合级访问。任何共享文件功能都要同时定义读取范围、写入位置、持久授权、撤销与删除后的恢复路径。