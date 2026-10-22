package org.panboost.feature.logs

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import org.panboost.core.logging.AppLog
import javax.inject.Inject

/**
 * 日志屏 ViewModel（v5.0.0）。
 *
 * 1s 轮询环形缓冲快照（旧→新）——日志屏实时滚动。
 */
@HiltViewModel
class LogsViewModel @Inject constructor(
    private val appLog: AppLog,
) : ViewModel() {

    private val _entries = MutableStateFlow<List<AppLog.Entry>>(emptyList())
    val entries: StateFlow<List<AppLog.Entry>> = _entries.asStateFlow()

    init {
        viewModelScope.launch {
            while (isActive) {
                _entries.value = appLog.snapshot()
                delay(1_000)
            }
        }
    }
}
