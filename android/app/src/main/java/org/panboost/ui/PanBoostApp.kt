package org.panboost.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import org.panboost.core.domain.DownloadStatus
import org.panboost.core.domain.DownloadTask
import org.panboost.ui.theme.PanBoostTheme

/**
 * 第 2 周验收屏（临时，第 3 周换 :feature:download 正式屏）。
 *
 * 验收路径：点「模拟下载 5MB」→ WorkManager 排队 →
 * MockDownloadWorker 分块写 MediaStore → 进度条实时走满 →
 * 完成；系统文件管理器的 Download/PanBoost 出现完整 5MB 文件。
 */
@Composable
fun PanBoostApp(
    viewModel: VerificationViewModel = hiltViewModel(),
) {
    val tasks by viewModel.tasks.collectAsState()
    PanBoostAppContent(
        tasks = tasks,
        onStart = viewModel::startMockDownload,
        onCancel = viewModel::cancel,
        onRetry = viewModel::retry,
    )
}

@Composable
private fun PanBoostAppContent(
    tasks: List<DownloadTask>,
    onStart: () -> Unit,
    onCancel: (String) -> Unit,
    onRetry: (String) -> Unit,
) {
    Scaffold { innerPadding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(innerPadding)
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(
                text = "PanBoost",
                style = MaterialTheme.typography.displayMedium,
            )
            Text(
                text = "第 2 周验收：模拟下载 → MediaStore 可见完整文件（Download/PanBoost）",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Button(
                onClick = onStart,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text("模拟下载 5MB")
            }
            LazyColumn(
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                items(tasks, key = { it.id }) { task ->
                    TaskRow(
                        task = task,
                        onCancel = { onCancel(task.id) },
                        onRetry = { onRetry(task.id) },
                    )
                }
            }
        }
    }
}

@Composable
private fun TaskRow(
    task: DownloadTask,
    onCancel: () -> Unit,
    onRetry: () -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = task.fileName,
                style = MaterialTheme.typography.bodyMedium,
                modifier = Modifier.weight(1f, fill = false),
                maxLines = 1,
            )
            Text(
                text = when (task.status) {
                    DownloadStatus.QUEUED -> "排队中"
                    DownloadStatus.RUNNING -> "${task.downloadedBytes / 1024}KB / ${task.totalBytes / 1024}KB"
                    DownloadStatus.SUCCEEDED -> "完成"
                    DownloadStatus.FAILED -> "失败"
                    DownloadStatus.CANCELLED -> "已取消"
                },
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            when (task.status) {
                DownloadStatus.QUEUED, DownloadStatus.RUNNING ->
                    OutlinedButton(onClick = onCancel) { Text("取消") }
                DownloadStatus.FAILED, DownloadStatus.CANCELLED ->
                    OutlinedButton(onClick = onRetry) { Text("重试") }
                else -> {}
            }
        }
        LinearProgressIndicator(
            progress = { task.progress.coerceIn(0f, 1f) },
            modifier = Modifier.fillMaxWidth(),
        )
    }
}

@Preview(showBackground = true)
@Composable
private fun PanBoostAppPreview() {
    PanBoostTheme {
        PanBoostAppContent(
            tasks = listOf(
                DownloadTask(
                    id = "1",
                    url = "mock://a.bin",
                    fileName = "panboost_验收_1.bin",
                    mimeType = "application/octet-stream",
                    totalBytes = 5L * 1024 * 1024,
                    downloadedBytes = 2 * 1024 * 1024,
                    status = DownloadStatus.RUNNING,
                    progress = 0.4f,
                )
            ),
            onStart = {},
            onCancel = {},
            onRetry = {},
        )
    }
}
