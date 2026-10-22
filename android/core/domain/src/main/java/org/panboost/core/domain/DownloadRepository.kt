package org.panboost.core.domain

import kotlinx.coroutines.flow.Flow

/**
 * 下载仓库接口（第 2 周）。
 *
 * 实现于 :core:data（WorkManager 队列 + MediaStore 落盘）。
 * 语义约定：
 * - enqueue：入队即返回；同 id 任务已在队列时保持既有任务
 *   （KEEP——重复点击不重复排队，第 3 周验收项）
 * - observeAll：任务列表冷热流（WorkManager 状态驱动，实时
 *   刷新进度）
 * - cancel：取消排队/运行中任务（运行中的半成品文件由实现
 *   负责清理）
 * - retry：失败/取消任务重新入队（REPLACE 语义，携带原任务参数）
 */
interface DownloadRepository {
    fun enqueue(task: DownloadTask)
    fun observeAll(): Flow<List<DownloadTask>>
    fun cancel(taskId: String)
    /** v5.3.3：重试传完整任务（原 URL/文件名/线程）——修复"重试变模拟下载"。 */
    fun retry(task: DownloadTask)
}
