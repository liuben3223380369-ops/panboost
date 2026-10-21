package org.panboost.feature.download

/**
 * 下载屏用户意图（第 3 周 MVI）。
 *
 * UI 不直接碰仓库——一切交互折叠为 Intent 交 ViewModel 单入口
 * onIntent 分发（可追踪/可测试，UI 无业务分支）。
 */
sealed interface DownloadIntent {
    /** 新建一个模拟下载任务（第 4 周接真实 URL 直链）。 */
    data object StartMockDownload : DownloadIntent

    /** 取消排队/运行中的任务（运行中半成品由 Worker abort 清理）。 */
    data class Cancel(val taskId: String) : DownloadIntent

    /** 重试失败/已取消的任务（REPLACE 语义重新排队）。 */
    data class Retry(val taskId: String) : DownloadIntent
}
