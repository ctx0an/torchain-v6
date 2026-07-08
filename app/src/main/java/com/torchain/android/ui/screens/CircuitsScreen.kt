package com.torchain.android.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.torchain.android.data.CircuitInfo
import com.torchain.android.data.TorState
import com.torchain.android.service.TorService
import com.torchain.android.ui.components.PillStatus
import com.torchain.android.ui.components.StatusPill
import com.torchain.android.ui.theme.KaliAccent
import com.torchain.android.ui.theme.KaliSurface
import com.torchain.android.ui.theme.KaliTextPrimary
import com.torchain.android.ui.theme.KaliTextSecondary
import com.torchain.android.util.TorStatusBus
import kotlinx.coroutines.delay

@Composable
fun CircuitsScreen() {
    val context = LocalContext.current
    val status by TorStatusBus.status.collectAsState()
    var refreshing by remember { mutableStateOf(false) }

    LaunchedEffect(status.state) {
        while (status.state is TorState.Running) {
            TorService.refreshCircuits(context)
            delay(5000)
        }
    }

    LaunchedEffect(refreshing) {
        if (refreshing) {
            delay(1000)
            refreshing = false
        }
    }

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
                Text("Circuits", style = MaterialTheme.typography.headlineMedium)
                Text("Live Tor circuit table",
                    style = MaterialTheme.typography.bodyMedium,
                    color = KaliTextSecondary)
            }
            StatusPill(
                text = "${status.circuits.size} active",
                status = if (status.circuits.isEmpty()) PillStatus.NEUTRAL else PillStatus.ACCENT)
        }

        OutlinedButton(
            onClick = {
                refreshing = true
                TorService.refreshCircuits(context)
            },
            enabled = status.state is TorState.Running && !refreshing,
            modifier = Modifier.fillMaxWidth().height(48.dp)
        ) { Text(if (refreshing) "REFRESHING..." else "REFRESH NOW") }

        if (status.circuits.isEmpty()) {
            Box(
                modifier = Modifier.fillMaxSize()
                    .clip(RoundedCornerShape(8.dp))
                    .background(KaliSurface).padding(24.dp),
                contentAlignment = Alignment.Center
            ) {
                Text("No circuits. Connect to Tor to see live circuits.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = KaliTextSecondary)
            }
        } else {
            LazyColumn(modifier = Modifier.fillMaxSize(),
                verticalArrangement = Arrangement.spacedBy(8.dp)) {
                items(status.circuits) { c -> CircuitRow(c) }
            }
        }
    }
}

@Composable
private fun CircuitRow(c: CircuitInfo) {
    Column(
        modifier = Modifier.fillMaxWidth()
            .clip(RoundedCornerShape(8.dp))
            .background(KaliSurface).padding(12.dp)
    ) {
        Row(modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween) {
            Text("Circuit #${c.id}",
                style = MaterialTheme.typography.titleMedium,
                color = KaliAccent, fontWeight = FontWeight.Bold)
            Text(c.status,
                style = MaterialTheme.typography.labelMedium,
                color = KaliTextSecondary)
        }
        Spacer(modifier = Modifier.height(8.dp))
        c.hops.forEachIndexed { i, hop ->
            Text("  ${i + 1}. ${hop.nickname} [${hop.countryCode.ifEmpty { "??" }}]",
                style = MaterialTheme.typography.bodyMedium, color = KaliTextPrimary)
            Text("     ${hop.fingerprint}",
                style = MaterialTheme.typography.labelSmall, color = KaliTextSecondary)
        }
    }
}
