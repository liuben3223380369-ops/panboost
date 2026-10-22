package org.panboost.core.domain

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** PanCatalog 单测（v5.4.1：数据完整性 + 检索语义）。 */
class PanCatalogTest {

    @Test
    fun catalog_has18Pans() {
        assertEquals(18, PanCatalog.all.size)
    }

    @Test
    fun catalog_keysUnique() {
        assertEquals(PanCatalog.all.size, PanCatalog.all.map { it.key }.toSet().size)
    }

    @Test
    fun byKey_quarkHasAuthKeys() {
        val quark = PanCatalog.byKey("quark")
        assertNotNull(quark)
        assertTrue(quark!!.authKeys.contains("__puus"))
        assertTrue(quark.authKeys.contains("__uid"))
    }

    @Test
    fun byKey_unknownReturnsNull() {
        assertNull(PanCatalog.byKey("nonexistent"))
    }

    @Test
    fun byShareUrl_quarkLink() {
        assertEquals("quark", PanCatalog.byShareUrl("https://pan.quark.cn/s/abc123")?.key)
    }

    @Test
    fun byShareUrl_ucLink() {
        assertEquals("uc", PanCatalog.byShareUrl("https://drive.uc.cn/s/xyz")?.key)
    }

    @Test
    fun byShareUrl_123panLink() {
        assertEquals("pan123", PanCatalog.byShareUrl("https://www.123pan.com/s/abc")?.key)
    }

    @Test
    fun byShareUrl_lanzouMultiDomain() {
        assertEquals("lanzou", PanCatalog.byShareUrl("https://wwp.lanzouv.com/iABCD")?.key)
    }

    @Test
    fun byShareUrl_unknownReturnsNull() {
        assertNull(PanCatalog.byShareUrl("https://example.com/s/x"))
    }

    @Test
    fun allPans_haveRequiredFields() {
        PanCatalog.all.forEach { pan ->
            assertTrue("loginUrl 空: ${pan.key}", pan.loginUrl.startsWith("https://"))
            assertTrue("domains 空: ${pan.key}", pan.domains.isNotEmpty())
            assertTrue("sharePatterns 空: ${pan.key}", pan.sharePatterns.isNotEmpty())
        }
    }
}
