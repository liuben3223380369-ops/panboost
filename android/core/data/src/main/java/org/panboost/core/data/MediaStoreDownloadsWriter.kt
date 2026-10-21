package org.panboost.core.data

import android.content.ContentValues
import android.content.Context
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import dagger.hilt.android.qualifiers.ApplicationContext
import java.io.File
import java.io.IOException
import java.io.OutputStream
import javax.inject.Inject
import javax.inject.Singleton

/**
 * 公共 Download 落盘写入器（第 2 周核心：MediaStore 正统路径）。
 *
 * Kivy 时代四轮真机坑（v3.2.5~v3.2.8 的 O_RDWR 拒发、隐藏文件
 * 误判、flock EACCES、ftruncate 被拒）的总结论：Android 11+ 上
 * 应用对公共 Download 的媒体文件没有直写路径权限，唯一正统是
 * MediaStore 插入——本类即该路径的实现：
 * - API 29+：MediaStore.Downloads 插入（RELATIVE_PATH =
 *   Download/PanBoost、IS_PENDING=1）→ openOutputStream 流式
 *   写 → IS_PENDING=0 发布（文件管理器即刻可见，**零权限**）
 * - API 26-28：无 MediaStore Downloads 集合，回退 App 专属外部
 *   目录（无权限、必可写）
 *
 * 事务语义：finish() 发布；abort() 清理半成品（取消/失败路径，
 * API 29+ 删除 pending 行，26-28 删除文件）。
 */
@Singleton
class MediaStoreDownloadsWriter @Inject constructor(
    @ApplicationContext private val context: Context,
) {

    /** 一次写入事务：流 + 结束/中止句柄（成对调用，且仅一次）。 */
    class Output(
        val stream: OutputStream,
        private val finisher: () -> Unit,
        private val aborter: () -> Unit,
    ) {
        private var done = false

        fun finish() {
            check(!done) { "output already closed" }
            done = true
            stream.close()
            finisher()
        }

        fun abort() {
            check(!done) { "output already closed" }
            done = true
            try {
                stream.close()
            } catch (_: IOException) {
            }
            aborter()
        }
    }

    /**
     * 创建下载目标并打开输出流。
     *
     * @param fileName 如 "panboost_验收.bin"
     * @param mime 如 "application/octet-stream"
     */
    fun create(fileName: String, mime: String): Output {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            createViaMediaStore(fileName, mime)
        } else {
            createViaAppDir(fileName)
        }
    }

    // ---- API 29+：MediaStore.Downloads ----

    private fun createViaMediaStore(fileName: String, mime: String): Output {
        val resolver = context.contentResolver
        val values = ContentValues().apply {
            put(MediaStore.MediaColumns.DISPLAY_NAME, fileName)
            put(MediaStore.MediaColumns.MIME_TYPE, mime)
            put(MediaStore.MediaColumns.RELATIVE_PATH, RELATIVE_DIR)
            put(MediaStore.MediaColumns.IS_PENDING, 1)
        }
        val uri: Uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
            ?: throw IOException("MediaStore insert 失败（Downloads 集合不可用）")
        val stream = resolver.openOutputStream(uri, "w")
            ?: run {
                resolver.delete(uri, null, null)
                throw IOException("MediaStore 打开输出流失败")
            }
        return Output(
            stream = stream,
            finisher = {
                resolver.update(
                    uri,
                    ContentValues().apply {
                        put(MediaStore.MediaColumns.IS_PENDING, 0)
                    },
                    null,
                    null,
                )
            },
            aborter = {
                resolver.delete(uri, null, null)
            },
        )
    }

    // ---- API 26-28：App 专属外部目录（getExternalFilesDir 永远可写）----

    private fun createViaAppDir(fileName: String): Output {
        val dir = File(
            context.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS)
                ?: context.filesDir,
            "PanBoost",
        )
        dir.mkdirs()
        val file = File(dir, fileName)
        return Output(
            stream = file.outputStream(),
            finisher = { /* 目录文件即时可见，无 pending 语义 */ },
            aborter = { file.delete() },
        )
    }

    private companion object {
        const val RELATIVE_DIR = "Download/PanBoost"
    }
}
