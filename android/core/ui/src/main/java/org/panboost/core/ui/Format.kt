package org.panboost.core.ui

import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.unit.sp

/**
 * 共享格式化工具（v5.4.0：消灭 fmtSize 三处重复定义——NIA 查缺
 * 结论：core/ui 公共层缺失导致 feature 各自复制粘贴）。
 *
 * 纯函数无 Compose 依赖也行——保留 @Composable 供未来主题化。
 */

/** 字节数人性化（B/KB/MB/GB）。 */
fun fmtSize(bytes: Long): String = when {
    bytes >= 1024L * 1024 * 1024 -> "%.1fGB".format(bytes / 1024f / 1024f / 1024f)
    bytes >= 1024L * 1024 -> "%.1fMB".format(bytes / 1024f / 1024f)
    bytes >= 1024L -> "%dKB".format(bytes / 1024)
    else -> "${bytes}B"
}

/** 速率人性化（B/s → MB/s）。 */
fun fmtSpeed(bps: Long): String = when {
    bps >= 1024L * 1024 -> "%.1fMB/s".format(bps / 1024f / 1024f)
    bps >= 1024L -> "%dKB/s".format(bps / 1024)
    else -> "${bps}B/s"
}

/** 状态色语义（成功/失败/中性）。 */
object StatusColors {
    val success = Color(0xFF15803D)
    val failure = Color(0xFFB91C1C)
    val neutral = Color(0xFF657086)
}

/** 共享文本样式锚点（轻量——避免每屏重复微调）。 */
object TypeScale {
    val labelSmall = TextStyle(fontSize = 11.sp)
    val labelMedium = TextStyle(fontSize = 12.sp)
}
