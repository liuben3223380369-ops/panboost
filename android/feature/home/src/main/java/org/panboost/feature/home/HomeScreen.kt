package org.panboost.feature.home

import org.panboost.core.ui.fmtSize

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Description
import androidx.compose.material.icons.filled.Folder
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import org.panboost.core.domain.DriveFile

/**
 * 网盘首页（v5.1.1 生命周期刷新 + 空/错误态）。
 *
 * 结构性修复：
 * - ON_RESUME 触发 Refresh——每次 Tab 回前台重拉列表（此前 init
 *   只跑一次：先开网盘 Tab 失败→登录→回来仍空）
 * - 空态/错误态持久 UI：错误卡片（重试/去登录按钮）；未登录引导
 *   直达账号 Tab
 * - 文件夹轻点进入（面包屑返回）；文件轻点取直链下载
 */
@Composable
fun HomeScreen(
    onOpenDownload: () -> Unit,
    onOpenAccounts: () -> Unit = {},
    viewModel: HomeViewModel = hiltViewModel(),
) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()
    val snackbarHostState = remember { SnackbarHostState() }

    // v5.1.1：Tab 回前台自动刷新（登录后回来即重拉）
    val lifecycleOwner = LocalLifecycleOwner.current
    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) {
                viewModel.onIntent(HomeIntent.Refresh)
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }

    LaunchedEffect(uiState.snackbar) {
        uiState.snackbar?.let {
            snackbarHostState.showSnackbar(it)
            viewModel.onIntent(HomeIntent.SnackbarShown)
        }
    }
    HomeScreenContent(
        uiState = uiState,
        onIntent = viewModel::onIntent,
        onOpenAccounts = onOpenAccounts,
        snackbarHostState = snackbarHostState,
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun HomeScreenContent(
    uiState: HomeUiState,
    onIntent: (HomeIntent) -> Unit,
    onOpenAccounts: () -> Unit = {},
    snackbarHostState: SnackbarHostState,
) {
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(uiState.path.last().name) },
                navigationIcon = {
                    if (uiState.path.size > 1) {
                        IconButton(onClick = { onIntent(HomeIntent.NavigateUp) }) {
                            Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "返回上级")
                        }
                    }
                },
            )
        },
        snackbarHost = { SnackbarHost(snackbarHostState) },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
        ) {
            if (uiState.loading) LinearProgressIndicator(Modifier.fillMaxWidth())

            // v5.2.0：网盘选择条（已登录/已存 Cookie 的网盘——v3.2.8 首页宫格语义）
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 12.dp, vertical = 4.dp),
                horizontalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                uiState.availablePans.forEach { entry ->
                    FilterChip(
                        selected = uiState.selectedPan == entry.pan.key,
                        onClick = { onIntent(HomeIntent.SelectPan(entry.pan.key)) },
                        label = {
                            Text(
                                entry.pan.name + if (entry.verified) "" else "（未验证）",
                                style = MaterialTheme.typography.labelSmall,
                            )
                        },
                    )
                }
            }

            // v6.6.0：未接浏览 API 的网盘显示接入预告（quark/uc 已通）
            if (uiState.selectedPan !in setOf("quark", "uc")) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(24.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Text(
                        text = "${uiState.selectedPanName} 的登录 Cookie 已保存",
                        style = MaterialTheme.typography.titleMedium,
                    )
                    Text(
                        text = "该网盘的原生浏览下载正在接入中（ROADMAP）——分享链接下载可用请先体验夸克",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }

            Text(
                text = uiState.path.joinToString(" / ") { it.name },
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
            )
            if (uiState.downloading != null) {
                LinearProgressIndicator(Modifier.fillMaxWidth())
            }

            // v5.1.1：空态/错误态持久 UI
            if (uiState.showEmpty && uiState.selectedPan in setOf("quark", "uc")) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(24.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    if (uiState.error != null) {
                        Card(
                            colors = CardDefaults.cardColors(
                                containerColor = MaterialTheme.colorScheme.errorContainer,
                            ),
                            modifier = Modifier.fillMaxWidth(),
                        ) {
                            Column(
                                modifier = Modifier.padding(16.dp),
                                verticalArrangement = Arrangement.spacedBy(8.dp),
                            ) {
                                Text(
                                    text = "网盘加载失败",
                                    style = MaterialTheme.typography.titleMedium,
                                    color = MaterialTheme.colorScheme.onErrorContainer,
                                )
                                Text(
                                    text = uiState.error,
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onErrorContainer,
                                )
                            }
                        }
                    } else {
                        Text(
                            text = "暂无文件",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    Spacer(Modifier.height(4.dp))
                    Button(
                        onClick = { onIntent(HomeIntent.Refresh) },
                        enabled = !uiState.loading,
                    ) {
                        Text("重新加载")
                    }
                    OutlinedButton(onClick = onOpenAccounts) {
                        Text("去「账号」页登录夸克")
                    }
                }
            }

            if (uiState.selectedPan in setOf("quark", "uc")) LazyColumn(
                modifier = Modifier.fillMaxSize(),
            ) {
                items(uiState.files, key = { it.fid }) { file ->
                    FileRow(
                        file = file,
                        onClick = {
                            if (file.isDir) {
                                onIntent(HomeIntent.OpenDir(file))
                            } else {
                                onIntent(HomeIntent.DownloadFile(file))
                            }
                        },
                    )
                    HorizontalDivider()
                }
            }
        }
    }
}

@Composable
private fun FileRow(file: DriveFile, onClick: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(horizontal = 16.dp, vertical = 12.dp),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(
            imageVector = if (file.isDir) Icons.Filled.Folder else Icons.Filled.Description,
            contentDescription = null,
            tint = if (file.isDir) MaterialTheme.colorScheme.primary
            else MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = file.name,
                style = MaterialTheme.typography.bodyMedium,
                maxLines = 1,
            )
            Text(
                text = if (file.isDir) "文件夹" else fmtSize(file.size),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        Text(
            text = if (file.isDir) "" else "轻点下载",
            style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.primary,
        )
    }
}


@Preview(showBackground = true)
@Composable
private fun HomeScreenPreview() {
    MaterialTheme {
        HomeScreenContent(
            uiState = HomeUiState(
                files = listOf(
                    DriveFile("1", "电影", 0, true, ""),
                    DriveFile("2", "panboost.bin", 5L * 1024 * 1024, false, ""),
                )
            ),
            onIntent = {},
            snackbarHostState = remember { SnackbarHostState() },
        )
    }
}
