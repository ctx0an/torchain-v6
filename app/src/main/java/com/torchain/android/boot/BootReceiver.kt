package com.torchain.android.boot

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import com.torchain.android.data.Config
import com.torchain.android.service.TorService
import com.torchain.android.util.Logger
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED &&
            intent.action != Intent.ACTION_LOCKED_BOOT_COMPLETED) return
        Logger.i("boot", "Boot completed received")
        val pending = goAsync()
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val cfg = Config.flow(context).first()
                if (cfg.startOnBoot) {
                    Logger.i("boot", "Auto-starting tor on boot")
                    TorService.start(context)
                }
            } catch (e: Exception) {
                Logger.w("boot", "auto-start check failed", e)
            } finally { pending.finish() }
        }
    }
}
