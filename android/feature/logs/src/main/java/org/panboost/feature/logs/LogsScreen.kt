package org.panboost.feature.logs

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import org.panboost.core.logging.AppLog
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * 日志屏（v5.0.0：v3.2.8「日志」屏原生等价）。
 *
 * 环形缓冲 500 条实时滚动（自动跟底）；ERROR 红 / WARN 橙 /
 * INFO 常色。完整文件位于
 * /Android/data/org.panboost.app/files/logs/app-YYYYMMDD.log
 * （按天轮转保留 7 天，文件管理器可取回反馈）。
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LogsScreen(
    viewModel: LogsViewModel = hiltViewModel(),
) {
    val entries by viewModel.entries.collectAsStateWithLifecycle()
    val listState = rememberLazyListState()
    LaunchedEffect(entries.size) {
        if (entries.isNotEmpty()) listState.animateScrollToItem(entries.size - 1)
    }
    Scaffold(topBar = { TopAppBar(title = { Text("日志（${entries.size}）") }) }) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
        ) {
            Text(
                text = "完整日志：Android/data/org.panboost.app/files/logs/app-日期.log（保留 7 天）",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(horizontal = 12.dp, vertical = 4.dp),
            )
            LazyColumn(
                state = listState,
                modifier = Modifier.fillMaxSize(),
            ) {
                items(entries) { e ->
                    LogRow(e)
                }
            }
        }
    }
}

@Composable
private fun LogRow(e: AppLog.Entry) {
    val time = SimpleDateFormat("HH:mm:ss", Locale.US).format(Date(e.time))
    val color = when (e.level) {
        "ERROR" -> MaterialTheme.colorScheme.error
        "WARN" -> androidx.compose.ui.graphics.Color(0xFFB45309)
        else -> MaterialTheme.colorScheme.onSurface
    }
    Text(
        text = "$time ${e.level} [${e.tag}] ${e.msg}",
        fontFamily = FontFamily.Monospace,
        fontSize = 11.sp,
        color = color,
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 12.dp, vertical = 2.dp),
    )
}
