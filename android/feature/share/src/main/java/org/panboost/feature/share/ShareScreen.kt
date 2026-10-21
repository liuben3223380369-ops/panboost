package org.panboost.feature.share

import android.content.ClipboardManager
import android.content.Context
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import org.panboost.core.domain.ShareFile

/**
 * 分享链接屏（v4.2.0：YunX 核心体验回补——v3.0.0 FilesScreen
 * 的原生等价物）。
 *
 * 粘贴分享链接（含提取码自动识别；剪贴板复制回来自动填入）
 * → 解析 → 勾选（单选/全选）→ 批量下载。下载进度/取消/重试
 * 在「下载」页（既有 MVI 链）。
 */
@Composable
fun ShareScreen(
    onOpenDownload: () -> Unit,
    viewModel: ShareViewModel = hiltViewModel(),
) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()
    val snackbarHostState = remember { SnackbarHostState() }
    val context = LocalContext.current

    // 剪贴板识别（P0#2）：进入屏时检测一次（不覆盖已输入）
    LaunchedEffect(Unit) {
        try {
            val cm = context.getSystemService(Context.CLIPBOARD_SERVICE)
                as ClipboardManager
            val text = cm.primaryClip?.getItemAt(0)?.text?.toString().orEmpty()
            if (Regex(QuarkShareUrlPattern).containsMatchIn(text) && text.length < 500) {
                viewModel.onClipboardShareUrl(text.trim())
            }
        } catch (_: Exception) {
        }
    }
    LaunchedEffect(uiState.snackbar) {
        uiState.snackbar?.let {
            snackbarHostState.showSnackbar(it)
            viewModel.onIntent(ShareIntent.SnackbarShown)
        }
    }
    ShareScreenContent(
        uiState = uiState,
        onIntent = viewModel::onIntent,
        onOpenDownload = onOpenDownload,
        snackbarHostState = snackbarHostState,
    )
}

private const val QuarkShareUrlPattern = "quark\\.cn/s/[A-Za-z0-9]+"

@Composable
internal fun ShareScreenContent(
    uiState: ShareUiState,
    onIntent: (ShareIntent) -> Unit,
    onOpenDownload: () -> Unit,
    snackbarHostState: SnackbarHostState,
) {
    Scaffold(
        topBar = { TopAppBar(title = { Text("分享链接下载") }) },
        snackbarHost = { SnackbarHost(snackbarHostState) },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            OutlinedTextField(
                value = uiState.shareUrl,
                onValueChange = { onIntent(ShareIntent.UrlChanged(it)) },
                label = { Text("分享链接（粘贴夸克分享链接）") },
                supportingText = { Text("提取码可写在链接里（?code=）或单独填写") },
                singleLine = false,
                maxLines = 3,
                modifier = Modifier.fillMaxWidth(),
            )
            Row(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                OutlinedTextField(
                    value = uiState.passcode,
                    onValueChange = { onIntent(ShareIntent.PasscodeChanged(it)) },
                    label = { Text("提取码（可选）") },
                    singleLine = true,
                    modifier = Modifier.weight(1f),
                )
                Button(
                    onClick = { onIntent(ShareIntent.Parse) },
                    enabled = !uiState.resolving && uiState.shareUrl.isNotBlank(),
                ) {
                    Text(if (uiState.resolving) "解析中…" else "解析")
                }
            }
            if (uiState.resolving) {
                CircularProgressIndicator(Modifier.padding(top = 32.dp))
            }
            if (uiState.files.isNotEmpty()) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        text = "共 ${uiState.files.size} 个文件",
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    FilterChip(
                        selected = uiState.allSelected,
                        onClick = { onIntent(ShareIntent.ToggleAll) },
                        label = { Text(if (uiState.allSelected) "全不选" else "全选") },
                    )
                }
                LazyColumn(
                    modifier = Modifier.weight(1f),
                    verticalArrangement = Arrangement.spacedBy(4.dp),
                ) {
                    items(uiState.files, key = { it.url }) { file ->
                        FileRow(
                            file = file,
                            checked = file.url in uiState.selected,
                            onToggle = { onIntent(ShareIntent.Toggle(file)) },
                        )
                        HorizontalDivider()
                    }
                }
                Button(
                    onClick = {
                        onIntent(ShareIntent.DownloadSelected)
                        onOpenDownload()
                    },
                    enabled = uiState.canDownload,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text(
                        if (uiState.selectedCount > 0) {
                            "下载所选（${uiState.selectedCount} 个文件）"
                        } else {
                            "勾选要下载的文件"
                        }
                    )
                }
            }
        }
    }
}

@Composable
private fun FileRow(
    file: ShareFile,
    checked: Boolean,
    onToggle: () -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Checkbox(checked = checked, onCheckedChange = { onToggle() })
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = file.name,
                style = MaterialTheme.typography.bodyMedium,
                maxLines = 1,
            )
            Text(
                text = fmtSize(file.size),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
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
private fun ShareScreenPreview() {
    MaterialTheme {
        ShareScreenContent(
            uiState = ShareUiState(
                shareUrl = "https://pan.quark.cn/s/abc12345",
                files = listOf(
                    ShareFile("电影_a.mp4", 2L * 1024 * 1024 * 1024, "https://dl.quark.cn/1"),
                    ShareFile("文档_b.zip", 15L * 1024 * 1024, "https://dl.quark.cn/2"),
                ),
                selected = setOf("https://dl.quark.cn/1"),
            ),
            onIntent = {},
            onOpenDownload = {},
            snackbarHostState = remember { SnackbarHostState() },
        )
    }
}
