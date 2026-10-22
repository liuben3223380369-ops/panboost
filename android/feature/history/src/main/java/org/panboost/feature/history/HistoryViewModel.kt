package org.panboost.feature.history

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import org.panboost.core.domain.DownloadHistoryEntry
import org.panboost.core.domain.DownloadHistoryList
import org.panboost.core.domain.DownloadHistoryRepository
import org.panboost.core.domain.DownloadRepository
import org.panboost.core.domain.DownloadTask
import java.util.UUID
import javax.inject.Inject

/**
 * 历史屏 ViewModel（v5.0.0）。
 *
 * 历史直通车（store 流）；清空/开关/失败重跑（重新 enqueue
 * 同 URL——v3.2.8 失败重跑语义）。
 */
@HiltViewModel
class HistoryViewModel @Inject constructor(
    historyRepository: DownloadHistoryRepository,
    private val downloadRepository: DownloadRepository,
) : ViewModel() {

    val uiState: StateFlow<DownloadHistoryList> =
        historyRepository.observeAll()
            .stateIn(
                scope = viewModelScope,
                started = SharingStarted.WhileSubscribed(5_000),
                initialValue = DownloadHistoryList(),
            )

    private val history = historyRepository

    fun clear() = history.clear()

    fun setEnabled(enabled: Boolean) = history.setEnabled(enabled)

    /** 失败/取消条目重新入队（v3.2.8 失败重跑；v5.3.3 带完整参数）。 */
    fun retry(entry: DownloadHistoryEntry) {
        downloadRepository.enqueue(
            DownloadTask(
                id = UUID.randomUUID().toString(),
                url = entry.url,
                fileName = entry.name,
                mimeType = guessMime(entry.name),
                totalBytes = entry.size,
                threadsChoice = "512",
            )
        )
        history.add(entry.copy(status = "重跑", ts = System.currentTimeMillis()))
    }

    private fun guessMime(name: String): String = when {
        name.endsWith(".apk", true) -> "application/vnd.android.package-archive"
        name.endsWith(".mp4", true) -> "video/mp4"
        name.endsWith(".mp3", true) -> "audio/mpeg"
        name.endsWith(".zip", true) -> "application/zip"
        else -> "application/octet-stream"
    }
}
