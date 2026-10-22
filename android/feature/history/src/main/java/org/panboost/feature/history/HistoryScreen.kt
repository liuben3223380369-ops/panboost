package org.panboost.feature.history

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import org.panboost.core.domain.DownloadHistoryEntry
import org.panboost.core.domain.DownloadHistoryList
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * 下载历史屏（v5.0.0：v3.2.8「历史」屏原生等价）。
 *
 * 永久记录（200 条）/记录开关/清空/失败重跑；
 * 条目显示：名称/大小/状态/速度/时间（v3.2.8 布局语义）。
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HistoryScreen(
    viewModel: HistoryViewModel = hiltViewModel(),
) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()
    HistoryScreenContent(
        uiState = uiState,
        onClear = viewModel::clear,
        onToggleEnabled = viewModel::setEnabled,
        onRetry = viewModel::retry,
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun HistoryScreenContent(
    uiState: DownloadHistoryList,
    onClear: () -> Unit,
    onToggleEnabled: (Boolean) -> Unit,
    onRetry: (DownloadHistoryEntry) -> Unit,
) {
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("下载历史（${uiState.items.size}）") },
                actions = {
                    TextButton(onClick = onClear) { Text("清空") }
                },
            )
        },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(horizontal = 12.dp),
        ) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(vertical = 8.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text("记录下载历史", style = MaterialTheme.typography.bodyMedium)
                Switch(checked = uiState.enabled, onCheckedChange = onToggleEnabled)
            }
            if (uiState.items.isEmpty()) {
                Text(
                    text = if (uiState.enabled) "暂无下载记录" else "记录已关闭（下载不受影响）",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(top = 24.dp),
                )
            }
            LazyColumn(
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                items(uiState.items, key = { "${it.ts}-${it.url}" }) { entry ->
                    HistoryCard(entry = entry, onRetry = { onRetry(entry) })
                }
            }
        }
    }
}

@Composable
private fun HistoryCard(entry: DownloadHistoryEntry, onRetry: () -> Unit) {
    Card(
        colors = CardDefaults.cardColors(
            containerColor = when (entry.status) {
                "完成" -> MaterialTheme.colorScheme.primaryContainer
                "失败", "已取消" -> MaterialTheme.colorScheme.errorContainer
                else -> MaterialTheme.colorScheme.surfaceVariant
            }
        ),
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            Text(
                text = entry.name,
                style = MaterialTheme.typography.bodyMedium,
                maxLines = 1,
            )
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = buildString {
                        append(entry.status)
                        append(" · ")
                        append(fmtSize(entry.size))
                        if (entry.speed > 0) {
                            append(" · ")
                            append(fmtSize(entry.speed))
                            append("/s")
                        }
                    },
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Text(
                    text = SimpleDateFormat("MM-dd HH:mm", Locale.US)
                        .format(Date(entry.ts)),
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            if (entry.status in setOf("失败", "已取消")) {
                AssistChip(onClick = onRetry, label = { Text("重跑") })
            }
        }
    }
}

internal fun fmtSize(bytes: Long): String = when {
    bytes >= 1024L * 1024 * 1024 -> "%.1fGB".format(bytes / 1024f / 1024f / 1024f)
    bytes >= 1024L * 1024 -> "%.1fMB".format(bytes / 1024f / 1024f)
    bytes >= 1024L -> "%dKB".format(bytes / 1024)
    else -> "${bytes}B"
}

@Preview(showBackground = true)
@Composable
private fun HistoryPreview() {
    MaterialTheme {
        HistoryScreenContent(
            uiState = DownloadHistoryList(
                items = listOf(
                    DownloadHistoryEntry(
                        System.currentTimeMillis() - 3600_000,
                        "https://dl.quark.cn/x", "电影.mp4",
                        2L * 1024 * 1024 * 1024, "完成", 25 * 1024 * 1024,
                    ),
                    DownloadHistoryEntry(
                        System.currentTimeMillis() - 600_000,
                        "https://dl.quark.cn/y", "文档.zip",
                        15L * 1024 * 1024, "失败", 0,
                    ),
                )
            ),
            onClear = {},
            onToggleEnabled = {},
            onRetry = {},
        )
    }
}
