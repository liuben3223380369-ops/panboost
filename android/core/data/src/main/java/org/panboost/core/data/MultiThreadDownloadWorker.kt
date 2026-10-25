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
        // v6.3.0：多直链并发（aria2 multi-URI 同款）——夸克 download API
        // 每次调用返回不同 CDN 节点直链，单链独立限速；N 条直链块轮询
        // 分布，总吞吐 = N × 单链速度
        val extraUrls = inputData.getStringArray(KEY_URLS).orEmpty()
        val urls = (listOf(url) + extraUrls).distinct()
        if (urls.size > 1) {
            appLog.info("download", "多直链模式：${urls.size} 条直链并发")
        }
        val fileName = inputData.getString(MockDownloadWorker.KEY_FILE_NAME)
            ?: "panboost.bin"
        val mime = inputData.getString(MockDownloadWorker.KEY_MIME)
            ?: "application/octet-stream"
        val threadsChoice = inputData.getInt(KEY_THREADS, DEFAULT_THREADS)
        // v6.2.0：网盘无关的下载上下文（根治三处写死夸克）——
        // panKey 经 DownloadTask 传入；URL 兜底反查（直链/历史重跑）
        val pan = panFor(inputData.getString(KEY_PAN), url)
        // Referer：catalog 登录页即各网盘主页域（夸克 pan.quark.cn/
        // UC drive.uc.cn/123 www.123pan.com——通用规则成立）
        val referer = pan?.loginUrl ?: inputData.getString(KEY_REFERER) ?: ""
        // Cookie：该网盘全部域 + 登录页 host 的 WebView 实时罐合并
        val dlCookie = panCookie(pan)
        // UA：夸克/UC 系（clouddrive API 家族）用官方客户端 UA，
        // 其余网盘用桌面浏览器 UA
        val dlUa = if (pan != null && pan.domains.any {
                it == "quark.cn" || it == "uc.cn"
            }) QuarkApi.CLIENT_UA else DESKTOP_UA
        appLog.info(
            "download",
            "上下文：${pan?.key ?: "直链（无网盘）"} cookie=${dlCookie.length}字",
        )

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
            // v6.1.1：10MB 大块 @ 慢速连接（200KB/s）≈50s+握手——
            // 60s 边缘超时会断块重拉（更亏）；120s 稳态兜底。
            // 注：OkHttp 对 CDN host 自动协商 HTTP/2（ALPN）——
            // 并发 8 在 h2 下是单连接多路复用流，连接风暴天然低。
            .readTimeout(120, TimeUnit.SECONDS)
            .dispatcher(okhttp3.Dispatcher().apply {
                maxRequests = MAX_THREADS
                maxRequestsPerHost = MAX_THREADS
            })
            .connectionPool(okhttp3.ConnectionPool(MAX_THREADS, 30, TimeUnit.SECONDS))
            .build()

        // v5.3.2：探测（HEAD 被拒 → GET Range 探测 → 全失败降级单流）
        val probe = probeRange(client, urls[0], referer, dlCookie, dlUa)
        if (probe == null) {
            appLog.warn(
                "download",
                "HEAD/Range 探测均失败（CDN 拒绝探测）——降级单流 GET：$fileName",
            )
            return downloadSingleStream(
                client, urls[0], fileName, mime, referer, dlCookie, dlUa, speedTracker,
            )
        }
        if (!probe.rangeOk || probe.total <= 0) {
            return downloadSingleStream(
                client, urls[0], fileName, mime, referer, dlCookie, dlUa, speedTracker,
            )
        }
        val total = probe.total

        // ---- auto 线程（v7.4.0：三档分档 + 阶梯探针） ----
        // ≤4MB→8（小文件开多了浪费）；≤64MB→32（经验中档）；
        // >64MB→阶梯探针（1/8/64/512 找吞吐拐点，在线自适应）
        val threads = if (threadsChoice == AUTO_THREADS) {
            when {
                total <= AUTO_SMALL_FILE_BYTES -> AUTO_TINY_THREADS
                total <= AUTO_TUNE_MIN_BYTES -> AUTO_MID_THREADS
                else -> {
                    val tuned = autoTune(client, url, referer, dlUa, total)
                    appLog.info("download", "auto 实测选定线程数: $tuned")
                    tuned
                }
            }
        } else {
            threadsChoice.coerceIn(1, MAX_THREADS)
        }

        // ---- 块模型（v6.5.0：回归 v3.2.8 引擎规格——threads×8 块，
        // 512KB~64MB 自适应；1024 线程时 512MB 文件=8192 块/每线程 8 块） ----
        val block = (total / (threads.toLong() * BLOCKS_PER_WORKER))
            .coerceIn(MIN_PIECE, MAX_PIECE)
        val nblocks = ((total + block - 1) / block).toInt()
        // v6.5.0：用户主权——选多少线程开多少 worker（上限 MAX_THREADS
        // 1024；v6.4.0 的 coerceAtMost(32) 是对用户选择的背叛）。
        // 慢启动/退避砍配额/慢链黑名单作为保护层保留（起步 SLOW_START
        // 爬升至所选值，412/403 自动收缩——保护而非限制）
        val workers = threads.coerceAtMost(nblocks)
        val livePermits = java.util.concurrent.atomic.AtomicInteger(SLOW_START)
        appLog.info(
            "download",
            "慢启动：${SLOW_START} 并发起步（爬升至所选 $workers）",
        )
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
                            client, urls, referer, dlCookie, dlUa, workers, total, block, nblocks,
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
            // v7.3.0：完成通知（点击跳 App——前台通知被取消后用户仍可
            // 从通知回到 App 查看下载屏；P3#16）
            notifyDone(fileName, total)
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
        urls: List<String>,
        referer: String,
        dlCookie: String,
        dlUa: String,
        maxWorkers: Int,
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
        val lastLog = AtomicLong(0)
        // v6.4.0：慢链黑名单（aria2 lowest-speed-limit 等价——
        // Server Performance Profile 轻量版）
        val slowLinks = java.util.concurrent.ConcurrentHashMap.newKeySet<Int>()
        while (!isStopped) {
            // v5.5.0 慢启动门控：worker 序号 < 当前配额才干活；配额爬升后
            // 后排 worker 自动加入，砍半时后排自动暂停
            var gate = 0
            var lastLoggedPermit = -1
            while (!isStopped && workerRank >= livePermits.get()) {
                // v6.2.1：只在配额变化时记一次（去刷屏）
                val permitNow = livePermits.get()
                if (permitNow != lastLoggedPermit) {
                    lastLoggedPermit = permitNow
                    appLog.info(
                        "download",
                        "并发 $permitNow（worker#$workerRank 排队）",
                    )
                }
                gate++
                delay(50)
            }
            if (isStopped) return
            val i = cursor.getAndIncrement()
            if (i >= nblocks) return
            // v6.3.0：块轮询分布到多条直链（每链独立限速）
            // v6.4.0：aria2 --uri-selector=feedback 等价——慢链黑名单
            // 顺延（块级实测慢的链跳过，选下一链）
            var linkIdx = i % urls.size.coerceAtLeast(1)
            if (urls.size > 1 && linkIdx in slowLinks) {
                linkIdx = (linkIdx + 1) % urls.size
                if (linkIdx in slowLinks) {
                    linkIdx = (linkIdx + 1) % urls.size
                }
            }
            val blockUrl = urls[linkIdx]
            val start = i.toLong() * block
            val endExclusive = minOf(start + block, total)
            val partFile = File(dir, "part$i")
            if (partFile.length() == endExclusive - start) {
                doneBytes.addAndGet(endExclusive - start)
                continue
            }
            val t0 = System.currentTimeMillis()
            fetchBlock(
                client, blockUrl, referer, dlCookie,
                start, endExclusive, partFile, dlUa, livePermits, appLog,
            )
            // v6.4.0：块级链速实测（aria2 feedback 数据源）——
            // <64KB/s 持续 2MB 块的链进黑名单（真实低限速而非慢启动抖动）
            val dt = System.currentTimeMillis() - t0
            if (dt > 0 && urls.size > 1) {
                val bps = (endExclusive - start) * 1000 / dt
                if (bps < SLOW_LINK_BPS) {
                    if (slowLinks.add(linkIdx)) {
                        appLog.info("download", "慢链 #$linkIdx 进黑名单（${bps / 1024}KB/s）——后续块跳过")
                    }
                }
            }
            doneBytes.addAndGet(partFile.length())
            speedTracker.add(partFile.length())
            // v5.5.0：爬升并发（每块完成 +1，到上限停）——慢启动核心
            livePermits.updateAndGet { cur ->
                if (cur < maxWorkers) cur + 1 else cur
            }
            // v5.5.0：进度节流（setProgress 是 WorkManager IPC，每块一报
            // ×上千块是隐性大头）——≥400ms 才上报
            val now = System.currentTimeMillis()
            if (now - lastReport.get() >= REPORT_INTERVAL_MS) {
                lastReport.set(now)
                reportProgress(doneBytes.get(), total, speedTracker.rate())
            }
            // v6.2.1：5s 周期进度日志（速度/百分比/并发）
            if (now - lastLog.get() >= PROGRESS_LOG_MS) {
                lastLog.set(now)
                val done = doneBytes.get()
                val pct = if (total > 0) done * 100 / total else 0
                appLog.info(
                    "download",
                    "进度 $pct%（${done / 1024 / 1024}/${total / 1024 / 1024}MB）" +
                            " ${fmt(speedTracker.rate())}/s 并发${livePermits.get()}",
                )
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
        dlUa: String,
        livePermits: AtomicInteger? = null,
        appLog: AppLog? = null,
    ) {
        var ua = dlUa
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

    /**
     * auto 线程探针（v7.4.0：阶梯探测找吞吐拐点）。
     *
     * v3.2.8 旧探针 ratio=v16/v1 恒 ≤16（物理上限），coerceIn(16,512)
     * 永远命中下限——探针形同虚设。v7.4.0 改阶梯：测 1/8/64/512
     * 并发吞吐，找增益比 <1.5（饱和拐点）的档位，选该档为线程数。
     */
    private fun autoTune(
        client: OkHttpClient,
        url: String,
        referer: String,
        dlUa: String,
        total: Long,
    ): Int {
        return try {
            val ms = 2_000L
            val v1 = probeSpeed(client, url, referer, dlUa, 1, ms, total)
            val v8 = probeSpeed(client, url, referer, dlUa, 8, ms, total)
            val v64 = probeSpeed(client, url, referer, dlUa, 64, ms, total)
            val v512 = probeSpeed(client, url, referer, dlUa, 512, ms, total)
            appLog.info(
                "download",
                "auto 探针：v1=${v1 / 1024}KB/s v8=${v8 / 1024}KB/s " +
                    "v64=${v64 / 1024}KB/s v512=${v512 / 1024}KB/s",
            )
            if (v1 <= 0) return DEFAULT_THREADS
            val steps = listOf(8 to v8, 64 to v64, 512 to v512)
            var chosen = 8
            var prevBps = v1
            for ((n, bps) in steps) {
                if (bps <= 0) break
                val gain = bps.toDouble() / prevBps
                appLog.info("download", "auto 探针：$n 并发增益 x${"%.2f".format(gain)}")
                if (gain < AUTO_TUNE_GAIN_THRESHOLD) break
                chosen = n
                prevBps = bps
            }
            chosen.coerceIn(SMALL_FILE_THREADS, MAX_THREADS)
        } catch (_: Exception) {
            DEFAULT_THREADS
        }
    }

    /** 并发探针：n 个连接各读 ms 毫秒，返回合计 B/s。 */
    private fun probeSpeed(
        client: OkHttpClient,
        url: String,
        referer: String,
        dlUa: String,
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
                        .header("User-Agent", dlUa)
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
        dlUa: String,
    ): ProbeInfo? {
        // 1. HEAD 探测
        try {
            val request = Request.Builder()
                .url(url)
                .head()
                .header("Referer", referer)
                .header("User-Agent", dlUa)
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
                .header("User-Agent", dlUa)
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
        dlUa: String,
        speedTracker: SpeedTracker?,
    ): Result {
        val request = Request.Builder()
            .url(url)
            .header("Referer", referer)
            .header("User-Agent", dlUa)
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

    // ---- 通知（v7.3.0：点按跳转 + 完成通知）----

    /**
     * 主界面跳转 PendingIntent（通知点按）。
     *
     * v7.3.0：包管理器取启动 Intent（getLaunchIntentForPackage）——
     * data 层无法引用 app 层 MainActivity（依赖方向：app→data），
     * 包名启动 Intent 零类引用同效果（系统定位 launcher Activity）。
     */
    private fun mainPendingIntent(): android.app.PendingIntent? {
        return try {
            val intent = appContext.packageManager
                .getLaunchIntentForPackage(appContext.packageName)
                ?: return null
            intent.flags = (
                android.content.Intent.FLAG_ACTIVITY_NEW_TASK
                    or android.content.Intent.FLAG_ACTIVITY_SINGLE_TOP
                )
            android.app.PendingIntent.getActivity(
                appContext, 0, intent,
                (
                    android.app.PendingIntent.FLAG_IMMUTABLE
                        or android.app.PendingIntent.FLAG_UPDATE_CURRENT
                    ),
            )
        } catch (_: Exception) {
            null
        }
    }

    /** 完成通知（前台服务停止后仍可见；点按跳 App）。 */
    private fun notifyDone(fileName: String, total: Long) {
        try {
            val nm = appContext.getSystemService(Context.NOTIFICATION_SERVICE)
                as NotificationManager
            val text = if (total > 0) {
                "已完成 ${fmt(total)} —— 点击查看"
            } else {
                "下载完成 —— 点击查看"
            }
            val n = NotificationCompat.Builder(appContext, CHANNEL_ID)
                .setContentTitle("✓ $fileName")
                .setContentText(text)
                .setSmallIcon(android.R.drawable.stat_sys_download_done)
                .setAutoCancel(true)
                .setContentIntent(mainPendingIntent())
                .build()
            nm.notify(DONE_NOTIF_BASE + id.hashCode() % 1000, n)
        } catch (_: Exception) {
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
                // v7.3.0：点通知跳 App（ROADMAP P3#16）
                .setContentIntent(mainPendingIntent())
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

    // ---- v6.2.0：网盘无关下载上下文 ----

    /** panKey 直查 + URL 域反查兜底。 */
    private fun panFor(panKey: String?, url: String) =
        org.panboost.core.domain.PanCatalog.byKey(panKey ?: "")
            ?: org.panboost.core.domain.PanCatalog.byShareUrl(url)
            ?: kotlin.run {
                val host = try {
                    java.net.URI(url).host.orEmpty()
                } catch (_: Exception) {
                    ""
                }
                if (host.isEmpty()) null
                else org.panboost.core.domain.PanCatalog.all.firstOrNull { pan ->
                    pan.domains.any { host == it || host.endsWith(".$it") }
                }
            }

    /** 该网盘全部域 + 登录页 host 的实时 Cookie 合并（登录态完整）。 */
    private fun panCookie(pan: org.panboost.core.domain.PanInfo?): String {
        if (pan == null) return ""
        return runCatching {
            val cm = android.webkit.CookieManager.getInstance()
            val hosts = pan.domains + pan.loginUrl
                .removePrefix("https://").removePrefix("http://")
                .substringBefore("/")
            val kv = linkedMapOf<String, String>()
            for (h in hosts.filter { it.isNotBlank() }.distinct()) {
                val raw = try {
                    cm.getCookie("https://$h")
                } catch (_: Exception) {
                    null
                } ?: continue
                for (c in raw.split(";")) {
                    val k = c.substringBefore("=").trim()
                    val v = c.substringAfter("=").trim()
                    if (k.isNotEmpty() && v.isNotEmpty()) kv[k] = v
                }
            }
            kv.entries.joinToString("; ") { "${it.key}=${it.value}" }
        }.getOrDefault("")
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
        const val KEY_PAN = "pan"
        const val KEY_URLS = "urls"
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
        const val MIN_PIECE = 512L * 1024
        // v6.0.0：对齐 OpenList PartSize=10MB
        const val MAX_PIECE = 64L * 1024 * 1024
        const val AUTO_TUNE_MIN_BYTES = 64L * 1024 * 1024
        // v7.4.0：auto 三档分档阈值与线程数
        const val AUTO_SMALL_FILE_BYTES = 4L * 1024 * 1024
        const val AUTO_TINY_THREADS = 8
        const val AUTO_MID_THREADS = 32
        const val AUTO_TUNE_GAIN_THRESHOLD = 1.5

        // v5.4.2：可退避错误码（412 预条件/403 风控/429 限流）
        val RETRYABLE_CODES = setOf(412, 403, 429)

        // v6.0.0：并发收敛 8——OpenList(25217★) quark_uc 驱动实战
        // Concurrency=3 跑满（CDN 单流限速高；高并发纯触发 412 退避
        // 实际吞吐反而暴跌）；慢启动 4 起步爬升至 8
        const val SLOW_START = 16


        // v6.4.0：慢链阈值（aria2 lowest-speed-limit 等价）
        const val SLOW_LINK_BPS = 64L * 1024

        // v5.5.0：进度上报节流（WorkManager IPC 隐性开销）
        const val REPORT_INTERVAL_MS = 400L

        // v6.2.1：进度日志周期
        const val PROGRESS_LOG_MS = 5_000L

        private val JITTER_MS = 0L..40L

        /** 非夸克系网盘的下载 UA（标准桌面浏览器）。 */
        const val DESKTOP_UA =
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        private const val CHANNEL_ID = "panboost_download"
        private const val NOTIF_ID = 1001
        private const val DONE_NOTIF_BASE = 2000
        private const val COPY_BUF = 100 * 1024
    }
}
