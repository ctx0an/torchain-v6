package com.torchain.android.ui.screens

import androidx.compose.foundation.background
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
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.torchain.android.data.LeakResult
import com.torchain.android.data.TorState
import com.torchain.android.leaktest.LeakTester
import com.torchain.android.ui.components.PillStatus
import com.torchain.android.ui.components.StatusPill
import com.torchain.android.ui.theme.KaliError
import com.torchain.android.ui.theme.KaliPrimary
import com.torchain.android.ui.theme.KaliSuccess
import com.torchain.android.ui.theme.KaliSurface
import com.torchain.android.ui.theme.KaliTextPrimary
import com.torchain.android.ui.theme.KaliTextSecondary
import com.torchain.android.util.TorStatusBus
import kotlinx.coroutines.launch

@Composable
fun LeakTestScreen() {
    val status by TorStatusBus.status.collectAsState()
    val results = remember { mutableStateListOf<LeakResult>() }
    val scope = rememberCoroutineScope()
    var running by remember { mutableStateOf(false) }
    val tester = remember { LeakTester() }

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
                Text("Leak Test", style = MaterialTheme.typography.headlineMedium)
                Text("Verify nothing escapes Tor",
                    style = MaterialTheme.typography.bodyMedium, color = KaliTextSecondary)
            }
            val failCount = results.count { !it.passed }
            StatusPill(
                text = if (results.isEmpty()) "NOT RUN"
                       else if (failCount == 0) "ALL PASS"
                       else "$failCount FAIL",
                status = when {
                    results.isEmpty() -> PillStatus.NEUTRAL
                    failCount == 0 -> PillStatus.SUCCESS
                    else -> PillStatus.ERROR
                }
            )
        }

        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Button(
                onClick = {
                    running = true; results.clear()
                    scope.launch {
                        try {
                            results.addAll(tester.runFull())
                        } finally {
                            running = false
                        }
                    }
                },
                enabled = !running && status.state is TorState.Running,
                modifier = Modifier.weight(1f).height(48.dp),
                colors = ButtonDefaults.buttonColors(containerColor = KaliPrimary)
            ) { Text(if (running) "RUNNING..." else "RUN FULL SUITE") }
            OutlinedButton(
                onClick = {
                    running = true; results.clear()
                    scope.launch {
                        try {
                            results.addAll(tester.runQuick())
                        } finally {
                            running = false
                        }
                    }
                },
                enabled = !running,
                modifier = Modifier.weight(1f).height(48.dp)
            ) { Text("RUN QUICK") }
        }

        if (results.isEmpty()) {
            Box(
                modifier = Modifier.fillMaxSize()
                    .clip(RoundedCornerShape(8.dp))
                    .background(KaliSurface).padding(24.dp),
                contentAlignment = Alignment.Center
            ) {
                Text(
                    "Connect to Tor, then run a leak test to verify your real IP, " +
                    "DNS, and IPv6 never escape.",
                    style = MaterialTheme.typography.bodyMedium, color = KaliTextSecondary)
            }
        } else {
            LazyColumn(modifier = Modifier.fillMaxSize(),
                verticalArrangement = Arrangement.spacedBy(8.dp)) {
                items(results) { r -> LeakResultRow(r) }
            }
        }
    }
}

@Composable
private fun LeakResultRow(r: LeakResult) {
    Row(
        modifier = Modifier.fillMaxWidth()
            .clip(RoundedCornerShape(8.dp))
            .background(KaliSurface).padding(16.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(
            modifier = Modifier
                .height(40.dp).padding(end = 16.dp)
                .clip(RoundedCornerShape(8.dp))
                .background(if (r.passed) KaliSuccess else KaliError)
                .padding(horizontal = 12.dp, vertical = 10.dp),
            contentAlignment = Alignment.Center
        ) {
            Text(if (r.passed) "PASS" else "FAIL",
                style = MaterialTheme.typography.labelMedium,
                color = KaliTextPrimary, fontWeight = FontWeight.Bold)
        }
        Column {
            Text(r.name,
                style = MaterialTheme.typography.titleMedium, color = KaliTextPrimary)
            Text(r.detail,
                style = MaterialTheme.typography.bodyMedium, color = KaliTextSecondary)
        }
    }
}
