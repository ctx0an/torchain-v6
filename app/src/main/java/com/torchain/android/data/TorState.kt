package com.torchain.android.data

sealed class TorState {
    object Stopped : TorState()
    object Starting : TorState()
    data class Bootstrapping(val progress: Int, val tag: String) : TorState()
    object Running : TorState()
    object Stopping : TorState()
    data class Error(val message: String) : TorState()
    val isRunning: Boolean get() = this is Running
    val isTransitioning: Boolean get() = this is Starting || this is Stopping || this is Bootstrapping
}

data class TorStatus(
    val state: TorState = TorState.Stopped,
    val pid: Int = 0,
    val socksPort: Int = 9050,
    val controlPort: Int = 9051,
    val dnsPort: Int = 5400,
    val exitIp: String = "",
    val exitCountry: String = "",
    val circuits: List<CircuitInfo> = emptyList(),
    val message: String = ""
)

data class CircuitInfo(val id: String, val status: String, val purpose: String, val hops: List<CircuitHop>)
data class CircuitHop(val nickname: String, val fingerprint: String, val ipv4: String, val countryCode: String)

data class Bridge(val transport: String, val line: String, val reachable: Boolean? = null, val latencyMs: Long? = null)

enum class BridgeTransport(val key: String, val display: String) {
    VANILLA("vanilla", "None"),
    OBFS4("obfs4", "obfs4"),
    SNOWFLAKE("snowflake", "Snowflake"),
    MEEK_LITE("meek_lite", "meek"),
    WEBTUNNEL("webtunnel", "WebTunnel"),
    CUSTOM("custom", "Custom");
}

data class LeakResult(val name: String, val passed: Boolean, val detail: String)
