package org.panboost.feature.download

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.stateIn
import org.panboost.core.domain.DownloadRepository
import org.panboost.core.domain.DownloadStatus
import org.panboost.core.domain.DownloadTask
import java.util.UUID
import javax.inject.Inject

/**
 * 下载屏 ViewModel（第 3 周 MVI）。
 *
 * 单一 UiState 流 + 单一 onIntent 入口：
 * - 进度实时刷新：observeAll（WorkManager 状态流）→ map(UiState)
 *   → stateIn——Worker 的 setProgress 每次上报驱动整条链
 * - 无重复排队（验收）：StartMockDownload 意图在"同名任务仍在
 *   排队/运行"时静默忽略——仓库层 uniqueWork KEEP 是同 id 兜底，
 *   这里是用户可见语义层（快速连点只产生一个任务）；不同文件
 *   名任务可并行
 * - 取消/重试：直通仓库（取消由 Worker isStopped→abort 清半成品；
 *   重试 REPLACE 顶替旧任务）
 */
@HiltViewModel
class DownloadViewModel @Inject constructor(
    private val downloadRepository: DownloadRepository,
) : ViewModel() {

    private val _urlInput = MutableStateFlow("")

    val uiState: StateFlow<DownloadUiState> =
        kotlinx.coroutines.flow.combine(
            downloadRepository.observeAll(),
            _urlInput,
        ) { tasks, url -> DownloadUiState(tasks = tasks, urlInput = url) }
            .stateIn(
                scope = viewModelScope,
                started = SharingStarted.WhileSubscribed(5_000),
                initialValue = DownloadUiState(),
            )

    fun onIntent(intent: DownloadIntent) {
        when (intent) {
            DownloadIntent.StartMockDownload -> startMockDownload()
            DownloadIntent.StartUrlDownload -> startUrlDownload()
            is DownloadIntent.UrlChanged -> _urlInput.value = intent.url
            is DownloadIntent.Cancel -> downloadRepository.cancel(intent.taskId)
            is DownloadIntent.Retry -> downloadRepository.retry(intent.taskId)
        }
    }

    /** URL 直链下载（v5.0.0：v3.2.8「高级下载」回补）。 */
    private fun startUrlDownload() {
        val url = _urlInput.value.trim()
        if (!url.startsWith("http")) return
        downloadRepository.enqueue(
            DownloadTask(
                id = UUID.randomUUID().toString(),
                url = url,
                fileName = url.substringAfterLast('/').substringBefore('?')
                    .ifEmpty { "panboost_${url.hashCode().toUInt()}.bin" },
                mimeType = "application/octet-stream",
                totalBytes = 0L,
            )
        )
        _urlInput.value = ""
    }

    private fun startMockDownload() {
        val name = MOCK_FILE_NAME
        val active = uiState.value.tasks.any {
            it.fileName == name &&
                    (it.status == DownloadStatus.QUEUED
                            || it.status == DownloadStatus.RUNNING)
        }
        if (active) {
            // 无重复排队：同名任务在途，忽略本次点击
            return
        }
        downloadRepository.enqueue(
            DownloadTask(
                id = UUID.randomUUID().toString(),
                url = "mock://$name",
                fileName = name,
                mimeType = "application/octet-stream",
                totalBytes = MOCK_TOTAL_BYTES,
            )
        )
    }

    companion object {
        private const val MOCK_FILE_NAME = "panboost_模拟下载.bin"
        private const val MOCK_TOTAL_BYTES = 5L * 1024 * 1024
    }
}
