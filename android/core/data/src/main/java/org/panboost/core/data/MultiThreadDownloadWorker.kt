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
import kotlinx.coroutines.delay
import okhttp3.OkHttpClient
import okhttp3.Request
import org.panboost.core.logging.AppLog
import org.panboost.core.network.PersonaInterceptor
import org.panboost.core.network.QuarkApi
import java.io.File
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicLong

/**
 * 多线程分块下载 Worker（v5.1.0：v3.2.8 引擎同构块模型）。
 *
 * 引擎规格对齐（panboost.py MultiThreadDownloader）：
 * - **线程 512 默认 / 1024 上限**（BLOCKS_PER_WORKER=8：任务被
 *   分成 threads×8 块，块大小 clamp [512KB, 64MB]——小文件自动
 *   降块数，不硬拆 25KB 碎片）
 * - **auto 线程**：>64MB 时探针实测（单连接 vs 16 并发吞吐比，
 *   上限 512）——v3.2.8 auto_tune 语义
 * - **防风控**：UA 池轮换（403 换 UA 重试一次）+ 块间随机抖动
 *   0~40ms（避免完美等间隔请求打点）+ PersonaInterceptor 全局
 *   拟人化头（Accept-Encoding: identity 等）
 * - 断点续传：块粒度 part 文件（重跑跳过已完成块）
 * - 前台服务 dataSync（Android 14+ 长时下载规范）
 */
@HiltWorker
class MultiThreadDownloadWorker @AssistedInject constructor(
    @Assisted private val appContext: Context,
    @Assisted params: WorkerParameters,
    private val writer: MediaStoreDownloadsWriter,
    private val appLog: AppLog,
    private val accounts: org.panboost.core.domain.AccountRepository,
) : CoroutineWorker(appContext, params) {

    override suspend fun getForegroundInfo(): ForegroundInfo =
        createForegroundInfo(0, 0)

    /** 失败结果带 fileName（v5.3.2：历史记录不再回退 panboost.bin）。 */
    private fun fail(fileName: String): Result = Result.failure(
        androidx.work.workDataOf(MockDownloadWorker.KEY_FILE_NAME to fileName)
    )

    override suspend fun doWork(): Result {
        val url = inputData.getString(KEY_URL) ?: return Result.failure()
        val fileName = inputData.getString(MockDownloadWorker.KEY_FILE_NAME)
            ?: "panboost.bin"
        val mime = inputData.getString(MockDownloadWorker.KEY_MIME)
            ?: "application/octet-stream"
        val referer = inputData.getString(KEY_REFERER) ?: QuarkApi.REFERER
        val threadsChoice = inputData.getInt(KEY_THREADS, DEFAULT_THREADS)
        // v5.3.3：直链请求带 Cookie（夸克直链校验 __puus 签名——
        // 真机实锤 HTTP 412 的根因：此前只带 Referer/UA）
        val dlCookie = runCatching {
            val cm = android.webkit.CookieManager.getInstance()
            listOf("https://pan.quark.cn", "https://quark.cn")
                .mapNotNull { cm.getCookie(it) }
                .joinToString("; ")
        }.getOrDefault("")

        setForeground(createForegroundInfo(0, 0))
        appLog.info("download", "开始：${fileName.take(40)}（${threadsChoice} 线程）")
        // v5.3.2：进度首报带 fileName（历史/下载屏实时拿名，不再默认名）
        setProgress(
            androidx.work.workDataOf(
                MockDownloadWorker.KEY_FILE_NAME to fileName,
                MockDownloadWorker.KEY_TOTAL to 0L,
            )
        )

        val speedTracker = SpeedTracker()

        // v5.1.0：1024 并发前置（Dispatcher/连接池）
        val client = OkHttpClient.Builder()
            .connectTimeout(20, TimeUnit.SECONDS)
            .readTimeout(60, TimeUnit.SECONDS)
            .dispatcher(okhttp3.Dispatcher().apply {
                maxRequests = MAX_THREADS
                maxRequestsPerHost = MAX_THREADS
            })
            .connectionPool(okhttp3.ConnectionPool(MAX_THREADS, 30, TimeUnit.SECONDS))
            .build()

        // v5.3.2：探测（HEAD 被拒 → GET Range 探测 → 全失败降级单流）
        val probe = probeRange(client, url, referer, dlCookie)
        if (probe == null) {
            appLog.warn(
                "download",
                "HEAD/Range 探测均失败（CDN 拒绝探测）——降级单流 GET：$fileName",
            )
            return downloadSingleStream(
                client, url, fileName, mime, referer, dlCookie, speedTracker,
            )
        }
        if (!probe.rangeOk || probe.total <= 0) {
            return downloadSingleStream(
                client, url, fileName, mime, referer, dlCookie, speedTracker,
            )
        }
        val total = probe.total

        // ---- auto 线程（v3.2.8 auto_tune：>64MB 实测） ----
        val threads = if (threadsChoice == AUTO_THREADS) {
            if (total > AUTO_TUNE_MIN_BYTES) {
                val tuned = autoTune(client, url, referer, total)
                appLog.info("download", "auto 实测选定线程数: $tuned")
                tuned
            } else {
                SMALL_FILE_THREADS
            }
        } else {
            threadsChoice.coerceIn(1, MAX_THREADS)
        }

        // ---- 块模型（v5.5.0 速度优化：目标 ~256 大块 [2MB, 8MB]） ----
        // 512KB 小块×1070 块 = 每块请求/TLS 开销占比过高（真机速度慢
        // 主因）；2-8MB 大块把请求数砍 4-16 倍，单连接吞吐更高
        val block = (total / TARGET_BLOCKS).coerceIn(MIN_PIECE, MAX_PIECE)
        val nblocks = ((total + block - 1) / block).toInt()
        // v5.5.0：慢启动并发——16 起步每 8 块爬升 ×1.5 至 MAX_CONCURRENT
        // (128)，412/403 退避时砍半（风控自适应）；worker 协程固定启动
        // MAX_CONCURRENT 个，靠 livePermits 排队门控实际并发
        val workers = threads.coerceAtMost(nblocks).coerceAtMost(MAX_CONCURRENT)
        val livePermits = java.util.concurrent.atomic.AtomicInteger(SLOW_START)
        appLog.info("download", "慢启动：${SLOW_START} 并发起步（爬升上限 $MAX_CONCURRENT）")
        val dir = File(appContext.cacheDir, "parts_${id}")
        dir.mkdirs()

        appLog.info(
            "download",
            "$fileName：$threads 线程 / $nblocks 块（${block / 1024}KB/块）",
        )

        val cursor = AtomicInteger(0)
        val doneBytes = AtomicLong(0)

        try {
            coroutineScope {
                (0 until workers).map { rank ->
                    async(Dispatchers.IO) {
                        downloadLoop(
                            client, url, referer, dlCookie, total, block, nblocks,
                            dir, cursor, doneBytes, speedTracker, livePermits, rank,
                        )
                    }
                }.awaitAll()
            }
            if (isStopped) {
                dir.deleteRecursively()
                return fail(fileName)
            }

            reportProgress(doneBytes.get(), total, speedTracker.rate())
            appLog.info(
                "download",
                "全块完成：$nblocks 块 / 最终并发 ${livePermits.get()}",
            )

            // ---- 合并（块顺序拼接） ----
            val output = writer.create(fileName, mime)
            try {
                var merged = 0L
                for (i in 0 until nblocks) {
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
            appLog.info(
                "download",
                "完成：$fileName（${fmt(speedTracker.rate())}/s，$threads 线程）",
            )
            return Result.success(
                androidx.work.workDataOf(
                    MockDownloadWorker.KEY_BYTES to total,
                    MockDownloadWorker.KEY_TOTAL to total,
                    KEY_SPEED to speedTracker.rate(),
                )
            )
        } catch (e: Exception) {
            if (isStopped) dir.deleteRecursively()
            appLog.error("download", "失败：$fileName——${e.message?.take(60)}")
            return fail(fileName)
        }
    }

    /** worker 主循环：取块 → 下载（断点跳过/403 换 UA/抖动）。 */
    private suspend fun downloadLoop(
        client: OkHttpClient,
        url: String,
        referer: String,
        dlCookie: String,
        total: Long,
        block: Long,
        nblocks: Int,
        dir: File,
        cursor: AtomicInteger,
        doneBytes: AtomicLong,
        speedTracker: SpeedTracker,
        livePermits: AtomicInteger,
        workerRank: Int,
    ) {
        val lastReport = AtomicLong(0)
        while (!isStopped) {
            // v5.5.0 慢启动门控：worker 序号 < 当前配额才干活；配额爬升后
            // 后排 worker 自动加入，砍半时后排自动暂停
            var gate = 0
            while (!isStopped && workerRank >= livePermits.get()) {
                if (++gate % 40 == 0) {  // ~2s 提示一次（50ms×40）
                    appLog.info("download", "并发配额 ${livePermits.get()}，worker#$workerRank 排队中")
                }
                delay(50)
            }
            if (isStopped) return
            val i = cursor.getAndIncrement()
            if (i >= nblocks) return
            val start = i.toLong() * block
            val endExclusive = minOf(start + block, total)
            val partFile = File(dir, "part$i")
            if (partFile.length() == endExclusive - start) {
                doneBytes.addAndGet(endExclusive - start)
                continue
            }
            fetchBlock(
                client, url, referer, dlCookie,
                start, endExclusive, partFile, livePermits, appLog,
            )
            doneBytes.addAndGet(partFile.length())
            speedTracker.add(partFile.length())
            // v5.5.0：爬升并发（每块完成 +1，到上限停）——慢启动核心
            livePermits.updateAndGet { cur ->
                if (cur < MAX_CONCURRENT) cur + 1 else cur
            }
            // v5.5.0：进度节流（setProgress 是 WorkManager IPC，每块一报
            // ×上千块是隐性大头）——≥400ms 才上报
            val now = System.currentTimeMillis()
            if (now - lastReport.get() >= REPORT_INTERVAL_MS) {
                lastReport.set(now)
                reportProgress(doneBytes.get(), total, speedTracker.rate())
            }
            // 块间随机抖动（防风控：避免完美等间隔请求）
            delay(JITTER_MS.random())
        }
    }

    /**
     * 单块 Range 请求（v5.5.0）。
     *
     * - Cookie 全量携带（直链校验签名）
     * - 412/403/429：砍并发配额（减半不低于 SLOW_START）+ 换 UA +
     *   指数退避（1s/3s），2 次重试后仍失败抛出
     */
    private fun fetchBlock(
        client: OkHttpClient,
        url: String,
        referer: String,
        dlCookie: String,
        start: Long,
        endExclusive: Long,
        partFile: File,
        livePermits: AtomicInteger? = null,
        appLog: AppLog? = null,
    ) {
        var ua = QuarkApi.CLIENT_UA
        val backoffs = longArrayOf(1_000, 3_000)
        for (attempt in 0 until 3) {
            try {
                val request = Request.Builder()
                    .url(url)
                    .header("Referer", referer)
                    .header("User-Agent", ua)
                    .header("Range", "bytes=$start-${endExclusive - 1}")
                    .apply { if (dlCookie.isNotBlank()) header("Cookie", dlCookie) }
                    .build()
                var retryableCode = 0
                val ok = client.newCall(request).execute().use { resp ->
                    when {
                        resp.code in RETRYABLE_CODES && attempt < 2 -> {
                            retryableCode = resp.code
                            false
                        }
                        !resp.isSuccessful -> throw IllegalStateException(
                            "块请求失败 HTTP ${resp.code}"
                        )
                        else -> {
                            val body = resp.body
                                ?: throw IllegalStateException("块响应空")
                            partFile.outputStream().use { out ->
                                body.byteStream().use { input ->
                                    input.copyTo(out, COPY_BUF)
                                }
                            }
                            true
                        }
                    }
                }
                if (ok) return
                // v6.0.0：UA 固定不轮换（OpenList/quark-auto-save 双实锤
                // ——真客户端 UA 恒定，轮换恰是机器人指纹）
                // v5.5.0：风控码先砍配额（减半，不低于 SLOW_START）
                livePermits?.updateAndGet { cur ->
                    (cur / 2).coerceAtLeast(SLOW_START)
                }
                appLog?.warn(
                    "download",
                    "HTTP $retryableCode 退避：并发砍至 ${livePermits?.get()}",
                )
                Thread.sleep(backoffs[attempt])
            } catch (e: Exception) {
                if (attempt == 2) throw e
                try {
                    Thread.sleep(backoffs[attempt])
                } catch (_: InterruptedException) {
                    Thread.currentThread().interrupt()
                    throw e
                }
            }
        }
    }

    /** 进度上报（字节 + 速率）。 */
    private suspend fun reportProgress(done: Long, total: Long, speed: Long) {
        setProgress(
            androidx.work.workDataOf(
                MockDownloadWorker.KEY_BYTES to done,
                MockDownloadWorker.KEY_TOTAL to total,
                KEY_SPEED to speed,
            )
        )
    }

    /** auto 线程探针（v3.2.8 auto_tune：单连接 vs 16 并发吞吐比）。 */
    private fun autoTune(
        client: OkHttpClient,
        url: String,
        referer: String,
        total: Long,
    ): Int {
        return try {
            val v1 = probeSpeed(client, url, referer, 1, 2_000, total)
            val v16 = probeSpeed(client, url, referer, 16, 2_500, total)
            if (v1 <= 0 || v16 <= 0) {
                DEFAULT_THREADS
            } else {
                (v16 / v1).toInt().coerceIn(SMALL_FILE_THREADS, AUTO_MAX_THREADS)
            }
        } catch (_: Exception) {
            DEFAULT_THREADS
        }
    }

    /** 并发探针：n 个连接各读 ms 毫秒，返回合计 B/s。 */
    private fun probeSpeed(
        client: OkHttpClient,
        url: String,
        referer: String,
        n: Int,
        ms: Long,
        total: Long,
    ): Long {
        val bytes = AtomicLong(0)
        val threads = (0 until n).map { i ->
            Thread {
                try {
                    val start = (i.toLong() * 4 * 1024 * 1024) % total
                    val request = Request.Builder()
                        .url(url)
                        .header("Referer", referer)
                        .header("User-Agent", QuarkApi.CLIENT_UA)
                        .header("Range", "bytes=$start-${start + 4 * 1024 * 1024 - 1}")
                        .build()
                    client.newCall(request).execute().use { resp ->
                        if (resp.isSuccessful) {
                            val buf = ByteArray(64 * 1024)
                            resp.body?.byteStream()?.use { input ->
                                val deadline = System.currentTimeMillis() + ms
                                while (System.currentTimeMillis() < deadline) {
                                    val rd = input.read(buf)
                                    if (rd < 0) break
                                    bytes.addAndGet(rd.toLong())
                                }
                            }
                        }
                    }
                } catch (_: Exception) {
                }
            }
        }
        threads.forEach { it.start() }
        threads.forEach { it.join(ms + 3_000) }
        return bytes.get() * 1000 / ms
    }

    /**
     * 探测：total + Range 支持（v5.3.2 双重探测）。
     *
     * 真机日志实锤：夸克 CDN 直链拒绝 HEAD（探测直接失败 → 整任务
     * 失败）。修复：HEAD 失败后用 GET Range: bytes=0-0 探测——
     * Content-Range: bytes 0-0/TOTAL 给出真实总长；两者都失败由
     * 调用方降级单流（contentLength 兜底），下载永不因探测而死。
     */
    private fun probeRange(
        client: OkHttpClient,
        url: String,
        referer: String,
        dlCookie: String,
    ): ProbeInfo? {
        // 1. HEAD 探测
        try {
            val request = Request.Builder()
                .url(url)
                .head()
                .header("Referer", referer)
                .header("User-Agent", QuarkApi.CLIENT_UA)
                .apply { if (dlCookie.isNotBlank()) header("Cookie", dlCookie) }
                .build()
            client.newCall(request).execute().use { resp ->
                if (resp.isSuccessful) {
                    val total = resp.header("Content-Length")?.toLongOrNull() ?: -1L
                    val rangeOk = resp.header("Accept-Ranges")?.contains("bytes") == true
                    if (total > 0) return ProbeInfo(total, rangeOk)
                }
            }
        } catch (_: Exception) {
        }
        // 2. GET Range 探测（bytes=0-0，读 Content-Range）
        try {
            val request = Request.Builder()
                .url(url)
                .header("Referer", referer)
                .header("User-Agent", QuarkApi.CLIENT_UA)
                .header("Range", "bytes=0-0")
                .apply { if (dlCookie.isNotBlank()) header("Cookie", dlCookie) }
                .build()
            client.newCall(request).execute().use { resp ->
                if (resp.isSuccessful || resp.code == 206) {
                    // Content-Range: bytes 0-0/1234567
                    val cr = resp.header("Content-Range")
                    val total = cr?.substringAfterLast("/")?.toLongOrNull() ?: -1L
                    val rangeOk = resp.code == 206 || cr != null
                    if (total > 0) return ProbeInfo(total, rangeOk)
                    // 200 全量响应：Content-Length 即总长
                    val cl = resp.header("Content-Length")?.toLongOrNull() ?: -1L
                    if (cl > 0) return ProbeInfo(cl, false)
                }
            }
        } catch (_: Exception) {
        }
        return null
    }

    /** 服务器不支持 Range 的降级单流。 */
    private suspend fun downloadSingleStream(
        client: OkHttpClient,
        url: String,
        fileName: String,
        mime: String,
        referer: String,
        dlCookie: String,
        speedTracker: SpeedTracker?,
    ): Result {
        val request = Request.Builder()
            .url(url)
            .header("Referer", referer)
            .header("User-Agent", QuarkApi.CLIENT_UA)
            .apply { if (dlCookie.isNotBlank()) header("Cookie", dlCookie) }
            .build()
        val response = try {
            client.newCall(request).execute()
        } catch (e: Exception) {
            appLog.error("download", "单流请求异常：$fileName——${e.message?.take(60)}")
            return fail(fileName)
        }
        response.use { resp ->
            if (!resp.isSuccessful) {
                appLog.error("download", "单流 HTTP ${resp.code}：$fileName")
                return fail(fileName)
            }
            val body = resp.body ?: return fail(fileName)
            val total = body.contentLength()
            val output = writer.create(fileName, mime)
            val buf = ByteArray(COPY_BUF)
            var written = 0L
            try {
                body.byteStream().use { input ->
                    while (true) {
                        if (isStopped) {
                            output.abort()
                            return fail(fileName)
                        }
                        val n = input.read(buf)
                        if (n < 0) break
                        output.stream.write(buf, 0, n)
                        written += n
                        speedTracker?.add(n.toLong())
                        if (total > 0) {
                            reportProgress(written, total, speedTracker?.rate() ?: 0L)
                        }
                    }
                }
                output.finish()
                appLog.info("download", "完成（单流）：$fileName")
                return Result.success(
                    androidx.work.workDataOf(
                        MockDownloadWorker.KEY_FILE_NAME to fileName,
                        MockDownloadWorker.KEY_BYTES to written,
                        MockDownloadWorker.KEY_TOTAL to if (total > 0) total else written,
                        KEY_SPEED to (speedTracker?.rate() ?: 0L),
                    )
                )
            } catch (e: Exception) {
                output.abort()
                return Result.failure()
            }
        }
    }

    // ---- 前台通知 ----

    private fun createForegroundInfo(done: Long, total: Long): ForegroundInfo {
        val nm = appContext.getSystemService(Context.NOTIFICATION_SERVICE)
            as NotificationManager
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            nm.createNotificationChannel(
                NotificationChannel(
                    CHANNEL_ID, "下载任务",
                    NotificationManager.IMPORTANCE_LOW,
                )
            )
        }
        val text = if (total > 0) "$done/$total 字节" else "正在下载"
        val notification: Notification =
            NotificationCompat.Builder(appContext, CHANNEL_ID)
                .setContentTitle("PanBoost 下载中")
                .setContentText(text)
                .setSmallIcon(android.R.drawable.stat_sys_download)
                .setOngoing(true)
                .setOnlyAlertOnce(true)
                .build()
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            ForegroundInfo(
                NOTIF_ID, notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC,
            )
        } else {
            ForegroundInfo(NOTIF_ID, notification)
        }
    }

    /** 滑动窗口速率（v5.0.0）。 */
    private class SpeedTracker {
        private val samples = ArrayDeque<Pair<Long, Long>>(16)

        fun add(deltaBytes: Long) {
            synchronized(samples) {
                val now = System.currentTimeMillis()
                val last = samples.lastOrNull()?.second ?: 0L
                samples.addLast(now to last + deltaBytes)
                while (samples.size > 16) samples.removeFirst()
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

    private fun fmt(bps: Long): String = when {
        bps >= 1024 * 1024 -> "%.1fMB".format(bps / 1024f / 1024f)
        bps >= 1024 -> "%dKB".format(bps / 1024)
        else -> "${bps}B"
    }

    private data class ProbeInfo(val total: Long, val rangeOk: Boolean)

    companion object {
        const val KEY_URL = "url"
        const val KEY_REFERER = "referer"
        const val KEY_THREADS = "threads"
        const val KEY_SPEED = "speed"

        /** auto 哨兵（UI 选择器 "auto"）。 */
        const val AUTO_THREADS = 0

        /** v5.1.0：默认 512（用户要求对齐 v3.2.8 的 512/1024 档）。 */
        const val DEFAULT_THREADS = 512
        const val MAX_THREADS = 1024
        const val SMALL_FILE_THREADS = 16
        const val AUTO_MAX_THREADS = 512

        // v3.2.8 引擎块模型常量
        const val BLOCKS_PER_WORKER = 8
        const val MIN_PIECE = 2L * 1024 * 1024
        // v6.0.0：对齐 OpenList PartSize=10MB
        const val MAX_PIECE = 10L * 1024 * 1024
        const val AUTO_TUNE_MIN_BYTES = 64L * 1024 * 1024

        // v5.4.2：可退避错误码（412 预条件/403 风控/429 限流）
        val RETRYABLE_CODES = setOf(412, 403, 429)

        // v6.0.0：并发收敛 8——OpenList(25217★) quark_uc 驱动实战
        // Concurrency=3 跑满（CDN 单流限速高；高并发纯触发 412 退避
        // 实际吞吐反而暴跌）；慢启动 4 起步爬升至 8
        const val MAX_CONCURRENT = 8
        const val SLOW_START = 4

        // v5.5.0：大块模型（目标 256 块，块 2~8MB）
        const val TARGET_BLOCKS = 256

        // v5.5.0：进度上报节流（WorkManager IPC 隐性开销）
        const val REPORT_INTERVAL_MS = 400L

        private val JITTER_MS = 0L..40L
        private const val CHANNEL_ID = "panboost_download"
        private const val NOTIF_ID = 1001
        private const val COPY_BUF = 100 * 1024
    }
}
