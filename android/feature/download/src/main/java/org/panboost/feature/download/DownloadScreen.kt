package org.panboost.feature.download

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import org.panboost.core.domain.DownloadStatus
import org.panboost.core.domain.DownloadTask

/**
 * 下载屏（第 3 周 MVI 正式屏）。
 *
 * 纯函数渲染：UiState → Compose；一切交互回调折叠为 Intent 交
 * ViewModel（UI 无业务分支）。进度条由 WorkManager 状态流驱动
 * 实时刷新；取消/重试按钮按任务状态显隐。
 */
@Composable
fun DownloadScreen(
    viewModel: DownloadViewModel = hiltViewModel(),
) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()
    DownloadScreenContent(
        uiState = uiState,
        onIntent = viewModel::onIntent,
    )
}

@Composable
internal fun DownloadScreenContent(
    uiState: DownloadUiState,
    onIntent: (DownloadIntent) -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(
            text = "下载",
            style = MaterialTheme.typography.headlineMedium,
        )
        Text(
            text = if (uiState.activeCount > 0) {
                "进行中 ${uiState.activeCount} 个任务——快速连点不会重复排队"
            } else {
                "模拟下载写入公共 Download（Download/PanBoost）"
            },
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        OutlinedTextField(
            value = uiState.urlInput,
            onValueChange = { onIntent(DownloadIntent.UrlChanged(it)) },
            label = { Text("粘贴下载直链（URL）开始多线程下载") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        Button(
            onClick = { onIntent(DownloadIntent.StartUrlDownload) },
            enabled = uiState.urlInput.startsWith("http"),
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text("开始下载")
        }
        Button(
            onClick = { onIntent(DownloadIntent.StartMockDownload) },
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(
                text = if (uiState.activeCount > 0) {
                    "模拟下载 5MB（${uiState.activeCount} 个进行中）"
                } else {
                    "模拟下载 5MB"
                }
            )
        }
        if (!uiState.hasTasks) {
            Text(
                text = "暂无下载任务",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(top = 24.dp),
            )
        }
        LazyColumn(
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            items(uiState.tasks, key = { it.id }) { task ->
                TaskCard(
                    task = task,
                    onCancel = { onIntent(DownloadIntent.Cancel(task.id)) },
                    onRetry = { onIntent(DownloadIntent.Retry(task.id)) },
                )
            }
        }
    }
}

@Composable
private fun TaskCard(
    task: DownloadTask,
    onCancel: () -> Unit,
    onRetry: () -> Unit,
) {
    Card(
        colors = CardDefaults.cardColors(
            containerColor = when (task.status) {
                DownloadStatus.SUCCEEDED ->
                    MaterialTheme.colorScheme.primaryContainer
                DownloadStatus.FAILED, DownloadStatus.CANCELLED ->
                    MaterialTheme.colorScheme.errorContainer
                else -> MaterialTheme.colorScheme.surfaceVariant
            }
        ),
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = task.fileName,
                        style = MaterialTheme.typography.bodyMedium,
                        maxLines = 1,
                    )
                    Text(
                        text = statusLine(task),
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                when (task.status) {
                    DownloadStatus.QUEUED, DownloadStatus.RUNNING ->
                        OutlinedButton(onClick = onCancel) { Text("取消") }
                    DownloadStatus.FAILED, DownloadStatus.CANCELLED ->
                        OutlinedButton(onClick = onRetry) { Text("重试") }
                    else -> {}
                }
            }
            if (task.status == DownloadStatus.RUNNING
                || (task.status == DownloadStatus.SUCCEEDED && task.totalBytes > 0)
            ) {
                LinearProgressIndicator(
                    progress = { task.progress.coerceIn(0f, 1f) },
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        }
    }
}

private fun statusLine(task: DownloadTask): String = when (task.status) {
    DownloadStatus.QUEUED -> "排队中"
    DownloadStatus.RUNNING ->
        "${fmt(task.downloadedBytes)} / ${fmt(task.totalBytes)} · ${fmt(task.speedBps)}/s"
    DownloadStatus.SUCCEEDED -> "完成 · ${fmt(task.totalBytes)}"
    DownloadStatus.FAILED -> "失败"
    DownloadStatus.CANCELLED -> "已取消"
}

private fun fmt(bytes: Long): String = when {
    bytes >= 1024 * 1024 -> "%.1fMB".format(bytes / 1024f / 1024f)
    bytes >= 1024 -> "%dKB".format(bytes / 1024)
    else -> "${bytes}B"
}

@Preview(showBackground = true)
@Composable
private fun DownloadScreenPreview() {
    MaterialTheme {
        DownloadScreenContent(
            uiState = DownloadUiState(
                tasks = listOf(
                    DownloadTask(
                        id = "1",
                        url = "mock://a.bin",
                        fileName = "panboost_模拟下载.bin",
                        mimeType = "application/octet-stream",
                        totalBytes = 5L * 1024 * 1024,
                        downloadedBytes = 2 * 1024 * 1024,
                        status = DownloadStatus.RUNNING,
                        progress = 0.4f,
                    ),
                    DownloadTask(
                        id = "2",
                        url = "mock://b.bin",
                        fileName = "panboost_完成样例.bin",
                        mimeType = "application/octet-stream",
                        totalBytes = 5L * 1024 * 1024,
                        downloadedBytes = 5L * 1024 * 1024,
                        status = DownloadStatus.SUCCEEDED,
                        progress = 1f,
                    ),
                )
            ),
            onIntent = {},
        )
    }
}
