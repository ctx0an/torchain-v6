package com.torchain.android.util

import java.io.File
import java.net.InetAddress

object GeoIp {
    private data class Range(val from: Long, val to: Long, val cc: String)
    @Volatile private var ranges: List<Range>? = null
    @Volatile private var loaded: Boolean = false

    fun load(geoipFile: File) {
        if (loaded) return
        val list = ArrayList<Range>(200_000)
        try {
            geoipFile.useLines { lines ->
                lines.forEach { line ->
                    if (line.startsWith('#')) return@forEach
                    val parts = line.split(',')
                    if (parts.size < 3) return@forEach
                    val from = parts[0].toLongOrNull() ?: return@forEach
                    val to = parts[1].toLongOrNull() ?: return@forEach
                    list.add(Range(from, to, parts[2].trim()))
                }
            }
            list.sortBy { it.from }
            ranges = list; loaded = true
            Logger.i("geoip", "Loaded ${list.size} ranges from ${geoipFile.name}")
        } catch (e: Exception) { Logger.w("geoip", "load failed", e) }
    }

    fun lookup(ip: String): String {
        val r = ranges ?: return "??"
        val addr = try { InetAddress.getByName(ip) } catch (_: Exception) { return "??" }
        if (addr.address.size != 4) return "??"
        val b = addr.address
        val num = ((b[0].toLong() and 0xFF) shl 24) or
                  ((b[1].toLong() and 0xFF) shl 16) or
                  ((b[2].toLong() and 0xFF) shl 8)  or
                   (b[3].toLong() and 0xFF)
        var lo = 0; var hi = r.size - 1
        while (lo <= hi) {
            val mid = (lo + hi) ushr 1
            val rng = r[mid]
            when {
                num < rng.from -> hi = mid - 1
                num > rng.to -> lo = mid + 1
                else -> return rng.cc
            }
        }
        return "??"
    }
}
