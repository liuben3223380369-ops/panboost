package org.panboost.core.data

import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.ExistingWorkPolicy
import androidx.work.OneTimeWorkRequest
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkInfo
import androidx.work.WorkManager
import androidx.work.workDataOf
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import org.panboost.core.domain.DownloadRepository
import org.panboost.core.domain.DownloadStatus
import org.panboost.core.domain.DownloadTask
import java.util.concurrent.TimeUnit
import javax.inject.Inject
import javax.inject.Singleton

/**
 * 下载仓库实现（第 2 周：WorkManager 队列）。
 *
 * - 任务唯一性：uniqueWork 名 = "download-{id}" + ExistingWorkPolicy
 *   .KEEP —— 重复 enqueue 同 id 不重复排队（第 3 周验收项
 *   "无重复排队"在本层落实）；retry 用 REPLACE 顶替失败任务
 * - v4.1.0：真实 URL 走 MultiThreadDownloadWorker（Range 分块
 *   并发 + part 断点续传 + 前台服务 dataSync——Android 14+ 长时
 *   Worker 规范，退后台不被冻结）
 * - 进度：WorkInfo.progress.bytes → DownloadTask.downloadedBytes
 *   （observeAll 的 Flow 由 WorkManager 状态流驱动，实时刷新）
 * - 持久化：WorkManager 自带队列持久化（进程死亡/重启后续跑），
 *   Kivy 时代"下载列表靠内存"的结构性缺陷就此消除
 */
@Singleton
class DownloadRepositoryImpl @Inject constructor(
    @ApplicationContext private val context: Context,
    private val history: DownloadHistoryStore,
    private val appLog: org.panboost.core.logging.AppLog,
) : DownloadRepository {

    private val workManager: WorkManager
        get() = WorkManager.getInstance(context)

    override fun enqueue(task: DownloadTask) {
        val request = if (task.url.startsWith("mock://")) {
            mockRequest(task)
        } else {
            urlRequest(task)
        }
        workManager.enqueueUniqueWork(
            uniqueName(task.id),
            ExistingWorkPolicy.KEEP,
            request,
        )
    }

    private fun mockRequest(task: DownloadTask): OneTimeWorkRequest {
        val request = OneTimeWorkRequestBuilder<MockDownloadWorker>()
            .setInputData(
                workDataOf(
                    MockDownloadWorker.KEY_FILE_NAME to task.fileName,
                    MockDownloadWorker.KEY_MIME to task.mimeType,
                    MockDownloadWorker.KEY_TOTAL to task.totalBytes,
                )
            )
            .setConstraints(
                Constraints.Builder()
                    .setRequiresStorageNotLow(true)
                    .build()
            )
            .setBackoffCriteria(
                BackoffPolicy.EXPONENTIAL,
                BACKOFF_SECONDS,
                TimeUnit.SECONDS,
            )
            .addTag(TAG)
            .build()
        return request
    }

    /** 真实下载（v4.1.0：多线程分块 + 前台服务 dataSync）。 */
    private fun urlRequest(task: DownloadTask): OneTimeWorkRequest =
        OneTimeWorkRequestBuilder<MultiThreadDownloadWorker>()
            .setInputData(
                workDataOf(
                    MultiThreadDownloadWorker.KEY_URL to task.url,
                    MultiThreadDownloadWorker.KEY_REFERER to "https://pan.quark.cn/",
                    MultiThreadDownloadWorker.KEY_THREADS to parseThreads(task.threadsChoice),
                    MockDownloadWorker.KEY_FILE_NAME to task.fileName,
                    MockDownloadWorker.KEY_MIME to task.mimeType,
                )
            )
            .addTag(TAG)
            .build()

    private val recordedIds = java.util.concurrent.ConcurrentHashMap.newKeySet<String>()

    override fun observeAll(): Flow<List<DownloadTask>> =
        workManager.getWorkInfosByTagFlow(TAG)
            .map { infos ->
                infos.map(::toTask)
                    .sortedByDescending { it.id }
                    .also { tasks -> tasks.forEach(::recordHistoryIfNeeded) }
            }

    /** 终态落史（v5.0.0：v3.2.8 add_history 语义——完成/失败/取消各一条，幂等）。 */
    private fun recordHistoryIfNeeded(task: DownloadTask) {
        val terminal = task.status == DownloadStatus.SUCCEEDED
                || task.status == DownloadStatus.FAILED
                || task.status == DownloadStatus.CANCELLED
        if (!terminal || !recordedIds.add(task.id)) return
        history.add(
            org.panboost.core.domain.DownloadHistoryEntry(
                ts = System.currentTimeMillis(),
                url = task.url,
                name = task.fileName,
                size = task.totalBytes,
                status = when (task.status) {
                    DownloadStatus.SUCCEEDED -> "完成"
                    DownloadStatus.FAILED -> "失败"
                    else -> "已取消"
                },
                speed = lastSpeeds.remove(task.id) ?: 0L,
            )
        )
        appLog.info(
            "history",
            "${task.fileName.take(40)} → ${when (task.status) {
                DownloadStatus.SUCCEEDED -> "完成"
                DownloadStatus.FAILED -> "失败"
                else -> "取消"
            }}"
        )
    }

    private val lastSpeeds = java.util.concurrent.ConcurrentHashMap<String, Long>()

    override fun cancel(taskId: String) {
        workManager.cancelUniqueWork(uniqueName(taskId))
    }

    override fun retry(task: DownloadTask) {
        // v5.3.3：重试重建原任务（此前误用 MockDownloadWorker——
        // "点击重试后自动变成模拟下载"的根因）
        val request = if (task.url.startsWith("mock://")) {
            mockRequest(task)
        } else {
            urlRequest(task)
        }
        workManager.enqueueUniqueWork(
            uniqueName(task.id),
            ExistingWorkPolicy.REPLACE,
            request,
        )
    }

    private fun toTask(info: WorkInfo): DownloadTask {
        val fileName = info.outputData.getString(MockDownloadWorker.KEY_FILE_NAME)
            ?: info.progress.getString(MockDownloadWorker.KEY_FILE_NAME)
            ?: "panboost.bin"
        val total = maxOf(
            info.outputData.getLong(MockDownloadWorker.KEY_TOTAL, 0L),
            info.progress.getLong(MockDownloadWorker.KEY_TOTAL, 0L),
        ).let { if (it > 0) it else MockDownloadWorker.DEFAULT_TOTAL }
        val bytes = info.progress.getLong(MockDownloadWorker.KEY_BYTES, 0L)
        val speed = info.progress.getLong(
            MultiThreadDownloadWorker.KEY_SPEED, 0L
        )
        if (speed > 0) lastSpeeds[info.id.toString()] = speed
        val status = when (info.state) {
            WorkInfo.State.ENQUEUED -> DownloadStatus.QUEUED
            WorkInfo.State.RUNNING -> DownloadStatus.RUNNING
            WorkInfo.State.SUCCEEDED -> DownloadStatus.SUCCEEDED
            WorkInfo.State.FAILED -> DownloadStatus.FAILED
            WorkInfo.State.CANCELLED -> DownloadStatus.CANCELLED
            WorkInfo.State.BLOCKED -> DownloadStatus.QUEUED
        }
        return DownloadTask(
            id = info.id.toString(),
            url = "mock://$fileName",
            fileName = fileName,
            mimeType = "application/octet-stream",
            totalBytes = total,
            downloadedBytes = if (status == DownloadStatus.SUCCEEDED) total else bytes,
            status = status,
            progress = if (total > 0) bytes.toFloat() / total else 0f,
            speedBps = speed,
        )
    }

    private fun uniqueName(id: String) = "download-$id"

    /** 线程选择解析（v5.1.0："auto"→0 哨兵；数字 clamp [1,1024]）。 */
    private fun parseThreads(choice: String): Int = when {
        choice.equals("auto", ignoreCase = true) ->
            MultiThreadDownloadWorker.AUTO_THREADS
        else -> (choice.toIntOrNull() ?: MultiThreadDownloadWorker.DEFAULT_THREADS)
            .coerceIn(1, MultiThreadDownloadWorker.MAX_THREADS)
    }

    companion object {
        private const val TAG = "panboost-download"
        private const val BACKOFF_SECONDS = 10L
    }
}
