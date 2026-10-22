package org.panboost.feature.share

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import org.panboost.core.domain.DownloadRepository
import org.panboost.core.domain.DownloadTask
import org.panboost.core.domain.ShareFile
import org.panboost.core.domain.ShareRepository
import java.util.UUID
import javax.inject.Inject

/**
 * 分享屏 ViewModel（v4.2.0：YunX 核心体验回补）。
 *
 * Parse：ShareRepository.resolve（夸克三步流）→ 文件列表整列
 * 替换（默认全不选——用户勾选后下载，v3.0.0 起的语义）。
 * DownloadSelected：逐文件 enqueue（DownloadTask 携带直链）→
 * snackbar 引导去下载页；进度/取消/重试由既有下载链承担。
 */
@HiltViewModel
class ShareViewModel @Inject constructor(
    private val shareRepository: ShareRepository,
    private val downloadRepository: DownloadRepository,
) : ViewModel() {

    private val _uiState = MutableStateFlow(ShareUiState())
    val uiState: StateFlow<ShareUiState> = _uiState.asStateFlow()

    fun onIntent(intent: ShareIntent) {
        when (intent) {
            is ShareIntent.UrlChanged -> _uiState.update { it.copy(shareUrl = intent.url) }
            is ShareIntent.PasscodeChanged -> _uiState.update { it.copy(passcode = intent.code) }
            ShareIntent.Parse -> parse()
            is ShareIntent.Toggle -> toggle(intent.file)
            ShareIntent.ToggleAll -> toggleAll()
            ShareIntent.DownloadSelected -> downloadSelected()
            ShareIntent.SnackbarShown -> _uiState.update { it.copy(snackbar = null) }
        }
    }

    /** 剪贴板识别（v4.2.0 P0#2）：填入不覆盖用户已输入。 */
    fun onClipboardShareUrl(url: String) {
        val cur = _uiState.value.shareUrl
        if (cur.isBlank() && url != cur) {
            _uiState.update { it.copy(shareUrl = url, snackbar = "已从剪贴板识别分享链接") }
        }
    }

    private fun parse() {
        val state = _uiState.value
        if (state.resolving || state.shareUrl.isBlank()) return
        _uiState.update { it.copy(resolving = true, files = emptyList(), selected = emptySet()) }
        viewModelScope.launch {
            try {
                val files = shareRepository.resolve(state.shareUrl, state.passcode)
                _uiState.update {
                    it.copy(resolving = false, files = files)
                }
            } catch (e: Exception) {
                _uiState.update {
                    it.copy(resolving = false, snackbar = "解析失败：${e.message?.take(80)}")
                }
            }
        }
    }

    private fun toggle(file: ShareFile) {
        _uiState.update {
            val next = it.selected.toMutableSet()
            if (!next.add(file.url)) next.remove(file.url)
            it.copy(selected = next)
        }
    }

    private fun toggleAll() {
        _uiState.update {
            if (it.allSelected) it.copy(selected = emptySet())
            else it.copy(selected = it.files.map(ShareFile::url).toSet())
        }
    }

    private fun downloadSelected() {
        val state = _uiState.value
        if (!state.canDownload) return
        val picked = state.files.filter { it.url in state.selected }
        picked.forEach { file ->
            downloadRepository.enqueue(
                DownloadTask(
                    id = UUID.randomUUID().toString(),
                    url = file.url,
                    fileName = file.name,
                    mimeType = guessMime(file.name),
                    totalBytes = file.size,
                )
            )
        }
        _uiState.update {
            it.copy(
                snackbar = "已发起 ${picked.size} 个下载——到「下载」页查看进度",
            )
        }
    }

    private fun guessMime(name: String): String = when {
        name.endsWith(".apk", true) -> "application/vnd.android.package-archive"
        name.endsWith(".mp4", true) -> "video/mp4"
        name.endsWith(".mp3", true) -> "audio/mpeg"
        name.endsWith(".zip", true) -> "application/zip"
        name.endsWith(".bin", true) -> "application/octet-stream"
        else -> "application/octet-stream"
    }
}
