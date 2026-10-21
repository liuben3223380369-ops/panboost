package org.panboost.core.domain

/**
 * 网盘文件/文件夹条目（第 4 周）。
 *
 * 纯 Kotlin：fid 为网盘侧唯一标识（根目录 "0"），isDir 决定
 * 点击语义（进入 vs 下载）。
 */
data class DriveFile(
    val fid: String,
    val name: String,
    val size: Long,
    val isDir: Boolean,
    val updatedAt: String,
)
