第003章：GPU 内存层级与缓存
===========================

核心知识点
----------

内存层级决定数据到达执行单元的成本
   shader 数据可能来自 register、shared/local memory、texture cache、L1/L2、VRAM 或 unified memory。越远的层级通常具有更高延迟和更大共享吞吐；真实性能还取决于并发访问、缓存命中、事务合并和是否有其它执行组覆盖等待。

寄存器压力会改变内存等待能力
   寄存器保存线程临时变量，访问最快，但每个线程占用过多寄存器会降低同一计算单元可驻留的执行组数量。发生 register spill 时，本应位于寄存器的数据进入更慢的内存路径，源码中的局部变量增长可能表现为额外访存和 stall。

共享存储用于组内复用
   shared memory、LDS 或 threadgroup memory 适合把一块远端数据加载一次，再由同一工作组多次读取。收益成立的条件是复用密集、数据块能容纳、同步次数受控；只读取一次或存在严重 bank conflict 时，搬运和 barrier 可能比直接读取更贵。

局部性决定缓存和事务效率
   空间局部性让相邻线程访问相邻地址，时间局部性让数据在被替换前再次使用，coalesced access 让同一 ``warp`` 或 ``wavefront`` 的请求合并为较少内存事务。随机索引、大 stride、非对齐布局和跨链表访问会降低每次事务中的有效字节比例。

缓存命中不能消除必要字节量
   连续的全屏采样可能拥有较高缓存命中率，但四张高精度全分辨率纹理和多个 render target 仍可能填满带宽。缓存问题需要同时检查命中率与总读写字节；命中率低关注布局和局部性，带宽已满关注格式、分辨率、采样数和中间资源数量。

渲染目标与搬运是稳定带宽来源
   MRT 数量、像素格式、分辨率、MSAA sample count、透明混合、resolve、copy、upload 和 readback 都会增加内存流量。这些成本常位于 render pass 或 copy 命令，而不在 shader 源码中。

资源生命周期会把访存变成等待
   一个 pass 写出的 texture 或 buffer 被后续 pass 读取时，需要正确的可见性和状态转换；CPU 与 GPU 复用同一动态资源时，需要 frame-in-flight 隔离或完成信号。过宽 barrier、立即 readback 和过早复用都会把内存路径转化为同步停顿。

优化动作必须绑定具体资源路径
   纹理路径优先检查压缩、mipmap、通道打包、采样次数和分辨率；buffer 路径优先检查结构布局、连续访问、排序与 compact；render target 路径优先检查 attachment、格式、load/store、MSAA 与 pass 合并；上传路径优先使用 ring buffer、staging 和批量 copy。

关键路径
--------

一次纹理采样的数据路径：

::

   shader invocation 生成 UV 与采样请求
   → 执行组向 texture unit 发射请求
   → 检查 texture cache 与 L1/L2
   → 未命中时访问 VRAM 或 unified memory
   → 返回 texel 并执行过滤与格式解码
   → 结果写入寄存器
   → 执行组恢复后续指令

跨 pass 的资源路径：

::

   G-buffer pass 写 render target
   → attachment 数据留在 tile/cache 或写回外部内存
   → 资源完成写后读状态转换
   → lighting pass 读取 G-buffer
   → cache 命中或发起外部内存事务
   → 光照结果写入 HDR target
   → 后处理继续读取、写入或 resolve

内存瓶颈定位路径：

::

   找到最慢 pass
   → 列出输入 texture、buffer 与输出 attachment
   → 估算分辨率、格式、sample count、元素数量和总字节
   → 判断访问连续、间接、随机还是写后读
   → 对照 bandwidth、cache miss、transaction、stall 与 copy/resolve 证据
   → 只修改一条布局、格式、采样或同步假设并复测

概念辨析
--------

* **延迟与带宽**：延迟表示单次请求多久返回；带宽表示单位时间能搬运多少数据。随机依赖链容易暴露延迟，连续大规模读写容易填满带宽。
* **缓存命中率与数据量**：高命中率表示更多请求在近端得到满足，不代表总字节量低；低命中率也可能因工作量很小而不是主瓶颈。
* **AoS 与 SoA**：AoS 把对象字段放在一起，适合每次读取完整对象；SoA 把同类字段连续排列，适合某个 pass 批量读取少数字段。应按 pass 的真实字段需求选择或拆分 stream。
* **VRAM 与 unified memory**：VRAM 强调设备本地容量、上传和显式搬运；unified memory 共享物理内存池，但仍存在 GPU cache、同步、带宽争用和读写方切换成本。
* **纹理缓存与通用缓存**：纹理缓存针对二维空间局部性、过滤和 mipmap 访问优化；L1/L2 服务更广泛的 texture、buffer 和 render target backing store。两者最终都受访问模式与工作集大小约束。
* **压缩与降低分辨率**：压缩减少每个 texel 的存储和传输字节，通常保留原尺寸；降低分辨率减少 texel 数量，也改变空间细节。两者都需检查格式支持、色彩空间和视觉误差。
* **barrier 与数据搬运**：barrier 表达顺序和可见性，不必然复制数据；resolve、copy 和 readback 明确搬运数据。某些架构上的状态转换可能触发 flush 或写回，但不能把所有 barrier 等同于 copy。

本章结论
--------

GPU 内存问题必须从资源读写图而不是单条 shader 语句开始分析。阅读代码或 frame capture 时，先确定数据位于哪一层、以何种模式被访问、总共读写多少字节以及何时跨越 pass 或 CPU/GPU 所有权边界，再用 bandwidth、cache、transaction、stall 和 copy/resolve 证据选择布局、压缩、mipmap、local memory、批量上传或同步收窄策略。