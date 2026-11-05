package com.revvl.supertablet;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
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

public final class MainActivity extends Activity {
    private static final String DASHBOARD = "http://127.0.0.1:8766/REVVL_Super_Tablet_v2.html";
    private static final String PERMISSION = "com.termux.permission.RUN_COMMAND";
    private static final String SCRIPT = "/data/data/com.termux/files/home/supertab/bin/REVVL-services.sh";
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private TextView status;
    private Button retry, permissions, openTermux;
    private boolean visible = false;
    private boolean ready = false;
    private boolean browserOpened = false;
    private int generation = 0;
    private int attempts = 0;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().setStatusBarColor(Color.rgb(8,17,31));
        getWindow().setNavigationBarColor(Color.rgb(8,17,31));
        createView();
        begin();
    }

    @Override protected void onResume() {
        super.onResume();
        visible = true;
        if (ready && !browserOpened) launchBrowser();
    }

    @Override protected void onPause() {
        visible = false;
        super.onPause();
    }

    @Override protected void onDestroy() {
        generation++;
        handler.removeCallbacksAndMessages(null);
        executor.shutdownNow();
        super.onDestroy();
    }

    private int dp(int value) {
        return (int)(value*getResources().getDisplayMetrics().density+0.5f);
    }

    private Button button(String text, Runnable callback) {
        Button b = new Button(this);
        b.setText(text);
        b.setAllCaps(false);
        b.setTextColor(Color.WHITE);
        b.setBackgroundTintList(android.content.res.ColorStateList.valueOf(Color.rgb(26,59,82)));
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(-1,dp(52));
        lp.topMargin = dp(14);
        b.setLayoutParams(lp);
        b.setOnClickListener(v -> callback.run());
        return b;
    }

    private void createView() {
        LinearLayout pane = new LinearLayout(this);
        pane.setOrientation(LinearLayout.VERTICAL);
        pane.setGravity(Gravity.CENTER_HORIZONTAL);
        pane.setPadding(dp(24),dp(54),dp(24),dp(24));
        pane.setBackgroundColor(Color.rgb(8,17,31));
        TextView title = new TextView(this);
        title.setText("REVVL\nSUPER TABLET");
        title.setTextSize(31);
        title.setTypeface(null, 1);
        title.setGravity(Gravity.CENTER);
        title.setTextColor(Color.WHITE);
        pane.addView(title,new LinearLayout.LayoutParams(-1,-2));
        TextView caption = new TextView(this);
        caption.setText("One tap • Connect services • Open dashboard");
        caption.setTextSize(14);
        caption.setGravity(Gravity.CENTER);
        caption.setTextColor(Color.rgb(103,226,185));
        LinearLayout.LayoutParams captionLp=new LinearLayout.LayoutParams(-1,-2);
        captionLp.topMargin=dp(18);
        pane.addView(caption,captionLp);
        ProgressBar spinner=new ProgressBar(this);
        LinearLayout.LayoutParams spinnerLp=new LinearLayout.LayoutParams(dp(50),dp(50));
        spinnerLp.topMargin=dp(42);
        spinnerLp.bottomMargin=dp(20);
        pane.addView(spinner,spinnerLp);
        status=new TextView(this);
        status.setTextColor(Color.WHITE);
        status.setTextSize(16);
        status.setGravity(Gravity.CENTER);
        pane.addView(status,new LinearLayout.LayoutParams(-1,-2));
        retry=button("Retry launch",this::begin);
        permissions=button("Grant Termux permission",this::openSettings);
        openTermux=button("Open Termux",this::openTermux);
        pane.addView(retry);
        pane.addView(permissions);
        pane.addView(openTermux);
        setContentView(pane);
    }

    private void message(String text) { status.setText(text); }

    private void begin() {
        generation++;
        final int id=generation;
        ready=false;
        browserOpened=false;
        attempts=0;
        retry.setVisibility(View.GONE);
        permissions.setVisibility(View.GONE);
        openTermux.setVisibility(View.GONE);
        message("Checking local dashboard...");
        executor.execute(() -> {
            boolean running=checkDashboard();
            handler.post(() -> {
                if (id!=generation || isFinishing()) return;
                if (running && checkSelfPermission(PERMISSION)!=PackageManager.PERMISSION_GRANTED) onReady();
                else startServices();
            });
        });
    }

    private boolean checkDashboard() {
        HttpURLConnection c=null;
        try {
            c=(HttpURLConnection)new URL(DASHBOARD).openConnection();
            c.setConnectTimeout(600);
            c.setReadTimeout(750);
            c.setInstanceFollowRedirects(false);
            c.setRequestMethod("GET");
            int code=c.getResponseCode();
            return code==200 && (c.getContentType()==null || c.getContentType().contains("text/html"));
        } catch (Exception e) { return false; }
        finally { if(c!=null)c.disconnect(); }
    }

    private void startServices() {
        if (checkSelfPermission(PERMISSION)!=PackageManager.PERMISSION_GRANTED) {
            message("Allow this launcher to run commands in Termux. This permission is needed only when starting the dashboard services.");
            permissions.setVisibility(View.VISIBLE);
            retry.setVisibility(View.VISIBLE);
            requestPermissions(new String[]{PERMISSION},615);
            return;
        }
        try {
            Intent i=new Intent("com.termux.RUN_COMMAND");
            i.setClassName("com.termux","com.termux.app.RunCommandService");
            i.putExtra("com.termux.RUN_COMMAND_PATH","/data/data/com.termux/files/usr/bin/bash");
            i.putExtra("com.termux.RUN_COMMAND_ARGUMENTS",new String[]{SCRIPT});
            i.putExtra("com.termux.RUN_COMMAND_WORKDIR","/data/data/com.termux/files/home");
            i.putExtra("com.termux.RUN_COMMAND_BACKGROUND",true);
            startService(i);
        } catch (Exception error) {
            message("Termux could not start: "+error.getClass().getSimpleName()+". Check additional permissions and allow-external-apps=true.");
            retry.setVisibility(View.VISIBLE);
            permissions.setVisibility(View.VISIBLE);
            openTermux.setVisibility(View.VISIBLE);
            return;
        }
        message("Starting your REVVL services...");
        poll(generation);
    }

    private void poll(int id) {
        if (isFinishing() || id!=generation) return;
        if (++attempts>45) {
            message("The dashboard did not respond. Check the Termux setup and tap Retry.");
            retry.setVisibility(View.VISIBLE);
            permissions.setVisibility(View.VISIBLE);
            openTermux.setVisibility(View.VISIBLE);
            return;
        }
        executor.execute(() -> {
            boolean running=checkDashboard();
            handler.post(() -> {
                if (id!=generation || isFinishing()) return;
                if (running) onReady();
                else handler.postDelayed(() -> poll(id),700);
            });
        });
    }

    private void onReady() {
        ready=true;
        message("Dashboard ready. Opening Chrome...");
        if (visible) launchBrowser();
    }

    private void launchBrowser() {
        if (browserOpened || !visible) return;
        Intent intent=new Intent(Intent.ACTION_VIEW,Uri.parse(DASHBOARD));
        intent.addCategory(Intent.CATEGORY_BROWSABLE);
        intent.setPackage("com.android.chrome");
        try {
            startActivity(intent);
            browserOpened=true;
            finish();
        } catch (ActivityNotFoundException noChrome) {
            intent.setPackage(null);
            try {
                startActivity(intent);
                browserOpened=true;
                finish();
            } catch (Exception error) { onBrowserError(); }
        } catch (Exception error) { onBrowserError(); }
    }

    private void onBrowserError() {
        message("Dashboard is ready; open this address in Chrome: "+DASHBOARD);
        retry.setVisibility(View.VISIBLE);
    }

    @Override public void onRequestPermissionsResult(int code,String[] p,int[] results) {
        super.onRequestPermissionsResult(code,p,results);
        if(code!=615) return;
        if(results.length>0 && results[0]==PackageManager.PERMISSION_GRANTED) begin();
        else {
            message("Use Android Settings → Apps → REVVL Super Tablet → Permissions → Additional permissions, then allow Run commands in Termux environment.");
            retry.setVisibility(View.VISIBLE);
            permissions.setVisibility(View.VISIBLE);
            openTermux.setVisibility(View.VISIBLE);
        }
    }

    private void openSettings() {
        startActivity(new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS,Uri.parse("package:"+getPackageName())));
    }

    private void openTermux() {
        Intent launch=getPackageManager().getLaunchIntentForPackage("com.termux");
        if (launch!=null) startActivity(launch);
        else message("Termux is unavailable. Keep your installed Termux app and its files.");
    }
}
