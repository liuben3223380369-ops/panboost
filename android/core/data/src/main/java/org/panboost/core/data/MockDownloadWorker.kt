package org.panboost.core.data

import android.content.Context
import androidx.hilt.work.HiltWorker
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject
import kotlinx.coroutines.delay
import kotlin.random.Random

/**
 * 模拟下载 Worker（第 2 周验收载体）。
 *
 * 生成分块随机数据写入 MediaStoreDownloadsWriter（5MB / 100KB
 * 块 / 块间 100ms ≈ 5 秒完成——真机可肉眼验收"MediaStore 中出现
 * 完整文件"）；进度经 setProgress 上报（WorkInfo.progress 驱动
 * observeAll 实时刷新，第 3 周 MVI 的数据源）。
 *
 * 取消语义：isStopped → abort() 清理半成品（pending 行删除/
 * 旧机型文件删除）→ Result.failure（状态映射为 CANCELLED）。
 * 第 4 周接 Retrofit 后本类保留结构、换真实分块 GET。
 */
@HiltWorker
class MockDownloadWorker @AssistedInject constructor(
    @Assisted context: Context,
    @Assisted params: WorkerParameters,
    private val writer: MediaStoreDownloadsWriter,
) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        val fileName = inputData.getString(KEY_FILE_NAME) ?: "panboost.bin"
        val mime = inputData.getString(KEY_MIME) ?: "application/octet-stream"
        val total = inputData.getLong(KEY_TOTAL, DEFAULT_TOTAL)
        val output = writer.create(fileName, mime)
        val chunk = ByteArray(CHUNK_BYTES)
        var written = 0L
        try {
            while (written < total) {
                if (isStopped) {
                    output.abort()
                    return Result.failure()
                }
                val len = minOf(chunk.size.toLong(), total - written).toInt()
                Random.nextBytes(chunk)
                output.stream.write(chunk, 0, len)
                output.stream.flush()
                written += len
                setProgress(
                    androidx.work.workDataOf(
                        KEY_BYTES to written,
                        KEY_TOTAL to total,
                    )
                )
                delay(DELAY_MS)
            }
            output.finish()
        } catch (e: Exception) {
            output.abort()
            return Result.failure()
        }
        return Result.success(
            androidx.work.workDataOf(
                KEY_BYTES to written,
                KEY_TOTAL to total,
            )
        )
    }

    companion object {
        const val KEY_FILE_NAME = "file_name"
        const val KEY_MIME = "mime"
        const val KEY_TOTAL = "total"
        const val KEY_BYTES = "bytes"

        const val DEFAULT_TOTAL = 5L * 1024 * 1024
        private const val CHUNK_BYTES = 100 * 1024
        private const val DELAY_MS = 100L
    }
}
