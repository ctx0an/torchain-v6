package com.torchain.android.tor

import com.torchain.android.util.Logger
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import java.io.BufferedReader
import java.io.IOException
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import java.net.InetSocketAddress
import java.net.Socket
import java.security.SecureRandom
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.TimeUnit
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

class ControlPortClient(
    private val host: String = "127.0.0.1",
    private val port: Int = 9051,
    private val cookieFile: java.io.File? = null
) {
    private val mutex = Mutex()
    @Volatile private var sock: Socket? = null
    @Volatile private var writer: OutputStreamWriter? = null
    @Volatile private var reader: BufferedReader? = null
    @Volatile private var listenerThread: Thread? = null
    private var eventListener: ((Event) -> Unit)? = null
    @Volatile private var running = false
    private val replyQueue = LinkedBlockingQueue<String>()

    sealed class Event {
        data class Bootstrap(val progress: Int, val tag: String) : Event()
        data class Status(val severity: String, val action: String, val args: String) : Event()
        data class Bandwidth(val read: Long, val written: Long) : Event()
        data class Circuit(
            val id: String,
            val status: String,
            val path: String,
            val buildFlags: String = "",
            val purpose: String = "",
            val confluxId: String = ""
        ) : Event()
        data class Log(val severity: String, val msg: String) : Event()
    }

    fun setEventListener(l: (Event) -> Unit) { eventListener = l }

    suspend fun connect() = withContext(Dispatchers.IO) {
        mutex.withLock {
            if (sock != null) {
                try { close() } catch (_: Exception) {}
            }
            val s = Socket()
            try {
                s.connect(InetSocketAddress(host, port), 5000)
                s.keepAlive = true
                sock = s
                writer = OutputStreamWriter(s.getOutputStream(), Charsets.UTF_8)
                reader = BufferedReader(InputStreamReader(s.getInputStream(), Charsets.UTF_8))
                replyQueue.clear()
                running = true
                authenticate()
                startReader()
            } catch (e: Exception) {
                running = false
                try { writer?.close() } catch (_: Exception) {}
                try { reader?.close() } catch (_: Exception) {}
                try { s.close() } catch (_: Exception) {}
                writer = null
                reader = null
                sock = null
                throw e
            }
        }
    }

    private fun authenticate() {
        val cookie = cookieFile?.takeIf { it.exists() }?.readBytes()
        if (cookie != null && cookie.isNotEmpty()) {
            val clientNonce = ByteArray(32).also { SecureRandom().nextBytes(it) }
            val clientNonceHex = clientNonce.toHex()
            send("AUTHCHALLENGE SAFECOOKIE $clientNonceHex")
            val resp = readReplyDirect().joinToString(" ")
            if (!resp.contains("AUTHCHALLENGE")) {
                throw IOException("AUTHCHALLENGE rejected: $resp")
            }
            val serverHashHex = extractHex(resp, "SERVERHASH=")
                ?: throw IOException("No SERVERHASH in challenge reply: $resp")
            val serverNonceHex = extractHex(resp, "SERVERNONCE=")
                ?: throw IOException("No SERVERNONCE in challenge reply: $resp")
            val serverNonce = serverNonceHex.fromHex()

            val message = cookie + clientNonce + serverNonce

            val expectedServerHash =
                hmacSha256(SERVER_TO_CONTROLLER_KEY.toByteArray(Charsets.US_ASCII), message)
            if (!expectedServerHash.contentEquals(serverHashHex.fromHex())) {
                throw IOException("SAFECOOKIE server hash mismatch (MITM?)")
            }

            val clientHash =
                hmacSha256(CONTROLLER_TO_SERVER_KEY.toByteArray(Charsets.US_ASCII), message)
            send("AUTHENTICATE ${clientHash.toHex()}")
        } else {
            send("AUTHENTICATE")
        }
        readReplyDirect().forEach { line ->
            if (!line.startsWith("250")) throw IOException("Tor auth failed: $line")
        }
        Logger.i("tor-ctl", "control port authenticated")
    }

    private fun startReader() {
        listenerThread = Thread({ readerLoop() }, "tor-ctl-reader").apply {
            isDaemon = true; start()
        }
    }

    private fun readerLoop() {
        val r = reader ?: return
        var inReplyDataBlock = false
        var inEventDataBlock = false
        try {
            while (running) {
                val line = r.readLine() ?: break
                if (line.isBlank() && !inReplyDataBlock && !inEventDataBlock) continue
                Logger.d("tor-ctl", "<< $line")

                if (inReplyDataBlock) {
                    replyQueue.put(line)
                    if (line == ".") {
                        inReplyDataBlock = false
                    }
                } else if (inEventDataBlock) {
                    if (line == ".") {
                        inEventDataBlock = false
                    }
                } else {
                    val isAsync = line.length >= 4 && line.startsWith("650") &&
                                  (line[3] == ' ' || line[3] == '-' || line[3] == '+')

                    if (isAsync) {
                        if (line.length >= 4 && line[3] == '+') {
                            inEventDataBlock = true
                        }
                        parseAsyncLine(line)?.let { ev -> eventListener?.invoke(ev) }
                    } else {
                        val isDataBlockStart = line.length >= 4 && line[3] == '+' &&
                                              line.substring(0, 3).all { it.isDigit() }
                        if (isDataBlockStart) {
                            inReplyDataBlock = true
                        }
                        replyQueue.put(line)
                    }
                }
            }
        } catch (e: Exception) {
            if (running) Logger.w("tor-ctl", "reader loop ended", e)
        } finally {
            replyQueue.offer(SHUTDOWN_SENTINEL)
        }
    }

    private fun splitArguments(s: String): List<String> {
        val tokens = mutableListOf<String>()
        val current = StringBuilder()
        var inQuotes = false
        var escaped = false
        for (i in 0 until s.length) {
            val ch = s[i]
            if (escaped) {
                current.append(ch)
                escaped = false
            } else if (ch == '\\') {
                val nextCh = s.getOrNull(i + 1)
                if (nextCh == '"' || nextCh == '\\') {
                    escaped = true
                } else {
                    current.append(ch)
                }
            } else if (ch == '"') {
                inQuotes = !inQuotes
                current.append(ch)
            } else if (ch.isWhitespace() && !inQuotes) {
                if (current.isNotEmpty()) {
                    tokens.add(current.toString())
                    current.clear()
                }
            } else {
                current.append(ch)
            }
        }
        if (current.isNotEmpty()) {
            tokens.add(current.toString())
        }
        return tokens
    }

    private fun parseKv(tokens: List<String>): Map<String, String> {
        val out = LinkedHashMap<String, String>()
        for (t in tokens) {
            val eq = t.indexOf('=')
            if (eq > 0) {
                val key = t.substring(0, eq)
                var value = t.substring(eq + 1)
                if (value.startsWith('"') && value.endsWith('"') && value.length >= 2) {
                    value = value.substring(1, value.length - 1)
                }
                value = value.replace("\\\"", "\"").replace("\\\\", "\\")
                out[key] = value
            }
        }
        return out
    }

    private fun parseAsyncLine(line: String): Event? {
        if (!line.startsWith("650 ")) return null
        val body = line.removePrefix("650 ").trim()
        return when {
            body.startsWith("STATUS_CLIENT ") || body.startsWith("STATUS_GENERAL ") ||
            body.startsWith("STATUS_BOOTSTRAP ") -> {
                val parts = splitArguments(body).drop(1)
                val severity = parts.firstOrNull() ?: ""
                val action = parts.getOrNull(1) ?: ""
                val kv = parseKv(parts.drop(2))
                if (action == "BOOTSTRAP") {
                    Event.Bootstrap((kv["PROGRESS"] ?: "0").toIntOrNull() ?: 0, kv["TAG"] ?: "")
                } else {
                    Event.Status(severity, action, kv.toString())
                }
            }
            body.startsWith("BW ") -> {
                val p = splitArguments(body.removePrefix("BW "))
                Event.Bandwidth(p.getOrNull(0)?.toLongOrNull() ?: 0, p.getOrNull(1)?.toLongOrNull() ?: 0)
            }
            body.startsWith("CIRC ") -> {
                val tokens = splitArguments(body.removePrefix("CIRC "))
                val cid = tokens.getOrNull(0) ?: ""
                val cstatus = tokens.getOrNull(1) ?: ""
                val meta = mutableMapOf<String, String>()
                val pathParts = mutableListOf<String>()
                for (i in 2 until tokens.size) {
                    val t = tokens[i]
                    if (t.contains('=') && t[0].isUpperCase()) {
                        val eq = t.indexOf('=')
                        val key = t.substring(0, eq)
                        var value = t.substring(eq + 1)
                        if (value.startsWith('"') && value.endsWith('"') && value.length >= 2) {
                            value = value.substring(1, value.length - 1)
                        }
                        value = value.replace("\\\"", "\"").replace("\\\\", "\\")
                        meta[key] = value
                    } else {
                        pathParts.add(t)
                    }
                }
                Event.Circuit(
                    id = cid,
                    status = cstatus,
                    path = pathParts.joinToString(" "),
                    buildFlags = meta["BUILD_FLAGS"] ?: "",
                    purpose = meta["PURPOSE"] ?: "",
                    confluxId = meta["CONFLUX_ID"] ?: ""
                )
            }
            body.startsWith("NOTICE ") || body.startsWith("WARN ") || body.startsWith("ERR ") -> {
                val sp = body.indexOf(' ')
                Event.Log(body.substring(0, sp), body.substring(sp + 1))
            }
            else -> null
        }
    }

    suspend fun setEvents(vararg events: String) = withContext(Dispatchers.IO) {
        mutex.withLock {
            send("SETEVENTS ${events.joinToString(" ")}")
            readReply()
        }
    }

    suspend fun getInfo(vararg keys: String): Map<String, String> = withContext(Dispatchers.IO) {
        mutex.withLock {
            send("GETINFO ${keys.joinToString(" ")}")
            val replies = readReply()
            val out = LinkedHashMap<String, String>()
            var currentKey: String? = null
            val currentValue = StringBuilder()

            for (line in replies) {
                if (currentKey != null) {
                    if (line == ".") {
                        out[currentKey] = currentValue.toString().trimEnd('\n')
                        currentKey = null
                        currentValue.clear()
                    } else {
                        val unescapedLine = if (line.startsWith("..")) line.substring(1) else line
                        currentValue.append(unescapedLine).append('\n')
                    }
                } else {
                    if (line.startsWith("250+")) {
                        val body = line.substring(4)
                        val eq = body.indexOf('=')
                        if (eq > 0) {
                            currentKey = body.substring(0, eq)
                            currentValue.clear()
                        }
                    } else if (line.startsWith("250-")) {
                        val body = line.substring(4)
                        val eq = body.indexOf('=')
                        if (eq > 0) {
                            out[body.substring(0, eq)] = body.substring(eq + 1)
                        }
                    } else if (line.startsWith("250 ")) {
                        val body = line.substring(4)
                        if (body != "OK") {
                            val eq = body.indexOf('=')
                            if (eq > 0) {
                                out[body.substring(0, eq)] = body.substring(eq + 1)
                            }
                        }
                    }
                }
            }
            out
        }
    }

    suspend fun setConf(vararg pairs: Pair<String, String>) = withContext(Dispatchers.IO) {
        mutex.withLock {
            val s = pairs.joinToString(" ") { (k, v) ->
                "$k=${if (v.contains(' ') || v.isEmpty()) "\"$v\"" else v}"
            }
            send("SETCONF $s")
            readReply()
        }
    }

    suspend fun signal(sig: String) = withContext(Dispatchers.IO) {
        mutex.withLock {
            send("SIGNAL $sig")
            readReply()
        }
    }

    suspend fun close() = withContext(Dispatchers.IO) {
        running = false
        val s = sock
        val w = writer
        val r = reader
        val t = listenerThread

        try {
            if (w != null) {
                Logger.d("tor-ctl", ">> QUIT")
                w.write("QUIT\r\n")
                w.flush()
            }
        } catch (_: Exception) {}
        try { w?.close() } catch (_: Exception) {}
        try { r?.close() } catch (_: Exception) {}
        try { s?.close() } catch (_: Exception) {}
        replyQueue.offer(SHUTDOWN_SENTINEL)
        try { t?.join(500) } catch (_: Exception) {}

        mutex.withLock {
            if (sock === s) sock = null
            if (writer === w) writer = null
            if (reader === r) reader = null
            if (listenerThread === t) listenerThread = null
        }
    }

    private fun send(line: String) {
        val w = writer ?: throw IOException("not connected")
        Logger.d("tor-ctl", ">> $line")
        w.write(line + "\r\n"); w.flush()
    }

    private fun readReply(): List<String> {
        val out = ArrayList<String>()
        var inDataBlock = false
        while (true) {
            val line = replyQueue.poll(20, TimeUnit.SECONDS)
                ?: throw IOException("control port reply timeout")
            if (line == SHUTDOWN_SENTINEL) {
                replyQueue.offer(SHUTDOWN_SENTINEL)
                throw IOException("Control port disconnected")
            }
            out.add(line)
            if (!inDataBlock && line.length >= 4 && line[3] == '+' && line.substring(0, 3).all { it.isDigit() }) {
                inDataBlock = true
            } else if (inDataBlock && line == ".") {
                inDataBlock = false
            }
            if (!inDataBlock && line.length >= 4 && line[3] == ' ' && line.substring(0, 3).all { it.isDigit() }) break
        }
        return out
    }

    private fun readReplyDirect(): List<String> {
        val r = reader ?: throw IOException("not connected")
        val out = ArrayList<String>()
        var inDataBlock = false
        while (true) {
            val line = r.readLine() ?: throw IOException("control port closed")
            Logger.d("tor-ctl", "<< $line")
            out.add(line)
            if (!inDataBlock && line.length >= 4 && line[3] == '+' && line.substring(0, 3).all { it.isDigit() }) {
                inDataBlock = true
            } else if (inDataBlock && line == ".") {
                inDataBlock = false
            }
            if (!inDataBlock && line.length >= 4 && line[3] == ' ' && line.substring(0, 3).all { it.isDigit() }) break
        }
        return out
    }

    private fun extractHex(s: String, key: String): String? {
        val i = s.indexOf(key)
        if (i < 0) return null
        val rest = s.substring(i + key.length)
        val end = rest.indexOf(' ').let { if (it < 0) rest.length else it }
        return rest.substring(0, end).trim()
    }

    private fun hmacSha256(key: ByteArray, msg: ByteArray): ByteArray {
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(key, "HmacSHA256"))
        return mac.doFinal(msg)
    }

    private fun ByteArray.toHex(): String = joinToString("") { "%02x".format(it) }
    private fun String.fromHex(): ByteArray {
        val clean = trim()
        require(clean.length % 2 == 0) { "odd-length hex string" }
        return ByteArray(clean.length / 2) { i ->
            ((Character.digit(clean[i * 2], 16) shl 4) +
              Character.digit(clean[i * 2 + 1], 16)).toByte()
        }
    }

    companion object {
        private const val SHUTDOWN_SENTINEL = "\u0000_SHUTDOWN_\u0000"
        private const val SERVER_TO_CONTROLLER_KEY =
            "Tor safe cookie authentication server-to-controller hash"
        private const val CONTROLLER_TO_SERVER_KEY =
            "Tor safe cookie authentication controller-to-server hash"
    }
}
