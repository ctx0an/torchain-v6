package com.torchain.android.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshots.SnapshotStateMap
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.torchain.android.data.BridgeTransport
import com.torchain.android.data.Config
import com.torchain.android.data.TorchainConfig
import com.torchain.android.tor.BridgeManager
import com.torchain.android.ui.components.PillStatus
import com.torchain.android.ui.components.StatusPill
import com.torchain.android.ui.theme.KaliAccent
import com.torchain.android.ui.theme.KaliError
import com.torchain.android.ui.theme.KaliMagenta
import com.torchain.android.ui.theme.KaliPrimary
import com.torchain.android.ui.theme.KaliSuccess
import com.torchain.android.ui.theme.KaliSurface
import com.torchain.android.ui.theme.KaliTextPrimary
import com.torchain.android.ui.theme.KaliTextSecondary
import kotlinx.coroutines.launch

@Composable
fun BridgesScreen() {
    val context = LocalContext.current
    val configFlow = remember(context) { Config.flow(context) }
    val cfg by configFlow.collectAsState(initial = TorchainConfig())
    val scope = rememberCoroutineScope()
    var newBridge by remember { mutableStateOf("") }
    val testingBridges: SnapshotStateMap<String, Boolean> = remember { mutableStateMapOf() }
    val testResults: SnapshotStateMap<String, Pair<Boolean, Long>> = remember { mutableStateMapOf() }
    var fetching by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf("") }

    Column(
        modifier = Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column {
                Text("Bridges", style = MaterialTheme.typography.headlineMedium)
                Text("Censorship circumvention transports",
                    style = MaterialTheme.typography.bodyMedium,
                    color = KaliTextSecondary)
            }
            StatusPill(
                text = if (cfg.bridgesEnabled) "ENABLED" else "DISABLED",
                status = if (cfg.bridgesEnabled) PillStatus.SUCCESS else PillStatus.NEUTRAL)
        }

        Row(
            modifier = Modifier.fillMaxWidth()
                .clip(RoundedCornerShape(8.dp))
                .background(KaliSurface).padding(16.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column {
                Text("Use bridges",
                    style = MaterialTheme.typography.titleMedium, color = KaliTextPrimary)
                Text("Route tor through a bridge relay",
                    style = MaterialTheme.typography.bodyMedium, color = KaliTextSecondary)
            }
            Switch(
                checked = cfg.bridgesEnabled,
                onCheckedChange = { v ->
                    scope.launch { Config.set(context) { it.copy(bridgesEnabled = v) } }
                }
            )
        }

        Text("TRANSPORT", style = MaterialTheme.typography.labelMedium, color = KaliTextSecondary)
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            BridgeTransport.values().filter { it != BridgeTransport.CUSTOM }.forEach { t ->
                Box(
                    modifier = Modifier
                        .weight(1f)
                        .clip(RoundedCornerShape(8.dp))
                        .background(if (cfg.bridgeTransport == t.key) KaliPrimary else KaliSurface)
                        .clickable {
                            scope.launch { Config.set(context) { it.copy(bridgeTransport = t.key) } }
                        }
                        .padding(8.dp, 12.dp),
                    contentAlignment = Alignment.Center
                ) {
                    Text(
                        text = t.display,
                        style = MaterialTheme.typography.labelMedium,
                        color = if (cfg.bridgeTransport == t.key) KaliTextPrimary else KaliTextSecondary,
                        fontWeight = FontWeight.SemiBold
                    )
                }
            }
        }

        OutlinedTextField(
            value = newBridge,
            onValueChange = { newBridge = it },
            label = { Text("Add bridge line") },
            placeholder = { Text("obfs4 1.2.3.4:443 FINGERPRINT cert=... iat-mode=0") },
            modifier = Modifier.fillMaxWidth(),
            singleLine = true
        )
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Button(
                onClick = {
                    val trimmed = newBridge.trim()
                    if (trimmed.isNotBlank()) {
                        val parsed = BridgeManager.parse(trimmed)
                        if (parsed == null) {
                            message = "Invalid bridge line format. Expected: <transport> <ip>:<port> [fingerprint] ..."
                        } else {
                            scope.launch {
                                Config.set(context) {
                                    it.copy(bridgeLines = (it.bridgeLines + parsed.line).distinct())
                                }
                                newBridge = ""; message = "Bridge added"
                            }
                        }
                    }
                },
                modifier = Modifier.weight(1f),
                colors = ButtonDefaults.buttonColors(containerColor = KaliPrimary)
            ) { Text("ADD") }
            OutlinedButton(
                onClick = {
                    fetching = true
                    scope.launch {
                        try {
                            val tp = BridgeTransport.values().first { it.key == cfg.bridgeTransport }
                            val fetched = BridgeManager.fetch(tp)
                            Config.set(context) {
                                it.copy(bridgeLines = (it.bridgeLines + fetched).distinct())
                            }
                            message = "Fetched ${fetched.size} bridges"
                        } catch (e: Exception) {
                            message = "Fetch failed: ${e.message}"
                        } finally { fetching = false }
                    }
                },
                enabled = !fetching,
                modifier = Modifier.weight(1f)
            ) { Text(if (fetching) "FETCHING..." else "FETCH") }
        }

        Text("CONFIGURED BRIDGES",
            style = MaterialTheme.typography.labelMedium, color = KaliTextSecondary)
        if (cfg.bridgeLines.isEmpty()) {
            Box(
                modifier = Modifier.fillMaxWidth().height(80.dp)
                    .clip(RoundedCornerShape(8.dp))
                    .background(KaliSurface).padding(16.dp),
                contentAlignment = Alignment.Center
            ) {
                Text("No bridges configured. Fetch some from Tor Project or add manually.",
                    style = MaterialTheme.typography.bodyMedium, color = KaliTextSecondary)
            }
        } else {
            LazyColumn(
                modifier = Modifier.weight(1f),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                items(cfg.bridgeLines.withIndex().toList()) { (i, line) ->
                    val result = testResults[line]
                    Row(
                        modifier = Modifier.fillMaxWidth()
                            .clip(RoundedCornerShape(8.dp))
                            .background(KaliSurface).padding(12.dp),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text("#$i  ${line.substringBefore(' ', line)}",
                                style = MaterialTheme.typography.labelLarge, color = KaliAccent)
                            Text(line,
                                style = MaterialTheme.typography.labelSmall, color = KaliTextSecondary)
                            result?.let { (ok, ms) ->
                                Text(if (ok) "REACHABLE ($ms ms)" else "UNREACHABLE",
                                    style = MaterialTheme.typography.labelSmall,
                                    color = if (ok) KaliSuccess else KaliError,
                                    fontWeight = FontWeight.Bold)
                            }
                        }
                        val isTesting = testingBridges[line] ?: false
                        OutlinedButton(
                            onClick = {
                                scope.launch {
                                    testingBridges[line] = true
                                    try {
                                        val r = BridgeManager.test(line)
                                        testResults[line] = r
                                    } finally {
                                        testingBridges[line] = false
                                    }
                                }
                            },
                            enabled = !isTesting
                        ) { Text(if (isTesting) "TESTING..." else "TEST") }
                        OutlinedButton(
                            onClick = {
                                scope.launch {
                                    Config.set(context) {
                                        it.copy(bridgeLines = it.bridgeLines.filter { x -> x != line })
                                    }
                                    testResults.remove(line)
                                    testingBridges.remove(line)
                                }
                            },
                            colors = ButtonDefaults.outlinedButtonColors(contentColor = KaliMagenta)
                        ) { Text("DEL") }
                    }
                }
            }
        }

        if (message.isNotBlank()) {
            Text(message,
                style = MaterialTheme.typography.bodyMedium, color = KaliAccent)
        }
    }
}
