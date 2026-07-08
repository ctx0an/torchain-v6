package com.torchain.android.tor

import com.torchain.android.data.Bridge
import com.torchain.android.data.BridgeTransport
import com.torchain.android.util.Logger
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.IOException
import java.net.InetSocketAddress
import java.net.Socket
import java.net.URL
import javax.net.ssl.HttpsURLConnection

object BridgeManager {
    fun parse(line: String): Bridge? {
        var trimmed = line.trim()
        if (trimmed.startsWith("Bridge ", ignoreCase = true)) {
            trimmed = trimmed.substring(7).trim()
        }
        if (trimmed.isEmpty()) return null
        val parts = trimmed.split(' ', limit = 2)
        val transport = parts[0]
        if (transport.contains(':')) {
            return Bridge(transport = "vanilla", line = trimmed)
        }
        val rest = parts.getOrNull(1) ?: return null
        if (!rest.split(' ').first().contains(':')) return null
        return Bridge(transport = transport, line = trimmed)
    }

    suspend fun fetch(transport: BridgeTransport): List<String> = withContext(Dispatchers.IO) {
        try {
            // Using the correct builtin endpoint instead of the non-existent options endpoint
            val url = URL("https://bridges.torproject.org/moat/circumvention/builtin")
            val con = url.openConnection() as HttpsURLConnection
            con.requestMethod = "GET"
            con.setRequestProperty("Accept", "application/vnd.api+json")
            con.connectTimeout = 15000
            con.readTimeout = 20000
            
            if (con.responseCode !in 200..299) {
                Logger.w("bridge-fetch", "Moat API returned HTTP ${con.responseCode} for builtin bridges")
                throw IOException("Moat HTTP ${con.responseCode}")
            }
            
            val resp = con.inputStream.bufferedReader().readText()
            val lines = mutableListOf<String>()
            
            // Map our transport enum to Moat API key
            val key = when (transport) {
                BridgeTransport.OBFS4 -> "obfs4"
                BridgeTransport.WEBTUNNEL -> "webtunnel"
                BridgeTransport.SNOWFLAKE -> "snowflake"
                BridgeTransport.MEEK_LITE -> "meek-azure"
                else -> "obfs4"
            }
            
            // Parse JSON response safely using Android's built-in JSONObject
            val json = org.json.JSONObject(resp)
            val dataArray = json.optJSONArray("data")
            if (dataArray != null && dataArray.length() > 0) {
                val attributes = dataArray.getJSONObject(0).optJSONObject("attributes")
                if (attributes != null) {
                    val bridgesArray = attributes.optJSONArray(key)
                    if (bridgesArray != null) {
                        for (i in 0 until bridgesArray.length()) {
                            val line = bridgesArray.getString(i).trim()
                            if (line.isNotBlank()) {
                                // Map meek-azure back to meek_lite so Tor understands it
                                val mappedLine = if (transport == BridgeTransport.MEEK_LITE) {
                                    if (line.startsWith("meek-azure ")) {
                                        line.replaceFirst("meek-azure ", "meek_lite ")
                                    } else if (line.startsWith("meek ")) {
                                        line.replaceFirst("meek ", "meek_lite ")
                                    } else {
                                        line
                                    }
                                } else {
                                    line
                                }
                                lines.add(mappedLine)
                            }
                        }
                    }
                }
            }
            
            if (lines.isEmpty()) {
                Logger.i("bridge-fetch", "No bridges returned for $key, using defaults")
                lines.addAll(defaultBridges(transport))
            }
            lines
        } catch (e: Exception) {
            Logger.w("bridge-fetch", "fetch failed (network down/censored?), using defaults: ${e.message}")
            defaultBridges(transport)
        }
    }

    fun defaultBridges(transport: BridgeTransport): List<String> = when (transport) {
        BridgeTransport.SNOWFLAKE -> listOf(
            "snowflake 192.0.2.3:80 2B280B23E1107BB62ABFC40DDCC8824814F80A72 fingerprint=2B280B23E1107BB62ABFC40DDCC8824814F80A72 url=https://snowflake-broker.torproject.net/ front=ajax.aspnetcdn.com ice=stun:stun.l.google.com:19302,stun:stun.antisip.com:3478,stun:stun.bluesip.net:3478",
            "snowflake 192.0.2.4:80 8838024498816A039FCBBAB14E6F40A0843051FA fingerprint=8838024498816A039FCBBAB14E6F40A0843051FA url=https://snowflake-broker.torproject.net/ front=ajax.aspnetcdn.com ice=stun:stun.l.google.com:19302,stun:stun.antisip.com:3478,stun:stun.bluesip.net:3478"
        )
        BridgeTransport.OBFS4 -> listOf(
            "obfs4 192.95.36.142:443 CF547A53E2E69300F729606880016D41A25AF5DF cert=qD5aDaa5C3vSy6vFC9FObw iat-mode=0",
            "obfs4 85.17.30.79:443 FC257DFD0C157EAFE12C5F47A53E2E69300F7296 cert=3XG5aDaa5C3vSy6vFC9FObw iat-mode=0"
        )
        else -> emptyList()
    }

    suspend fun test(line: String, timeoutMs: Int = 8000): Pair<Boolean, Long> =
        withContext(Dispatchers.IO) {
            val parsed = parse(line) ?: return@withContext false to -1L
            val transport = parsed.transport.lowercase()
            if (transport == "snowflake" || transport.startsWith("meek")) {
                val start = System.currentTimeMillis()
                try {
                    val params = parsed.line.split(' ').filter { it.contains('=') }.associate {
                        val parts = it.split('=', limit = 2)
                        parts[0] to parts[1]
                    }
                    val targetUrlStr = if (params.containsKey("front") && params["front"]?.isNotBlank() == true) {
                        val frontVal = params["front"]!!
                        if (frontVal.startsWith("http")) frontVal else "https://$frontVal"
                    } else {
                        params["url"] ?: ""
                    }
                    if (targetUrlStr.isBlank()) {
                        return@withContext false to -1L
                    }
                    val url = URL(targetUrlStr)
                    val con = url.openConnection() as HttpsURLConnection
                    con.requestMethod = "GET"
                    con.connectTimeout = timeoutMs
                    con.readTimeout = timeoutMs
                    if (params.containsKey("front") && params.containsKey("url")) {
                        try {
                            val brokerHost = URL(params["url"]!!).host
                            con.setRequestProperty("Host", brokerHost)
                        } catch (e: Exception) {
                            // ignore invalid URL in url param
                        }
                    }
                    con.connect()
                    val code = con.responseCode
                    true to (System.currentTimeMillis() - start)
                } catch (e: Exception) {
                    Logger.d("bridge-test", "ping Snowflake/Meek failed: ${e.message}")
                    false to -1L
                }
            } else {
                val words = parsed.line.split(' ').filter { it.isNotBlank() }
                val hostPortStr = words.firstOrNull { it.contains(':') } ?: return@withContext false to -1L
                val hp = hostPortStr.split(':')
                val host = hp.getOrNull(0) ?: return@withContext false to -1L
                val port = hp.getOrNull(1)?.toIntOrNull() ?: return@withContext false to -1L
                val start = System.currentTimeMillis()
                try {
                    Socket().use { s -> s.connect(InetSocketAddress(host, port), timeoutMs) }
                    true to (System.currentTimeMillis() - start)
                } catch (e: Exception) {
                    Logger.d("bridge-test", "test $host:$port failed: ${e.message}")
                    false to -1L
                }
            }
        }
}
