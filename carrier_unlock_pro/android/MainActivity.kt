package com.carrierunlockpro

import android.app.Activity
import android.os.Bundle
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Button
import android.os.Build

class MainActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val layout = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(32,32,32,32) }
        val text = TextView(this).apply { textSize = 18f; text = "Carrier Unlock Pro\nDevice: ${Build.MANUFACTURER} ${Build.MODEL}\nAndroid: ${Build.VERSION.RELEASE}\nCarrier lock status: unavailable via standard Android public APIs" }
        layout.addView(text)
        setContentView(layout)
    }
}
