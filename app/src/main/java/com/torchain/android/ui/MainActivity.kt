package com.torchain.android.ui

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.DrawerValue
import androidx.compose.material3.ModalNavigationDrawer
import androidx.compose.material3.Scaffold
import androidx.compose.material3.rememberDrawerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.activity.result.contract.ActivityResultContracts
import com.torchain.android.ui.components.AppTopBar
import com.torchain.android.ui.components.NavTarget
import com.torchain.android.ui.components.SidebarDrawer
import com.torchain.android.ui.screens.AdvancedScreen
import com.torchain.android.ui.screens.BridgesScreen
import com.torchain.android.ui.screens.CircuitsScreen
import com.torchain.android.ui.screens.DashboardScreen
import com.torchain.android.ui.screens.LeakTestScreen
import com.torchain.android.ui.screens.LogsScreen
import com.torchain.android.ui.screens.SettingsScreen
import com.torchain.android.ui.theme.KaliBg
import com.torchain.android.ui.theme.TorchainTheme
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    private val requestPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { isGranted: Boolean ->
        // Permission result handled if needed
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        
        // Request notification permission for Android 13+
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.TIRAMISU) {
            if (checkSelfPermission(android.Manifest.permission.POST_NOTIFICATIONS) != android.content.pm.PackageManager.PERMISSION_GRANTED) {
                requestPermissionLauncher.launch(android.Manifest.permission.POST_NOTIFICATIONS)
            }
        }

        setContent { TorchainTheme { AppRoot() } }
    }
}

@Composable
private fun AppRoot() {
    var current by rememberSaveable { mutableStateOf(NavTarget.DASHBOARD) }
    val context = LocalContext.current

    val drawerState = rememberDrawerState(initialValue = DrawerValue.Closed)
    val scope = rememberCoroutineScope()

    ModalNavigationDrawer(
        drawerState = drawerState,
        gesturesEnabled = true,
        drawerContent = {
            SidebarDrawer(
                current = current,
                onSelect = { target ->
                    current = target
                    scope.launch { drawerState.close() }
                },
                onStar = {
                    try {
                        val intent = android.content.Intent(
                            android.content.Intent.ACTION_VIEW,
                            android.net.Uri.parse("https://github.com/ctx0an/torchain")
                        )
                        context.startActivity(intent)
                    } catch (e: android.content.ActivityNotFoundException) {
                        e.printStackTrace()
                    }
                }
            )
        }
    ) {
        Scaffold(
            containerColor = KaliBg,
            contentColor = Color.Unspecified,
            topBar = {
                AppTopBar(onMenuClick = { scope.launch { drawerState.open() } })
            }
        ) { innerPadding ->
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(innerPadding)
            ) {
                when (current) {
                    NavTarget.DASHBOARD -> DashboardScreen()
                    NavTarget.CIRCUITS  -> CircuitsScreen()
                    NavTarget.BRIDGES   -> BridgesScreen()
                    NavTarget.LEAKTEST  -> LeakTestScreen()
                    NavTarget.SETTINGS  -> SettingsScreen()
                    NavTarget.ADVANCED  -> AdvancedScreen()
                    NavTarget.LOGS      -> LogsScreen()
                }
            }
        }
    }
}
