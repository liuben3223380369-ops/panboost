package org.panboost.core.network

import org.json.JSONObject

/**
 * Cookie / 直链解析纯函数工具集（v5.4.1：从 NetworkModule 内部类与
 * QuarkDriveRepository 私有方法提炼——单一定义点 + JVM 可单测）。
 *
 * 全部为无副作用纯函数：mergeCookie/setKv/extractDownloadUrl。
 */
object CookieKit {

    /** 快照合并（live 优先，快照补缺键）。 */
    fun mergeCookie(live: String, snapshot: String): String {
        if (live.isBlank()) return snapshot.trim()
        if (snapshot.isBlank()) return live
        val kv = linkedMapOf<String, String>()
        for (c in snapshot.split(";")) {
            val k = c.substringBefore("=").trim()
            if (k.isNotEmpty()) kv[k] = c.substringAfter("=").trim()
        }
        for (c in live.split(";")) {
            val k = c.substringBefore("=").trim()
            if (k.isNotEmpty()) kv[k] = c.substringAfter("=").trim()
        }
        return kv.entries.joinToString("; ") { "${it.key}=${it.value}" }
    }

    /** Cookie 串里覆盖/追加一个键值（保活合并用）。 */
    fun setKv(cookie: String, k: String, v: String): String {
        val parts = cookie.split("; ").filter { it.isNotBlank() }.toMutableList()
        val idx = parts.indexOfFirst {
            it.substringBefore("=").trim().equals(k, ignoreCase = true)
        }
        val kv = "$k=$v"
        if (idx >= 0) parts[idx] = kv else parts.add(kv)
        return parts.joinToString("; ")
    }

    /**
     * 三形态 download_url 提取（v5.3.1 真机日志实锤修正后提炼）。
     *
     * - 对象数组（当前夸克形态）：[{fid, file_name, download_url}]
     * - 旧裸数组（v3.2.8 时代）：[fid, name, url, size]
     * - 单对象：{download_url}
     */
    fun extractDownloadUrl(data: Any?): String {
        return when (data) {
            is org.json.JSONArray -> {
                for (i in 0 until data.length()) {
                    val o = data.optJSONObject(i) ?: continue
                    val u = o.optString("download_url")
                    if (u.startsWith("http")) return u
                }
                data.optString(2).takeIf { it.startsWith("http") } ?: ""
            }
            is JSONObject -> data.optString("download_url")
                .takeIf { it.startsWith("http") } ?: ""
            else -> ""
        }
    }
}
