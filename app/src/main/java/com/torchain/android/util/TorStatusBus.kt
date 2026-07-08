package com.torchain.android.util

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import androidx.localbroadcastmanager.content.LocalBroadcastManager
import com.torchain.android.data.TorState
import com.torchain.android.data.TorStatus
import com.torchain.android.service.TorService
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

object TorStatusBus {
    private val _status = MutableStateFlow(TorStatus())
    val status: StateFlow<TorStatus> = _status.asStateFlow()

    fun update(newStatus: TorStatus) {
        _status.value = newStatus
    }

    private val receiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            if (intent.action != TorService.ACTION_STATUS) return
            val stateName = intent.getStringExtra(TorService.EXTRA_STATE) ?: "Stopped"
            val state: TorState = when (stateName) {
                "Starting" -> TorState.Starting
                "Running" -> TorState.Running
                "Stopping" -> TorState.Stopping
                "Bootstrapping" -> TorState.Bootstrapping(
                    intent.getIntExtra(TorService.EXTRA_PROGRESS, 0),
                    intent.getStringExtra(TorService.EXTRA_TAG) ?: ""
                )
                "Error" -> TorState.Error(intent.getStringExtra(TorService.EXTRA_MESSAGE) ?: "")
                else -> TorState.Stopped
            }
            _status.value = _status.value.copy(
                state = state,
                pid = intent.getIntExtra(TorService.EXTRA_PID, 0),
                socksPort = intent.getIntExtra(TorService.EXTRA_SOCKS, 9050),
                controlPort = intent.getIntExtra(TorService.EXTRA_CONTROL, 9051),
                exitIp = intent.getStringExtra(TorService.EXTRA_EXIT_IP) ?: "",
                message = intent.getStringExtra(TorService.EXTRA_MESSAGE) ?: ""
            )
        }
    }

    @Volatile private var registered = false
    private val lock = Any()

    fun register(context: Context) = synchronized(lock) {
        if (registered) return
        LocalBroadcastManager.getInstance(context.applicationContext).registerReceiver(
            receiver, IntentFilter(TorService.ACTION_STATUS))
        registered = true
    }

    fun unregister(context: Context) = synchronized(lock) {
        if (!registered) return
        LocalBroadcastManager.getInstance(context.applicationContext).unregisterReceiver(receiver)
        registered = false
    }
}
