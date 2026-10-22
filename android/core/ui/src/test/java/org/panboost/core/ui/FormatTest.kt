package org.panboost.core.ui

import org.junit.Assert.assertEquals
import org.junit.Test

/** core:ui 格式化单测（v5.4.1）。 */
class FormatTest {

    @Test
    fun fmtSize_bytes() {
        assertEquals("500B", fmtSize(500))
    }

    @Test
    fun fmtSize_kb() {
        assertEquals("4KB", fmtSize(4096))
    }

    @Test
    fun fmtSize_mb() {
        assertEquals("1.5MB", fmtSize(1572864))
    }

    @Test
    fun fmtSize_gb() {
        assertEquals("2.0GB", fmtSize(2147483648L))
    }

    @Test
    fun fmtSpeed_units() {
        assertEquals("500B/s", fmtSpeed(500))
        assertEquals("128KB/s", fmtSpeed(131072))
        assertEquals("1.5MB/s", fmtSpeed(1572864))
    }
}
