package com.revvl.supertablet.rigengine;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.graphics.Color;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.TextView;
import android.widget.LinearLayout;
import java.net.HttpURLConnection;
import java.net.URL;
import java.io.InputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.Executors;
import java.util.concurrent.ExecutorService;

/** Starts the engine with an explicit user launch, never touching Recovery app data. */
public final class EngineActivity extends Activity {
    private TextView status;
    private final Handler ui=new Handler(Looper.getMainLooper());
    private final ExecutorService worker=Executors.newSingleThreadExecutor();
    private boolean alive=true;
    private int dp(int n){return (int)(n*getResources().getDisplayMetrics().density+.5f);}
    @Override public void onCreate(Bundle state){super.onCreate(state);
        getWindow().setStatusBarColor(Color.rgb(8,18,30));
        LinearLayout panel=new LinearLayout(this);panel.setOrientation(LinearLayout.VERTICAL);panel.setPadding(dp(22),dp(35),dp(22),dp(20));panel.setBackgroundColor(Color.rgb(8,18,30));
        TextView title=new TextView(this);title.setText("REVVL 3D CHARACTER ENGINE");title.setTextSize(25);title.setTextColor(Color.WHITE);title.setGravity(Gravity.CENTER);panel.addView(title);
        status=new TextView(this);status.setTextColor(Color.rgb(112,220,183));status.setTextSize(16);status.setText("Starting the on-device rig creator…");status.setPadding(0,dp(28),0,dp(16));panel.addView(status);
        addButton(panel,"Start / Restart 3D Engine",this::startEngine);
        addButton(panel,"Open 3D Character Creator",()->open(RigService.HOME));
        addButton(panel,"Return to REVVL Recovery dashboard",()->open("http://127.0.0.1:8788/REVVL_Super_Tablet_v2.html#rigging"));
        TextView note=new TextView(this);note.setText("The rigging service runs only on this device at 127.0.0.1:8770. You can download basic rigged GLB drafts from the browser. Approved photos and Drama Studio projects remain in Recovery. Photorealistic identity reconstruction requires additional modeling and verification.");note.setTextColor(Color.rgb(194,203,217));note.setPadding(0,dp(25),0,0);panel.addView(note);
        setContentView(panel);
        startEngine();
    }
    private void addButton(LinearLayout panel,String text,Runnable action){Button b=new Button(this);b.setText(text);b.setAllCaps(false);LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,dp(56));lp.topMargin=dp(12);panel.addView(b,lp);b.setOnClickListener(v->action.run());}
    private void open(String url){Intent i=new Intent(Intent.ACTION_VIEW,Uri.parse(url));i.addCategory(Intent.CATEGORY_BROWSABLE);try{startActivity(i);}catch(Exception e){status.setText("Open Chrome manually: "+url);}}
    private void startEngine(){
        status.setText("Starting local 3D service…");
        try{startForegroundService(new Intent(this,RigService.class));}
        catch(Exception e){status.setText("Could not start service: "+e.getClass().getSimpleName());return;}
        worker.execute(()->{
            boolean ready=false;
            boolean foreign=false;
            for(int n=0;n<15&&alive&&!ready;n++){
                HttpURLConnection conn=null;
                try{
                    conn=(HttpURLConnection)new URL("http://127.0.0.1:8770/health").openConnection();
                    conn.setConnectTimeout(600);conn.setReadTimeout(600);
                    if(conn.getResponseCode()==200){
                        String mime=conn.getContentType();
                        if(mime!=null&&mime.startsWith("application/json")){
                            try(InputStream in=conn.getInputStream();ByteArrayOutputStream out=new ByteArrayOutputStream()){
                                byte[] b=new byte[512];int count;
                                while(out.size()<4096&&(count=in.read(b))!=-1)out.write(b,0,count);
                                String body=out.toString(StandardCharsets.UTF_8.name());
                                ready=body.contains("\\"service\\":\\"REVVL Native 3D Character Engine\\"")
                                    &&body.contains("\\"animation_clips\\":3")
                                    &&body.contains("\\"ok\\":true");
                                if(!ready)foreign=true;
                            }
                        } else foreign=true;
                    }else foreign=true;
                }catch(Exception ignored){}finally{if(conn!=null)conn.disconnect();}
                if(foreign)break;
                if(!ready)try{Thread.sleep(350);}catch(InterruptedException e){Thread.currentThread().interrupt();break;}
            }
            final boolean result=ready, other=foreign;
            ui.post(()->{if(alive)status.setText(result
                ?"✓ Native 3D Character Engine verified on port 8770. Open Creator or return to Recovery."
                :other
                    ?"Another Character Lab service is using port 8770. Native engine NOT verified. Stop the older Termux rig service, then tap Start/Restart, or keep using the older Lab for unapproved model review."
                    :"Port 8770 is unavailable. Tap Start / Restart, then check Android notifications for a service error.");});
        });
    }
    @Override public void onDestroy(){alive=false;worker.shutdownNow();super.onDestroy();}
}
