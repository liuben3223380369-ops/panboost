package org.panboost.feature.accounts

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
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
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import org.panboost.core.domain.AccountEntry
import org.panboost.core.domain.PanCatalog

/**
 * 账号管理屏（v4.3.0：v3.2.8 账簿原生等价）。
 *
 * 18 网盘宫格：已登录徽标（特征键验证）/未验证徽标（Cookie
 * 已存但登录态不存 Cookie 的网盘）；点卡片去登录页；卡片上
 * "删除""粘贴"操作（手动粘贴 Cookie 是 WebView 登录失败的
 * 兜底路径——v3.2.8 同款语义）。
 */
@Composable
fun AccountsScreen(
    onLoginPan: (String) -> Unit,
    viewModel: AccountsViewModel = hiltViewModel(),
) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()
    val snackbarHostState = remember { SnackbarHostState() }
    LaunchedEffect(uiState.snackbar) {
        uiState.snackbar?.let {
            snackbarHostState.showSnackbar(it)
            viewModel.onIntent(AccountsIntent.SnackbarShown)
        }
    }
    AccountsScreenContent(
        uiState = uiState,
        onIntent = viewModel::onIntent,
        onLoginPan = onLoginPan,
        snackbarHostState = snackbarHostState,
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun AccountsScreenContent(
    uiState: AccountsUiState,
    onIntent: (AccountsIntent) -> Unit,
    onLoginPan: (String) -> Unit,
    snackbarHostState: SnackbarHostState,
) {
    Scaffold(
        topBar = {
            TopAppBar(title = { Text("账号（已验证 ${uiState.verifiedCount}）") })
        },
        snackbarHost = { SnackbarHost(snackbarHostState) },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(horizontal = 12.dp),
        ) {
            Text(
                text = "点网盘卡片登录；「粘贴」为手动 Cookie 兜底（登录页打不开时在浏览器登录后复制 Cookie 粘贴）",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(vertical = 8.dp),
            )
            LazyVerticalGrid(
                columns = GridCells.Fixed(2),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                items(uiState.entries, key = { it.pan.key }) { entry ->
                    AccountCard(
                        entry = entry,
                        onClick = { onLoginPan(entry.pan.key) },
                        onRemove = { onIntent(AccountsIntent.Remove(entry.pan.key)) },
                        onPaste = { onIntent(AccountsIntent.OpenPasteDialog(entry.pan.key)) },
                    )
                }
            }
        }
    }

    if (uiState.pasteDialogFor != null) {
        val panName = PanCatalog.byKey(uiState.pasteDialogFor!!)?.name.orEmpty()
        AlertDialog(
            onDismissRequest = { onIntent(AccountsIntent.ClosePasteDialog) },
            title = { Text("粘贴 Cookie（$panName）") },
            text = {
                OutlinedTextField(
                    value = uiState.pasteValue,
                    onValueChange = { onIntent(AccountsIntent.PasteValueChanged(it)) },
                    label = { Text("浏览器登录后复制的完整 Cookie 串") },
                    minLines = 3,
                    maxLines = 6,
                    modifier = Modifier.fillMaxWidth(),
                )
            },
            confirmButton = {
                TextButton(
                    onClick = { onIntent(AccountsIntent.SavePaste) },
                    enabled = uiState.pasteValue.isNotBlank(),
                ) { Text("保存") }
            },
            dismissButton = {
                TextButton(onClick = { onIntent(AccountsIntent.ClosePasteDialog) }) {
                    Text("取消")
                }
            },
        )
    }
}

@Composable
private fun AccountCard(
    entry: AccountEntry,
    onClick: () -> Unit,
    onRemove: () -> Unit,
    onPaste: () -> Unit,
) {
    Card(
        onClick = onClick,
        colors = CardDefaults.cardColors(
            containerColor = if (entry.verified) {
                MaterialTheme.colorScheme.primaryContainer
            } else {
                MaterialTheme.colorScheme.surfaceVariant
            }
        ),
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = entry.pan.name,
                    style = MaterialTheme.typography.titleMedium,
                )
                Text(
                    text = when {
                        entry.verified -> "已登录"
                        entry.hasCookie -> "未验证"
                        else -> "未登录"
                    },
                    style = MaterialTheme.typography.labelSmall,
                    color = if (entry.verified) {
                        MaterialTheme.colorScheme.primary
                    } else {
                        MaterialTheme.colorScheme.onSurfaceVariant
                    },
                )
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                AssistChip(
                    onClick = onPaste,
                    label = { Text("粘贴", style = MaterialTheme.typography.labelSmall) },
                )
                if (entry.hasCookie) {
                    AssistChip(
                        onClick = onRemove,
                        label = { Text("删除", style = MaterialTheme.typography.labelSmall) },
                    )
                }
            }
        }
    }
}

@Preview(showBackground = true)
@Composable
private fun AccountsScreenPreview() {
    MaterialTheme {
        AccountsScreenContent(
            uiState = AccountsUiState(
                entries = PanCatalog.all.take(6).mapIndexed { i, pan ->
                    AccountEntry(pan, hasCookie = i < 3, verified = i < 2)
                }
            ),
            onIntent = {},
            onLoginPan = {},
            snackbarHostState = remember { SnackbarHostState() },
        )
    }
}
