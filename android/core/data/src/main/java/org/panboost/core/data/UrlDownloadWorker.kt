package org.panboost.core.data

import android.content.Context
import androidx.hilt.work.HiltWorker
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject
import okhttp3.OkHttpClient
import okhttp3.Request
import org.panboost.core.network.QuarkApi
import java.util.concurrent.TimeUnit

/**
 * 真实下载 Worker（第 4 周：OkHttp 流式）。
 *
 * 完整链路的下载端：HomeViewModel 取直链 → enqueue → 本 Worker
 * OkHttp GET（夸克直链校验 Referer——头与 API 客户端同策略）→
 * 流式写 MediaStoreDownloadsWriter（100KB 缓冲）→ setProgress
 * 实时上报 → finish 发布（文件管理器即刻可见）。
 *
 * Kivy 引擎的多线程分块/断点续传（panboost.py 的核心竞争力）
 * 迁移计划：第 5 周清理后在 Worker 内以 Range 分块 + 多协程
 * 并发重建（MediaStore 流式写的分块 Seek 兼容性届时验证；
 * 本周先保链路完整——单流对媒体文件已是可用下载）。
 */
@HiltWorker
class UrlDownloadWorker @AssistedInject constructor(
    @Assisted context: Context,
    @Assisted params: WorkerParameters,
    private val writer: MediaStoreDownloadsWriter,
) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        val url = inputData.getString(KEY_URL) ?: return Result.failure()
        val fileName = inputData.getString(KEY_FILE_NAME) ?: "panboost.bin"
        val mime = inputData.getString(KEY_MIME) ?: "application/octet-stream"
        val referer = inputData.getString(KEY_REFERER) ?: QuarkApi.REFERER

        // 下载直链走独立客户端（同头策略；API 客户端的 Cookie 对
        // 直链域非必需且可能过期干扰，直链仅校验 Referer）
        val client = OkHttpClient.Builder()
            .connectTimeout(20, TimeUnit.SECONDS)
            .readTimeout(60, TimeUnit.SECONDS)
            .build()
        val request = Request.Builder()
            .url(url)
            .header("Referer", referer)
            .header("User-Agent", QuarkApi.CLIENT_UA)
            .build()

        val response = try {
            client.newCall(request).execute()
        } catch (e: Exception) {
            return Result.failure()
        }
        response.use { resp ->
            if (!resp.isSuccessful) return Result.failure()
            val body = resp.body ?: return Result.failure()
            val total = body.contentLength()
            val output = writer.create(fileName, mime)
            val buf = ByteArray(BUF)
            var written = 0L
            try {
                body.byteStream().use { input ->
                    while (true) {
                        if (isStopped) {
                            output.abort()
                            return Result.failure()
                        }
                        val n = input.read(buf)
                        if (n < 0) break
                        output.stream.write(buf, 0, n)
                        written += n
                        if (total > 0) {
                            setProgress(
                                androidx.work.workDataOf(
                                    MockDownloadWorker.KEY_BYTES to written,
                                    MockDownloadWorker.KEY_TOTAL to total,
                                )
                            )
                        }
                    }
                }
                output.finish()
            } catch (e: Exception) {
                output.abort()
                return Result.failure()
            }
            return Result.success(
                androidx.work.workDataOf(
                    MockDownloadWorker.KEY_BYTES to written,
                    MockDownloadWorker.KEY_TOTAL to if (total > 0) total else written,
                )
            )
        }
    }

    companion object {
        const val KEY_URL = "url"
        const val KEY_REFERER = "referer"
        private const val BUF = 100 * 1024
    }
}
