第144章：File Upload, Object Storage, Media Asset, and Large Data Path
======================================================================

核心知识点
----------

* 文件上传是跨 browser、network、server、object storage、database、worker、CDN 与 authorization 的数据路径，不应被理解成单个 ``POST /upload``。
* Browser ``File`` 只是用户授权给页面的本地对象；客户端校验文件名、扩展名、size、MIME 只能改善 UX，最终授权与内容校验必须在可信边界重新执行。
* 小文件可经 app server 中转；大文件/高并发媒体更适合 server 生成受限 upload capability 后由 browser 直传 object storage。
* Server-mediated upload 控制集中，但占用应用服务器带宽、request lifetime、memory/temp disk 与并发；direct upload 减少中转成本，但需要 upload session、signed URL、完成确认和 reconciliation。
* Signed/presigned upload capability 必须限制 object key、method、expiry、tenant、size/content 条件与必要 checksum；泄漏半径应控制在单次、短时、特定对象。
* Binary data 与 metadata 生命周期不同。Bytes 通常由 object storage 拥有；owner、tenant、business relation、size、hash、MIME、visibility、processing status 和 object key 由 database 拥有。
* 上传应使用明确状态机，例如 ``created → uploading → uploaded → scanning → processing → ready``，并为 ``failed / blocked / deleted`` 定义恢复路径。
* 大文件需要 progress、chunk/multipart、resume、retry、cancel、timeout 与 checksum；整个文件重传不适合脆弱网络和长时上传。
* Media asset 常需要异步 post-processing：virus scan、EXIF cleanup、thumbnail、image optimization、video transcode、audio waveform、content moderation、format conversion 与 CDN publish。
* Object storage permission 必须与 application authorization 对齐。Public/private ACL、bucket policy、signed download URL、CDN token 不能绕过用户/tenant 权限模型。
* Upload success 与 business success 不是同一状态。对象写入成功但数据库确认失败，会产生 orphan；数据库记录存在但 object 缺失，会产生 broken reference。
* 生命周期必须包含 cleanup/reconciliation：取消上传、超时 upload session、替换旧头像、删除业务资源、处理失败、孤儿对象都需要后台回收与审计。

关键路径
--------

对象存储直传：

::

   user selects File
   → browser local precheck
   → request upload session from trusted server
   → auth + tenant + quota + object-key policy
   → server returns short-lived signed upload capability
   → browser multipart/chunk upload to object storage
   → checksum / complete confirmation
   → server verifies object metadata
   → database marks uploaded/processing
   → worker scan/transcode
   → mark ready
   → authorized CDN/download delivery

失败恢复：

::

   object exists but DB not confirmed
   → retry completion or reconciliation scan
   → attach object if valid
   → otherwise expire and delete orphan

概念辨析
--------

* **File 与 Asset**：File 是浏览器本地对象；asset 是经过授权、持久化、处理并进入业务状态机的系统资源。
* **Object Storage 与 Database**：前者保存 bytes，后者保存业务元数据、权限与处理状态。
* **Server Upload 与 Direct Upload**：前者中转数据，后者中转授权；两者都必须由应用 server 拥有业务权限判断。
* **Upload Complete 与 Ready**：bytes 上传完成不代表扫描、转码、审核和权限发布已经完成。
* **Public URL 与 Authorized Access**：有 URL 不等于公开资源；私有对象应通过短期签名或受控 delivery path 授权访问。

本章结论
--------

文件系统应按 ``Local File → Upload Capability → Binary Storage → Metadata State → Async Processing → Authorized Delivery → Cleanup`` 设计。核心是把大二进制路径和业务状态路径分离，再用受控状态机、权限和 reconciliation 把它们重新绑定成可靠资产生命周期。
