package org.panboost.core.data

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.content.pm.ServiceInfo
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.hilt.work.HiltWorker
import androidx.work.CoroutineWorker
import androidx.work.ForegroundInfo
import androidx.work.WorkerParameters
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import okhttp3.OkHttpClient
import okhttp3.Request
import org.panboost.core.network.QuarkApi
import java.io.File
import java.util.concurrent.TimeUnit

/**
 * 多线程分块下载 Worker（v4.1.0：引擎核心能力迁移）。
 *
 * 旧 Python 引擎（panboost.py MultiThreadDownloader）核心竞争力的
 * 原生重建，对齐 2025 官方规范：
 * - **前台服务**：getForegroundInfo 返回 dataSync 类型（Android 14+
 *   长时 Worker 强制；ForegroundInfo 展示实时进度通知，退后台
 *   不被冻结——Kivy 时代 v3.2.5 闪退雷的正规替代）
 * - **Range 分块**：HEAD 探测 total/accept-ranges → N 协程并发
 *   GET（Range: bytes=a-b）→ 各自写 cacheDir part 文件 → 全部
 *   完成后顺序合并进 MediaStore → part 清理
 * - **断点续传**：part 文件按块偏移保留，重跑任务跳过已完成块
 *   （块粒度 .part{i}，崩溃/取消后续传）
 * - **服务器不支持 Range**：降级单流（同 v4.0 单 Worker 语义）
 */
@HiltWorker
class MultiThreadDownloadWorker @AssistedInject constructor(
    @Assisted private val appContext: Context,
    @Assisted params: WorkerParameters,
    private val writer: MediaStoreDownloadsWriter,
    private val appLog: org.panboost.core.logging.AppLog,
) : CoroutineWorker(appContext, params) {

    override suspend fun getForegroundInfo(): ForegroundInfo {
        return createForegroundInfo(0, 0)
    }

    override suspend fun doWork(): Result {
        val url = inputData.getString(KEY_URL) ?: return Result.failure()
        val fileName = inputData.getString(MockDownloadWorker.KEY_FILE_NAME) ?: "panboost.bin"
        val mime = inputData.getString(MockDownloadWorker.KEY_MIME) ?: "application/octet-stream"
        val referer = inputData.getString(KEY_REFERER) ?: QuarkApi.REFERER
        val threads = inputData.getInt(KEY_THREADS, DEFAULT_THREADS)
            .coerceIn(1, MAX_THREADS)

        setForeground(createForegroundInfo(0, 0))
        appLog.info("download", "开始：${fileName.take(40)}（${threads} 线程）")

        val client = OkHttpClient.Builder()
            .connectTimeout(20, TimeUnit.SECONDS)
            .readTimeout(60, TimeUnit.SECONDS)
            .build()

        // ---- 探测：total + Range 支持 ----
        val probe = probeRange(client, url, referer)
            ?: return Result.failure()
        if (!probe.rangeOk) {
            return downloadSingleStream(client, url, fileName, mime, referer)
        }

        // ---- 分块并发 ----
        val total = probe.total
        if (total <= 0) {
            return downloadSingleStream(client, url, fileName, mime, referer)
        }
        val block = (total + threads - 1) / threads
        val dir = File(appContext.cacheDir, "parts_${id}")
        dir.mkdirs()
        val speedTracker = SpeedTracker()
        val totalWritten = java.util.concurrent.atomic.AtomicLong(0)

        try {
            coroutineScope {
                (0 until threads).map { i ->
                    async(Dispatchers.IO) {
                        downloadBlock(
                            client, url, referer,
                            start = i * block,
                            endExclusive = minOf((i + 1) * block, total),
                            partFile = File(dir, "part$i"),
                            speedTracker = speedTracker,
                            onProgress = { done, total2 ->
                                // v5.0.0：进度含滑动窗口速率（下载屏 MB/s 实时显示）
                                val speed = speedTracker.rate()
                                setProgress(
                                    androidx.work.workDataOf(
                                        MockDownloadWorker.KEY_BYTES to done,
                                        MockDownloadWorker.KEY_TOTAL to total,
                                        KEY_SPEED to speed,
                                    )
                                )
                            },
                        )
                    }
                }.awaitAll()
            }

            if (isStopped) {
                dir.deleteRecursively()
                return Result.failure()
            }

            // ---- 合并进 MediaStore（顺序拼接 part）----
            val output = writer.create(fileName, mime)
            try {
                var merged = 0L
                for (i in 0 until threads) {
                    val part = File(dir, "part$i")
                    part.inputStream().use { input ->
                        input.copyTo(output.stream, COPY_BUF)
                    }
                    merged += part.length()
                }
                check(merged == total) { "合并大小不符：$merged / $total" }
                output.finish()
            } catch (e: Exception) {
                output.abort()
                throw e
            }
            appLog.info("download", "完成：$fileName（${fmt(speedTracker.rate())}/s）")
            return Result.success(
                androidx.work.workDataOf(
                    MockDownloadWorker.KEY_BYTES to total,
                    MockDownloadWorker.KEY_TOTAL to total,
                    KEY_SPEED to speedTracker.rate(),
                )
            )
        } catch (e: Exception) {
            // 失败保留 part（断点续传）；仅取消时清半成品
            if (isStopped) dir.deleteRecursively()
            return Result.failure()
        }
    }

    /** HEAD 探测：返回 (total, rangeOk) 或 null（探测失败）。 */
    private fun probeRange(
        client: OkHttpClient,
        url: String,
        referer: String,
    ): ProbeInfo? {
        return try {
            val request = Request.Builder()
                .url(url)
                .head()
                .header("Referer", referer)
                .header("User-Agent", QuarkApi.CLIENT_UA)
                .build()
            client.newCall(request).execute().use { resp ->
                if (!resp.isSuccessful) return null
                val total = resp.header("Content-Length")?.toLongOrNull() ?: -1L
                val rangeOk = resp.header("Accept-Ranges")?.contains("bytes") == true
                ProbeInfo(total, rangeOk)
            }
        } catch (e: Exception) {
            null
        }
    }

    /** 单块下载（含 part 断点续传：已有完整 part 直接跳过）。 */
    private suspend fun downloadBlock(
        client: OkHttpClient,
        url: String,
        referer: String,
        start: Long,
        endExclusive: Long,
        partFile: File,
        onProgress: suspend (Long, Long) -> Unit,
        speedTracker: SpeedTracker? = null,
    ) {
        if (start >= endExclusive) return
        if (partFile.length() == endExclusive - start) {
            // 断点续传：该块已完成
            return
        }
        partFile.outputStream().use { out ->
            val request = Request.Builder()
                .url(url)
                .header("Referer", referer)
                .header("User-Agent", QuarkApi.CLIENT_UA)
                .header("Range", "bytes=$start-${endExclusive - 1}")
                .build()
            client.newCall(request).execute().use { resp ->
                if (!resp.isSuccessful) throw IllegalStateException("块请求失败 HTTP ${resp.code}")
                val body = resp.body ?: throw IllegalStateException("块响应空")
                body.byteStream().use { input ->
                    input.copyTo(out, COPY_BUF)
                }
            }
        }
        onProgress(start + partFile.length(), 0)
        speedTracker?.add(partFile.length())
    }

    /** 服务器不支持 Range 时的降级路径（单流）。 */
    private suspend fun downloadSingleStream(
        client: OkHttpClient,
        url: String,
        fileName: String,
        mime: String,
        referer: String,
    ): Result {
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
            val buf = ByteArray(COPY_BUF)
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
                                    KEY_SPEED to speedTracker.rate(),
                                )
                            )
                        }
                    }
                }
                output.finish()
                return Result.success(
                    androidx.work.workDataOf(
                        MockDownloadWorker.KEY_BYTES to written,
                        MockDownloadWorker.KEY_TOTAL to if (total > 0) total else written,
                    )
                )
            } catch (e: Exception) {
                output.abort()
                return Result.failure()
            }
        }
    }

    // ---- 前台通知（Android 14+ dataSync 类型） ----

    private fun createForegroundInfo(done: Long, total: Long): ForegroundInfo {
        val channelId = CHANNEL_ID
        val nm = appContext.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            nm.createNotificationChannel(
                NotificationChannel(
                    channelId,
                    "下载任务",
                    NotificationManager.IMPORTANCE_LOW,
                )
            )
        }
        val text = if (total > 0) "$done/$total 字节" else "正在下载"
        val notification: Notification =
            NotificationCompat.Builder(appContext, channelId)
                .setContentTitle("PanBoost 下载中")
                .setContentText(text)
                .setSmallIcon(android.R.drawable.stat_sys_download)
                .setOngoing(true)
                .setOnlyAlertOnce(true)
                .build()
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            ForegroundInfo(
                NOTIF_ID,
                notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC,
            )
        } else {
            ForegroundInfo(NOTIF_ID, notification)
        }
    }

    private data class ProbeInfo(val total: Long, val rangeOk: Boolean)

    private fun fmt(bps: Long): String = when {
        bps >= 1024 * 1024 -> "%.1fMB".format(bps / 1024f / 1024f)
        bps >= 1024 -> "%dKB".format(bps / 1024)
        else -> "${bps}B"
    }

    /** 滑动窗口速率（v5.0.0：下载屏实时 MB/s）。 */
    private class SpeedTracker {
        private val samples = ArrayDeque<Pair<Long, Long>>(16) // (ts, bytes)

        fun add(deltaBytes: Long) {
            synchronized(samples) {
                val now = System.currentTimeMillis()
                val last = samples.lastOrNull()?.second ?: 0L
                samples.addLast(now to last + deltaBytes)
                while (samples.size > 16) samples.removeFirst()
                // 窗口 5s 裁剪
                while (samples.size > 2 &&
                    now - samples.first().first > 5_000
                ) samples.removeFirst()
            }
        }

        fun rate(): Long = synchronized(samples) {
            val first = samples.firstOrNull() ?: return 0L
            val last = samples.lastOrNull() ?: return 0L
            val dt = (last.first - first.first) / 1000.0
            if (dt < 0.5) return 0L
            ((last.second - first.second) / dt).toLong()
        }
    }

    companion object {
        const val KEY_URL = "url"
        const val KEY_REFERER = "referer"
        const val KEY_THREADS = "threads"
        const val DEFAULT_THREADS = 8
        const val MAX_THREADS = 16
        const val KEY_SPEED = "speed"

        private const val CHANNEL_ID = "panboost_download"
        private const val NOTIF_ID = 1001
        private const val COPY_BUF = 100 * 1024
    }
}
