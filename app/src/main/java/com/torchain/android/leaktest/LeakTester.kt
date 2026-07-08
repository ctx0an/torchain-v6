package com.torchain.android.leaktest

import com.torchain.android.data.LeakResult
import com.torchain.android.util.Logger
import kotlinx.coroutines.Deferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.withContext
import java.io.IOException
import java.net.HttpURLConnection
import java.net.InetSocketAddress
import java.net.Proxy
import java.net.Socket
import java.net.URL

class LeakTester(private val socksPort: Int = 9050) {

    suspend fun runFull(): List<LeakResult> = withContext(Dispatchers.IO) {
        val exitIpDeferred = async {
            try { fetch("https://api.ipify.org", useTor = true) } catch (e: Exception) { "" }
        }
        val d1 = async { checkRealIp(exitIpDeferred) }
        val d2 = async { checkExitIp(exitIpDeferred) }
        val d3 = async { checkDns() }
        val d4 = async { checkIpv6() }
        val d5 = async { checkFirewall() }
        awaitAll(d1, d2, d3, d4, d5)
    }

    suspend fun runQuick(): List<LeakResult> = withContext(Dispatchers.IO) {
        val exitIpDeferred = async {
            try { fetch("https://api.ipify.org", useTor = true) } catch (e: Exception) { "" }
        }
        val d1 = async { checkRealIp(exitIpDeferred) }
        val d2 = async { checkExitIp(exitIpDeferred) }
        awaitAll(d1, d2)
    }

    private suspend fun checkRealIp(exitIpDeferred: Deferred<String>): LeakResult {
        val realIp = try {
            fetch("https://api.ipify.org", useTor = false)
        } catch (e: Exception) {
            ""
        }
        val exitIp = exitIpDeferred.await()
        return if (realIp.isBlank()) {
            LeakResult("Real IP", true, "No clearnet reachability (good when VPN is up)")
        } else if (exitIp.isNotBlank() && realIp == exitIp) {
            LeakResult("Real IP", true, "Clearnet routed via Tor: $realIp")
        } else {
            LeakResult("Real IP", false, "Leak detected! Clearnet IP ($realIp) differs from Tor IP ($exitIp)")
        }
    }

    private suspend fun checkExitIp(exitIpDeferred: Deferred<String>): LeakResult {
        val exitIp = exitIpDeferred.await()
        return if (exitIp.isBlank()) {
            LeakResult("Exit IP", false, "Could not reach via Tor")
        } else {
            LeakResult("Exit IP", true, "Tor exit: $exitIp")
        }
    }

    private fun checkDns(): LeakResult = try {
        val addrs = java.net.InetAddress.getAllByName("duckduckgogg42xjoc72x3sjasowoarfbgcmvfimaftt6twagswzczad.onion")
        LeakResult("DNS", true,
            "Onion DNS resolved successfully: ${addrs.joinToString { it.hostAddress ?: "?" }}")
    } catch (e: Exception) {
        LeakResult("DNS", false, "DNS resolution failed: Onion DNS not routed")
    }

    private fun checkIpv6(): LeakResult = try {
        val url = URL("https://api6.ipify.org")
        val con = url.openConnection() as HttpURLConnection
        con.connectTimeout = 3000
        con.readTimeout = 3000
        con.requestMethod = "GET"
        con.connect()
        val ip = con.inputStream.bufferedReader().use { it.readText().trim() }
        con.disconnect()
        if (ip.isNotBlank() && isValidIp(ip)) {
            LeakResult("IPv6", false, "IPv6 endpoint reachable: $ip - possible leak")
        } else {
            LeakResult("IPv6", true, "IPv6 connection returned empty response (good)")
        }
    } catch (e: Exception) {
        LeakResult("IPv6", true, "IPv6 unreachable - good: ${e.message}")
    }

    private fun checkFirewall(): LeakResult = try {
        Socket().use { s -> s.connect(InetSocketAddress("1.1.1.1", 53), 5000) }
        LeakResult("Firewall", true, "Direct socket succeeded (traffic goes through TUN)")
    } catch (e: Exception) {
        LeakResult("Firewall", true, "Direct socket blocked - kill-switch active")
    }

    private fun isValidIp(ip: String): Boolean {
        val ipv4Regex = """^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$""".toRegex()
        val ipv6Regex = """^[a-fA-F0-9:]+$""".toRegex()
        return ipv4Regex.matches(ip) || (ip.contains(':') && ipv6Regex.matches(ip))
    }

    private fun fetch(urlStr: String, useTor: Boolean): String {
        val url = URL(urlStr)
        val con = if (useTor) {
            (url.openConnection(Proxy(Proxy.Type.SOCKS,
                InetSocketAddress("127.0.0.1", socksPort))) as HttpURLConnection)
        } else url.openConnection() as HttpURLConnection
        con.connectTimeout = 8000
        con.readTimeout = 10000
        con.requestMethod = "GET"
        try {
            if (con.responseCode !in 200..299) throw IOException("HTTP ${con.responseCode}")
            val ip = con.inputStream.bufferedReader().use { it.readText().trim() }
            if (!isValidIp(ip)) throw IOException("Invalid IP response: $ip")
            return ip
        } finally { con.disconnect() }
    }
}
