package com.torchain.android.util

import android.content.Context
import android.util.Log
import java.io.File
import java.io.PrintWriter
import java.io.StringWriter
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

object Logger {
    private const val MAX_LOG_BYTES = 1L * 1024 * 1024
    private const val MAX_LOG_FILES = 3
    private const val TAG = "torchain"
    private lateinit var logDir: File
    private val isoFormat = SimpleDateFormat("yyyy-MM-dd HH:mm:ss.SSS", Locale.US)
    private val lock = Any()

    fun init(context: Context) = synchronized(lock) {
        if (!::logDir.isInitialized) {
            logDir = File(context.applicationContext.filesDir, "logs").apply { mkdirs() }
        }
    }

    fun currentLogFiles(): List<File> = synchronized(lock) {
        logDir.listFiles { f -> f.name.endsWith(".log") }
            ?.sortedByDescending { it.lastModified() } ?: emptyList()
    }

    fun tail(lines: Int = 500): String = synchronized(lock) {
        val cur = File(logDir, "torchain.log")
        if (!cur.exists()) return ""

        val maxReadBytes = 128 * 1024
        val fileLength = cur.length()
        val readLength = minOf(fileLength, maxReadBytes.toLong()).toInt()
        if (readLength <= 0) return ""

        val bytes = ByteArray(readLength)
        try {
            java.io.RandomAccessFile(cur, "r").use { raf ->
                raf.seek(fileLength - readLength)
                raf.readFully(bytes)
            }
        } catch (e: Exception) {
            return ""
        }

        val content = String(bytes, Charsets.UTF_8)
        val allLines = content.split('\n')
        // The first line might be incomplete because we cut in the middle of a line.
        // If we read only a portion of the file, drop the first line to avoid showing a partial log.
        val linesToTake = if (fileLength > readLength && allLines.size > 1) {
            allLines.drop(1)
        } else {
            allLines
        }
        linesToTake.takeLast(lines).joinToString("\n")
    }

    fun clear() {
        if (!::logDir.isInitialized) return
        synchronized(lock) {
            try {
                val cur = File(logDir, "torchain.log")
                if (cur.exists()) cur.writeText("")
                for (i in 1..MAX_LOG_FILES) {
                    val f = File(logDir, "torchain.$i.log")
                    if (f.exists()) f.delete()
                }
            } catch (_: Exception) { }
        }
    }

    fun d(tag: String, msg: String) { write('D', tag, msg); Log.d(tag, msg) }
    fun i(tag: String, msg: String) { write('I', tag, msg); Log.i(tag, msg) }
    fun w(tag: String, msg: String, t: Throwable? = null) {
        write('W', tag, msg + (t?.let { " - " + it.stack() } ?: "")); Log.w(tag, msg, t)
    }
    fun e(tag: String, msg: String, t: Throwable? = null) {
        write('E', tag, msg + (t?.let { " - " + it.stack() } ?: "")); Log.e(tag, msg, t)
    }

    private fun write(level: Char, tag: String, msg: String) {
        if (!::logDir.isInitialized) return
        synchronized(lock) {
            try {
                val cur = File(logDir, "torchain.log")
                if (cur.exists() && cur.length() > MAX_LOG_BYTES) rotate()
                cur.appendText("${isoFormat.format(Date())} $level/$tag: $msg\n")
            } catch (_: Exception) { }
        }
    }

    private fun rotate() {
        for (i in MAX_LOG_FILES downTo 1) {
            val src = if (i == 1) File(logDir, "torchain.log")
                      else File(logDir, "torchain.${i - 1}.log")
            if (!src.exists()) continue
            val dst = File(logDir, "torchain.$i.log")
            if (dst.exists()) dst.delete()
            src.renameTo(dst)
        }
        File(logDir, "torchain.log").createNewFile()
    }

    private fun Throwable.stack(): String {
        val sw = StringWriter()
        PrintWriter(sw).use { pw -> this.printStackTrace(pw) }
        return sw.toString().trim()
    }
}
