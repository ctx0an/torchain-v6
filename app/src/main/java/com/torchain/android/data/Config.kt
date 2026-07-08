package com.torchain.android.data

import android.content.Context
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.intPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

import android.os.Build
import java.io.File
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.PreferenceDataStoreFactory

private val dataStoreLock = Any()
@Volatile
private var cachedDataStore: DataStore<Preferences>? = null

private val Context.dataStore: DataStore<Preferences>
    get() = synchronized(dataStoreLock) {
        cachedDataStore ?: PreferenceDataStoreFactory.create(
            produceFile = {
                val storageContext = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
                    applicationContext.createDeviceProtectedStorageContext()
                } else {
                    applicationContext
                }
                File(storageContext.filesDir, "datastore/torchain_prefs.preferences_pb")
            }
        ).also { cachedDataStore = it }
    }

data class TorchainConfig(
    val exitCountry: String = "",
    val blockIpv6: Boolean = true,
    val spoofMac: Boolean = false,
    val spoofHostname: Boolean = false,
    val watchdogEnabled: Boolean = false,
    val autoRotateMinutes: Int = 0,
    val startOnBoot: Boolean = false,
    val bridgesEnabled: Boolean = false,
    val bridgeTransport: String = "vanilla",
    val bridgeLines: List<String> = emptyList(),
    val proxyMode: String = "vpn" // "vpn" or "socks5"
)

object Config {
    private object Keys {
        val EXIT_COUNTRY = stringPreferencesKey("exit_country")
        val BLOCK_IPV6 = booleanPreferencesKey("block_ipv6")
        val SPOOF_MAC = booleanPreferencesKey("spoof_mac")
        val SPOOF_HOSTNAME = booleanPreferencesKey("spoof_hostname")
        val WATCHDOG_ENABLED = booleanPreferencesKey("watchdog_enabled")
        val AUTO_ROTATE_MIN = intPreferencesKey("auto_rotate_minutes")
        val START_ON_BOOT = booleanPreferencesKey("start_on_boot")
        val BRIDGES_ENABLED = booleanPreferencesKey("bridges_enabled")
        val BRIDGE_TRANSPORT = stringPreferencesKey("bridge_transport")
        val BRIDGE_LINES = stringPreferencesKey("bridge_lines")
        val PROXY_MODE = stringPreferencesKey("proxy_mode")
    }

    fun flow(ctx: Context): Flow<TorchainConfig> = ctx.dataStore.data.map { it.toConfig() }

    suspend fun set(ctx: Context, block: (TorchainConfig) -> TorchainConfig) {
        ctx.dataStore.edit { prefs ->
            val updated = block(prefs.toConfig())
            prefs[Keys.EXIT_COUNTRY] = updated.exitCountry
            prefs[Keys.BLOCK_IPV6] = updated.blockIpv6
            prefs[Keys.SPOOF_MAC] = updated.spoofMac
            prefs[Keys.SPOOF_HOSTNAME] = updated.spoofHostname
            prefs[Keys.WATCHDOG_ENABLED] = updated.watchdogEnabled
            prefs[Keys.AUTO_ROTATE_MIN] = updated.autoRotateMinutes
            prefs[Keys.START_ON_BOOT] = updated.startOnBoot
            prefs[Keys.BRIDGES_ENABLED] = updated.bridgesEnabled
            prefs[Keys.BRIDGE_TRANSPORT] = updated.bridgeTransport
            prefs[Keys.BRIDGE_LINES] = updated.bridgeLines.joinToString("\n")
            prefs[Keys.PROXY_MODE] = updated.proxyMode
        }
    }

    private fun Preferences.toConfig() = TorchainConfig(
        exitCountry = this[Keys.EXIT_COUNTRY] ?: "",
        blockIpv6 = this[Keys.BLOCK_IPV6] ?: true,
        spoofMac = this[Keys.SPOOF_MAC] ?: false,
        spoofHostname = this[Keys.SPOOF_HOSTNAME] ?: false,
        watchdogEnabled = this[Keys.WATCHDOG_ENABLED] ?: false,
        autoRotateMinutes = this[Keys.AUTO_ROTATE_MIN] ?: 0,
        startOnBoot = this[Keys.START_ON_BOOT] ?: false,
        bridgesEnabled = this[Keys.BRIDGES_ENABLED] ?: false,
        bridgeTransport = this[Keys.BRIDGE_TRANSPORT] ?: "vanilla",
        bridgeLines = (this[Keys.BRIDGE_LINES] ?: "").split('\n').map { it.trim() }.filter { it.isNotBlank() },
        proxyMode = this[Keys.PROXY_MODE] ?: "vpn"
    )
}
