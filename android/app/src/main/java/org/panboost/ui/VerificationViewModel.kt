package org.panboost.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import org.panboost.core.domain.DownloadRepository
import org.panboost.core.domain.DownloadTask
import java.util.UUID
import javax.inject.Inject

/**
 * 第 2 周验收 ViewModel（临时载体，第 3 周由 :feature:download
 * 的正式 MVI DownloadViewModel 替代）。
 *
 * 单一 StateFlow（MVI 雏形）：observeAll 仓库流直通 UI；
 * 每次点击生成新 id 的新任务（KEEP 语义防的是同 id 重复排队）。
 */
@HiltViewModel
class VerificationViewModel @Inject constructor(
    private val downloadRepository: DownloadRepository,
) : ViewModel() {

    val tasks: StateFlow<List<DownloadTask>> = downloadRepository.observeAll()
        .stateIn(
            scope = viewModelScope,
            started = SharingStarted.WhileSubscribed(5_000),
            initialValue = emptyList(),
        )

    fun startMockDownload() {
        downloadRepository.enqueue(
            DownloadTask(
                id = UUID.randomUUID().toString(),
                url = "mock://week2.bin",
                fileName = "panboost_第2周验收_${(0..999).random()}.bin",
                mimeType = "application/octet-stream",
                totalBytes = 5L * 1024 * 1024,
            )
        )
    }

    fun cancel(taskId: String) = downloadRepository.cancel(taskId)

    fun retry(taskId: String) = downloadRepository.retry(taskId)
}
