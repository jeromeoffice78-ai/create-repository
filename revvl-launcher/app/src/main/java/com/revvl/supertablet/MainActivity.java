package com.revvl.supertablet;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * One tap starts a localhost dashboard served by this app, then opens Chrome.
 * Works with the Google Play Termux edition, which lacks RUN_COMMAND.
 * The old Termux-based services remain untouched if already running.
 */
public final class MainActivity extends Activity {
    private static final String URL = DashboardService.DASHBOARD;
    private static final String SERVER_ID = "REVVL-ONE-TAP/3.4";
    private enum DashboardState { CURRENT, OCCUPIED, NOT_RUNNING }
    private final Handler ui = new Handler(Looper.getMainLooper());
    private final ExecutorService checks = Executors.newSingleThreadExecutor();
    private TextView status;
    private Button retry;
    private Button openTermux;
    private boolean visible = false;
    private boolean opened = false;
    private boolean ready = false;
    private int generation = 0;

    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        getWindow().setStatusBarColor(Color.rgb(8,17,31));
        getWindow().setNavigationBarColor(Color.rgb(8,17,31));
        layout();
        start();
    }
    @Override public void onResume() {
        super.onResume();
        visible = true;
        if (ready && !opened) launchBrowser();
    }
    @Override public void onPause() { visible = false; super.onPause(); }
    @Override public void onDestroy() {
        generation++;
        ui.removeCallbacksAndMessages(null);
        checks.shutdownNow();
        super.onDestroy();
    }
    private int dp(int n) {
        return (int)(n*getResources().getDisplayMetrics().density+0.5f);
    }
    private Button makeButton(String title, Runnable callback) {
        Button b = new Button(this);
        b.setText(title);
        b.setAllCaps(false);
        b.setTextColor(Color.WHITE);
        b.setBackgroundTintList(android.content.res.ColorStateList.valueOf(Color.rgb(27,61,83)));
        LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,dp(54));
        lp.topMargin=dp(16);
        b.setLayoutParams(lp);
        b.setOnClickListener(v -> callback.run());
        return b;
    }
    private void layout() {
        LinearLayout l = new LinearLayout(this);
        l.setOrientation(LinearLayout.VERTICAL);
        l.setGravity(Gravity.CENTER_HORIZONTAL);
        l.setPadding(dp(23),dp(52),dp(23),dp(25));
        l.setBackgroundColor(Color.rgb(8,17,31));
        TextView title = new TextView(this);
        title.setText("REVVL\nSUPER TABLET");
        title.setTextSize(32);
        title.setTypeface(null,1);
        title.setGravity(Gravity.CENTER);
        title.setTextColor(Color.WHITE);
        l.addView(title,new LinearLayout.LayoutParams(-1,-2));
        TextView description=new TextView(this);
        description.setText("One tap • Start dashboard • Open Chrome");
        description.setGravity(Gravity.CENTER);
        description.setTextSize(15);
        description.setTextColor(Color.rgb(101,228,187));
        LinearLayout.LayoutParams descLp=new LinearLayout.LayoutParams(-1,-2);
        descLp.topMargin=dp(22);
        l.addView(description,descLp);
        ProgressBar p=new ProgressBar(this);
        LinearLayout.LayoutParams pLp=new LinearLayout.LayoutParams(dp(50),dp(50));
        pLp.topMargin=dp(52);
        pLp.bottomMargin=dp(26);
        l.addView(p,pLp);
        status=new TextView(this);
        status.setTextSize(16);
        status.setTextColor(Color.WHITE);
        status.setGravity(Gravity.CENTER);
        l.addView(status,new LinearLayout.LayoutParams(-1,-2));
        retry=makeButton("Retry dashboard launch",this::start);
        openTermux=makeButton("Open Linux tools in Termux",this::openTermux);
        l.addView(retry);
        l.addView(openTermux);
        setContentView(l);
    }
    private void start() {
        generation++;
        final int id=generation;
        ready=false; opened=false;
        retry.setVisibility(View.GONE);
        openTermux.setVisibility(View.GONE);
        status.setText("Checking your existing dashboard...");
        checks.execute(() -> {
            DashboardState result=inspectDashboard();
            ui.post(() -> {
                if (id!=generation || isFinishing()) return;
                if (result == DashboardState.CURRENT) onReady();
                else if (result == DashboardState.OCCUPIED) showPortConflict();
                else startOwnServer(id);
            });
        });
    }
    private DashboardState inspectDashboard() {
        HttpURLConnection c=null;
        try {
            c=(HttpURLConnection)new URL(URL).openConnection();
            c.setConnectTimeout(850);
            c.setReadTimeout(950);
            c.setRequestMethod("GET");
            int code=c.getResponseCode();
            String server=c.getHeaderField("X-REVVL-Server");
            if (code==200 && SERVER_ID.equals(server))
                return DashboardState.CURRENT;
            // Something is running on the original browser-storage origin, but this app
            // cannot safely claim it or silently show outdated dashboard assets.
            return DashboardState.OCCUPIED;
        } catch (Exception e) {
            return DashboardState.NOT_RUNNING;
        } finally { if (c!=null) c.disconnect(); }
    }
    private void showPortConflict() {
        ready=false;
        status.setText("Another service is using 127.0.0.1:8766. It may be the older Termux dashboard. Stop that old server in Termux, then tap Retry. Do not uninstall or clear Chrome storage: your saved Drama Studio project uses this address.");
        retry.setVisibility(View.VISIBLE);
        openTermux.setVisibility(View.VISIBLE);
    }
    private void startOwnServer(int id) {
        status.setText("Starting your REVVL dashboard locally...");
        try {
            Intent i=new Intent(this, DashboardService.class);
            startForegroundService(i);
        } catch (Exception e) {
            status.setText("Could not start dashboard: "+e.getClass().getSimpleName()+". Try Retry, or open Termux for diagnostics.");
            retry.setVisibility(View.VISIBLE);
            openTermux.setVisibility(View.VISIBLE);
            return;
        }
        poll(id,0);
    }
    private void poll(int id, int attempt) {
        if (id!=generation || isFinishing()) return;
        if (attempt>38) {
            status.setText("Dashboard did not start. Your original Termux setup is untouched.");
            retry.setVisibility(View.VISIBLE);
            openTermux.setVisibility(View.VISIBLE);
            return;
        }
        checks.execute(() -> {
            DashboardState result=inspectDashboard();
            ui.post(() -> {
                if (id!=generation || isFinishing()) return;
                if (result==DashboardState.CURRENT) onReady();
                else if (result==DashboardState.OCCUPIED) showPortConflict();
                else ui.postDelayed(() -> poll(id,attempt+1),500);
            });
        });
    }
    private void onReady() {
        ready=true;
        status.setText("Dashboard ready. Opening Chrome...");
        if (visible) launchBrowser();
    }
    private void launchBrowser() {
        if (!visible || opened) return;
        Intent view=new Intent(Intent.ACTION_VIEW,Uri.parse(URL));
        view.addCategory(Intent.CATEGORY_BROWSABLE);
        view.setPackage("com.android.chrome");
        try {
            startActivity(view);
            opened=true;
            finish();
        } catch (ActivityNotFoundException noChrome) {
            view.setPackage(null);
            try {
                startActivity(view); opened=true; finish();
            } catch (Exception e) { browserError(); }
        } catch (Exception e) { browserError(); }
    }
    private void browserError() {
        status.setText("Dashboard is running. Open this address in Chrome:\n"+URL);
        retry.setVisibility(View.VISIBLE);
        openTermux.setVisibility(View.VISIBLE);
    }
    private void openTermux() {
        Intent i=getPackageManager().getLaunchIntentForPackage("com.termux");
        if(i!=null) startActivity(i);
        else status.setText("Termux isn't installed, but the local REVVL dashboard can still run.");
    }
}
