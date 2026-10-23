package org.panboost.core.domain

/**
 * 下载任务领域模型（第 2 周）。
 *
 * 纯 Kotlin 无 Android 依赖：被 :core:data 的 WorkManager 实现
 * 映射，被 feature 层展示。id 全局唯一（UUID），url 第 2 周为
 * 模拟地址（mock://），第 4 周接 Retrofit 后为真实直链。
 */
data class DownloadTask(
    val id: String,
    val url: String,
    val fileName: String,
    val mimeType: String,
    val totalBytes: Long,
    val downloadedBytes: Long = 0L,
    val status: DownloadStatus = DownloadStatus.QUEUED,
    val progress: Float = 0f,
    /** 实时速率 B/s（v5.0.0：Worker 滑动窗口）。 */
    val speedBps: Long = 0L,
    /** 线程选择（v5.1.0：auto/8~1024，默认 512）。 */
    val threadsChoice: String = "512",
    /** 发起网盘（v6.2.0：Worker 按此查 PanCatalog 算 Cookie/Referer/UA）。 */
    val panKey: String = "",
)

/** 任务生命周期。 */
enum class DownloadStatus {
    QUEUED,
    RUNNING,
    SUCCEEDED,
    FAILED,
    CANCELLED,
}
