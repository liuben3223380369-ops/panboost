package org.panboost.core.domain

import kotlinx.coroutines.flow.Flow

/**
 * 下载历史条目（v5.0.0：v3.2.8 history.json 原生等价）。
 */
data class DownloadHistoryEntry(
    val ts: Long,
    val url: String,
    val name: String,
    val size: Long,
    val status: String,
    val speed: Long,
)

/**
 * 下载历史仓库（v5.0.0）。
 *
 * 实现于 :core:data（JSON 文件持久化）。语义对齐 v3.2.8：
 * - enabled 开关（关闭后不记录，下载照常）
 * - 上限 200 条（新条目插队头，超出裁尾）
 * - observeAll：历史屏实时流
 */
interface DownloadHistoryRepository {
    fun observeAll(): Flow<DownloadHistoryList>
    fun add(entry: DownloadHistoryEntry)
    fun clear()
    fun setEnabled(enabled: Boolean)
}

data class DownloadHistoryList(
    val enabled: Boolean = true,
    val items: List<DownloadHistoryEntry> = emptyList(),
)
