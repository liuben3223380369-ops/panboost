package org.panboost.core.data

import android.content.Context
import dagger.hilt.android.qualifiers.ApplicationContext
import java.io.File
import java.io.PrintWriter
import java.io.StringWriter
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import javax.inject.Inject
import javax.inject.Singleton

/**
 * 全局崩溃捕获（v4.1.1：v3.2 诊断能力回魂）。
 *
 * v3.2.8 的 _install_crash_logger（sys.excepthook + Kivy
 * ExceptionManager → crash-*.log）在原生栈的等价物：
 * - Thread.setDefaultUncaughtExceptionHandler 捕获主线程/worker
 *   线程全部未捕获异常
 * - 崩溃快照写入 App 外部私有目录 crash-yyyyMMdd-HHmmss.txt
 *   （/Android/data/org.panboost.app/files/——用户可用文件管理器
 *   直接取回，无需权限）
 * - 写盘后交回系统默认 handler（保持正常崩溃流程，不吞异常）
 * - 装饰器模式链式保留（多次 install 不丢 handler）
 */
@Singleton
class CrashReporter @Inject constructor(
    @ApplicationContext private val context: Context,
) {

    fun install() {
        val current = Thread.getDefaultUncaughtExceptionHandler()
        if (current is CrashHandler) return
        Thread.setDefaultUncaughtExceptionHandler(
            CrashHandler(context, current)
        )
    }

    private class CrashHandler(
        private val context: Context,
        private val previous: Thread.UncaughtExceptionHandler?,
    ) : Thread.UncaughtExceptionHandler {

        override fun uncaughtException(thread: Thread, throwable: Throwable) {
            try {
                writeCrashFile(thread, throwable)
            } catch (_: Throwable) {
                // 诊断写盘自身绝不抛（崩溃路径上最后一道防线）
            }
            previous?.uncaughtException(thread, throwable)
        }

        private fun writeCrashFile(thread: Thread, throwable: Throwable) {
            val dir = File(
                context.getExternalFilesDir(null) ?: context.filesDir,
                "crashes",
            )
            dir.mkdirs()
            // 上限 10 份：崩溃循环时防占满存储
            dir.listFiles()?.sortedByDescending { it.name }?.drop(9)?.forEach {
                it.delete()
            }
            val stamp = SimpleDateFormat(
                "yyyyMMdd-HHmmss", Locale.US
            ).format(Date())
            val stack = StringWriter().also { throwable.printStackTrace(PrintWriter(it)) }.toString()
            val content = buildString {
                appendLine("PanBoost v4.1.1 崩溃报告")
                appendLine("时间: $stamp")
                appendLine("线程: ${thread.name} (id=${thread.id})")
                appendLine("系统: Android ${android.os.Build.VERSION.RELEASE} (API ${android.os.Build.VERSION.SDK_INT})")
                appendLine("设备: ${android.os.Build.MANUFACTURER} ${android.os.Build.MODEL}")
                appendLine()
                appendLine(stack.take(64 * 1024))
            }
            File(dir, "crash-$stamp.txt").writeText(content)
        }
    }
}
