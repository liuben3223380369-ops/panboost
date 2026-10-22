package org.panboost.core.network

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * CookieKit 纯函数单测（v5.4.1：JVM 直跑——testImplementation
 * org.json:json 提供 Android 外的真实实现）。
 */
class CookieKitTest {

    // ---- mergeCookie ----

    @Test
    fun mergeCookie_liveBlank_returnsSnapshot() {
        assertEquals("a=1; b=2", CookieKit.mergeCookie("", "a=1; b=2"))
    }

    @Test
    fun mergeCookie_snapshotBlank_returnsLive() {
        assertEquals("x=9", CookieKit.mergeCookie("x=9", ""))
    }

    @Test
    fun mergeCookie_liveOverridesSnapshot() {
        // live 值优先（实时罐最新登录态）
        assertEquals("a=2; b=2", CookieKit.mergeCookie("a=2", "a=1; b=2"))
    }

    @Test
    fun mergeCookie_liveAddsMissingKeys() {
        assertEquals("a=1; c=3", CookieKit.mergeCookie("c=3", "a=1"))
    }

    // ---- setKv ----

    @Test
    fun setKv_overridesSameKey() {
        assertEquals("__puus=new; b=2", CookieKit.setKv("__puus=old; b=2", "__puus", "new"))
    }

    @Test
    fun setKv_appendsNewKey() {
        assertEquals("a=1; k=v", CookieKit.setKv("a=1", "k", "v"))
    }

    @Test
    fun setKv_caseInsensitiveMatch() {
        assertEquals("K=v", CookieKit.setKv("k=old", "K", "v"))
    }

    @Test
    fun setKv_emptyCookie_appends() {
        assertEquals("k=v", CookieKit.setKv("", "k", "v"))
    }

    // ---- extractDownloadUrl（三形态——v5.3.1 真机实锤） ----

    @Test
    fun extract_objectArray_currentQuarkForm() {
        // 真机日志实锤形态：data=[{fid,file_name,download_url}]
        val data = JSONArray().put(
            JSONObject()
                .put("fid", "faac56")
                .put("file_name", "TikTok.apk")
                .put("download_url", "https://dl-pc.quark.cn/abc")
        )
        assertEquals(
            "https://dl-pc.quark.cn/abc",
            CookieKit.extractDownloadUrl(data),
        )
    }

    @Test
    fun extract_objectArray_multipleEntries_firstHttpWins() {
        val data = JSONArray()
            .put(JSONObject().put("fid", "1").put("file_name", "no-url"))
            .put(JSONObject().put("fid", "2").put("download_url", "https://d/2"))
        assertEquals("https://d/2", CookieKit.extractDownloadUrl(data))
    }

    @Test
    fun extract_legacyBareArray_v328Form() {
        val data = JSONArray()
            .put("fid").put("name").put("https://old/zzz").put(123)
        assertEquals("https://old/zzz", CookieKit.extractDownloadUrl(data))
    }

    @Test
    fun extract_singleObject() {
        assertEquals(
            "https://d/1",
            CookieKit.extractDownloadUrl(JSONObject().put("download_url", "https://d/1")),
        )
    }

    @Test
    fun extract_objectArray_noUrl_returnsEmpty() {
        val data = JSONArray().put(JSONObject().put("fid", "x").put("file_name", "y"))
        assertEquals("", CookieKit.extractDownloadUrl(data))
    }

    @Test
    fun extract_nullAndWrongType_returnEmpty() {
        assertEquals("", CookieKit.extractDownloadUrl(null))
        assertEquals("", CookieKit.extractDownloadUrl(42))
        assertEquals("", CookieKit.extractDownloadUrl("https://x"))
    }
}
