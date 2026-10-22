package org.panboost.core.logging

import android.content.Context
import dagger.hilt.android.qualifiers.ApplicationContext
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import javax.inject.Inject
import javax.inject.Singleton

/**
 * 统一应用日志（v5.0.0：v3.2.8 applog.py 的原生等价物）。
 *
 * 三大诊断体系对齐旧版：
 * - crash-*.txt    CrashReporter（v4.1.1 已有）
 * - app-YYYYMMDD.log 本模块——关键操作流水，按天轮转保留 7 天
 * - 内存环形缓冲 RING_MAX=500 条——「日志」屏实时可见
 *
 * 设计约束（旧版同款）：
 * - 线程安全（synchronized）——Worker 并发写安全
 * - 文件写失败静默降级（只进内存 ring）——日志绝不弄崩 App
 */
@Singleton
class AppLog @Inject constructor(
    @ApplicationContext private val context: Context,
) {

    data class Entry(val time: Long, val level: String, val tag: String, val msg: String)

    private val ring = ArrayDeque<Entry>(RING_MAX)
    private val dayFmt = SimpleDateFormat("yyyyMMdd", Locale.US)
    private val timeFmt = SimpleDateFormat("HH:mm:ss", Locale.US)
    private val dir: File? = run {
        try {
            File(context.getExternalFilesDir(null) ?: context.filesDir, "logs").apply {
                mkdirs()
            }
        } catch (_: Exception) {
            null
        }
    }

    fun info(tag: String, msg: String) = write("INFO", tag, msg)
    fun warn(tag: String, msg: String) = write("WARN", tag, msg)
    fun error(tag: String, msg: String) = write("ERROR", tag, msg)

    /** 环形缓冲快照（日志屏消费；旧→新顺序）。 */
    fun snapshot(): List<Entry> = synchronized(ring) { ring.toList() }

    private fun write(level: String, tag: String, msg: String) {
        val now = System.currentTimeMillis()
        val entry = Entry(now, level, tag, msg.take(300))
        synchronized(ring) {
            ring.addLast(entry)
            while (ring.size > RING_MAX) ring.removeFirst()
        }
        // 落盘失败静默（仅内存模式）——v3.2.8 同约束
        try {
            val d = dir ?: return
            val line = "${timeFmt.format(Date(now))} $level [$tag] $msg\n"
            File(d, "app-${dayFmt.format(Date(now))}.log").appendText(line)
            cleanup(d)
        } catch (_: Exception) {
        }
    }

    /** 按天轮转清理（保留 KEEP_DAYS 天）。 */
    private fun cleanup(d: File) {
        val files = d.listFiles { f -> f.name.startsWith("app-") } ?: return
        if (files.size <= KEEP_DAYS) return
        files.sortedByDescending { it.name }.drop(KEEP_DAYS).forEach { it.delete() }
    }

    private companion object {
        const val RING_MAX = 500
        const val KEEP_DAYS = 7
    }
}
