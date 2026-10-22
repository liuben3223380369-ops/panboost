package org.panboost.core.data

import android.content.Context
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import org.json.JSONArray
import org.json.JSONObject
import org.panboost.core.domain.DownloadHistoryEntry
import org.panboost.core.domain.DownloadHistoryList
import org.panboost.core.domain.DownloadHistoryRepository
import java.io.File
import javax.inject.Inject
import javax.inject.Singleton

/**
 * 下载历史存储（v5.0.0：v3.2.8 history.json 原生等价）。
 *
 * JSON 文件（外部私有目录 history.json）+ StateFlow 驱动历史屏。
 * 语义对齐旧版：新条目插队头 / 上限 200 / enabled 开关 /
 * 写盘失败静默（内存态兜底）。
 */
@Singleton
class DownloadHistoryStore @Inject constructor(
    @ApplicationContext context: Context,
) : DownloadHistoryRepository {

    private val file = File(
        context.getExternalFilesDir(null) ?: context.filesDir,
        "history.json",
    )

    private val state = MutableStateFlow(load())

    private fun load(): DownloadHistoryList = try {
        if (!file.exists()) return DownloadHistoryList()
        val root = JSONObject(file.readText())
        val arr = root.optJSONArray("items") ?: JSONArray()
        val items = (0 until arr.length()).mapNotNull { i ->
            val o = arr.optJSONObject(i) ?: return@mapNotNull null
            DownloadHistoryEntry(
                ts = o.optLong("ts"),
                url = o.optString("url"),
                name = o.optString("name"),
                size = o.optLong("size"),
                status = o.optString("status"),
                speed = o.optLong("speed"),
            )
        }
        DownloadHistoryList(enabled = root.optBoolean("enabled", true), items = items)
    } catch (_: Exception) {
        DownloadHistoryList()
    }

    /** 供仓库层读取当前态（enqueue 后落史用）。 */
    val current: StateFlow<DownloadHistoryList> = state.asStateFlow()

    override fun observeAll(): kotlinx.coroutines.flow.Flow<DownloadHistoryList> = state

    override fun add(entry: DownloadHistoryEntry) {
        val s = state.value
        if (!s.enabled) return
        val items = (listOf(entry) + s.items).take(ITEMS_MAX)
        update(DownloadHistoryList(enabled = s.enabled, items = items))
    }

    override fun clear() {
        update(DownloadHistoryList(enabled = state.value.enabled, items = emptyList()))
    }

    override fun setEnabled(enabled: Boolean) {
        update(DownloadHistoryList(enabled = enabled, items = state.value.items))
    }

    private fun update(next: DownloadHistoryList) {
        state.value = next
        try {
            val root = JSONObject().apply {
                put("enabled", next.enabled)
                put("items", JSONArray(next.items.map { e ->
                    JSONObject().apply {
                        put("ts", e.ts)
                        put("url", e.url)
                        put("name", e.name)
                        put("size", e.size)
                        put("status", e.status)
                        put("speed", e.speed)
                    }
                }))
            }
            file.writeText(root.toString())
        } catch (_: Exception) {
            // 写盘失败静默（内存态兜底——v3.2.8 同约束）
        }
    }

    private companion object {
        const val ITEMS_MAX = 200
    }
}
