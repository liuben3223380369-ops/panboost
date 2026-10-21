package org.panboost.feature.download

import org.panboost.core.domain.DownloadStatus
import org.panboost.core.domain.DownloadTask

/**
 * 下载屏单一 UiState（第 3 周 MVI）。
 *
 * 不可变 data class：ViewModel 内 stateIn 派生，UI collectAsState
 * 渲染——任何变化都经新 List 传播（Composable 逐项 diff）。
 * activeCount 供"开始下载"按钮的防重复文案（第 3 周验收：
 * 无重复排队）。
 */
data class DownloadUiState(
    val tasks: List<DownloadTask> = emptyList(),
) {
    val activeCount: Int
        get() = tasks.count {
            it.status == DownloadStatus.QUEUED || it.status == DownloadStatus.RUNNING
        }

    val hasTasks: Boolean
        get() = tasks.isNotEmpty()
}
