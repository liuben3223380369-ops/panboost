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
 * - 进度：WorkInfo.progress.bytes → DownloadTask.downloadedBytes
 *   （observeAll 的 Flow 由 WorkManager 状态流驱动，实时刷新）
 * - 持久化：WorkManager 自带队列持久化（进程死亡/重启后续跑），
 *   Kivy 时代"下载列表靠内存"的结构性缺陷就此消除
 */
@Singleton
class DownloadRepositoryImpl @Inject constructor(
    @ApplicationContext private val context: Context,
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

    /** 真实下载（第 4 周链路：URL 直链 + Referer 流式写）。 */
    private fun urlRequest(task: DownloadTask): OneTimeWorkRequest =
        OneTimeWorkRequestBuilder<UrlDownloadWorker>()
            .setInputData(
                workDataOf(
                    UrlDownloadWorker.KEY_URL to task.url,
                    UrlDownloadWorker.KEY_REFERER to "https://pan.quark.cn/",
                    MockDownloadWorker.KEY_FILE_NAME to task.fileName,
                    MockDownloadWorker.KEY_MIME to task.mimeType,
                )
            )
            .addTag(TAG)
            .build()

    override fun observeAll(): Flow<List<DownloadTask>> =
        workManager.getWorkInfosByTagFlow(TAG)
            .map { infos -> infos.map(::toTask).sortedByDescending { it.id } }

    override fun cancel(taskId: String) {
        workManager.cancelUniqueWork(uniqueName(taskId))
    }

    override fun retry(taskId: String) {
        // REPLACE 语义：失败/取消任务被新请求顶替重新排队
        val request = OneTimeWorkRequestBuilder<MockDownloadWorker>()
            .setInputData(
                workDataOf(
                    MockDownloadWorker.KEY_FILE_NAME to "panboost_${taskId.take(8)}.bin",
                    MockDownloadWorker.KEY_MIME to "application/octet-stream",
                    MockDownloadWorker.KEY_TOTAL to MockDownloadWorker.DEFAULT_TOTAL,
                )
            )
            .addTag(TAG)
            .build()
        workManager.enqueueUniqueWork(
            uniqueName(taskId),
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
        )
    }

    private fun uniqueName(id: String) = "download-$id"

    companion object {
        private const val TAG = "panboost-download"
        private const val BACKOFF_SECONDS = 10L
    }
}
