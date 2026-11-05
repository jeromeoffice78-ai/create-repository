package com.revvl.supertablet.rigengine;

import android.app.Service;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Intent;
import android.graphics.Color;
import android.os.IBinder;
import android.util.Log;

import java.net.ServerSocket;
import java.net.Socket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.ByteArrayOutputStream;
import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.concurrent.Executors;
import java.util.concurrent.ExecutorService;
import java.util.zip.GZIPInputStream;

/**
 * Native standalone localhost-only creator. Does not need Termux or a Python backend.
 * This app runs independently of Recovery 8788 and never reads its browser data.
 * The user can transfer an approved photo explicitly through a checked message
 * or by choosing a local file, entirely inside the phone/tablet browser.
 */
public final class RigService extends Service {
    static final String HOME = "http://127.0.0.1:8770/creator.html";
    private static final String TAG="REVVL-RigEngine";
    private static final String CHANNEL="revvl_rig_engine_local";
    private final ExecutorService workers=Executors.newFixedThreadPool(3);
    private Thread serverThread;
    private ServerSocket serverSocket;
    private volatile boolean stopping;
    private byte[] page;
    private byte[] template;

    private static byte[] readAll(InputStream stream) throws Exception {
        try (InputStream in=stream; ByteArrayOutputStream out=new ByteArrayOutputStream()) {
            byte[] buffer=new byte[8192];int n;
            while ((n=in.read(buffer))>=0)out.write(buffer,0,n);
            return out.toByteArray();
        }
    }
    @Override public void onCreate(){
        super.onCreate();
        try {
            page=readAll(getAssets().open("creator.html"));
            byte[] compressed=Base64.getDecoder().decode(new String(readAll(getAssets().open("rig_template.b64")),StandardCharsets.US_ASCII).trim());
            template=readAll(new GZIPInputStream(new ByteArrayInputStream(compressed)));
            if(template.length<10000 || template[0]!='g'||template[1]!='l'||template[2]!='T'||template[3]!='F')
                throw new IllegalStateException("Invalid built-in rigged GLB template");
        }catch(Exception e){Log.e(TAG,"Missing creator assets",e);stopSelf();}
    }
    @Override public int onStartCommand(Intent i,int flags,int startId){
        if(page==null||template==null){stopSelf();return START_NOT_STICKY;}
        NotificationManager manager=getSystemService(NotificationManager.class);
        NotificationChannel channel=new NotificationChannel(CHANNEL,"REVVL 3D Character Engine",NotificationManager.IMPORTANCE_LOW);
        channel.setDescription("Local portrait-to-rig draft creator service at 127.0.0.1:8770");
        manager.createNotificationChannel(channel);
        Intent open=new Intent(this,EngineActivity.class);
        PendingIntent pending=PendingIntent.getActivity(this,0,open,PendingIntent.FLAG_IMMUTABLE|PendingIntent.FLAG_UPDATE_CURRENT);
        Notification notification=new Notification.Builder(this,CHANNEL)
            .setSmallIcon(android.R.drawable.ic_menu_edit)
            .setContentTitle("REVVL 3D Character Engine")
            .setContentText("Local basic rig creator ready on port 8770")
            .setColor(Color.rgb(97,223,183))
            .setContentIntent(pending).setOngoing(true).build();
        try {startForeground(8770,notification);}catch(RuntimeException e){Log.e(TAG,"Foreground start failed",e);stopSelf();return START_NOT_STICKY;}
        if(serverThread==null){
            stopping=false;
            serverThread=new Thread(this::serve,"rig-engine-loopback");
            serverThread.start();
        }
        return START_STICKY;
    }
    private void serve(){
        try(ServerSocket s=new ServerSocket()){
            serverSocket=s;
            s.setReuseAddress(true);
            s.bind(new InetSocketAddress(InetAddress.getByName("127.0.0.1"),8770),10);
            Log.i(TAG,"Native offline creator ready on 8770");
            while(!stopping){
                Socket client=s.accept();
                workers.execute(()->handle(client));
            }
        }catch(Exception e){if(!stopping)Log.e(TAG,"Creator service stopped (port might be occupied)",e);stopSelf();}
    }
    private void handle(Socket connection){
        try(Socket c=connection){
            c.setSoTimeout(2000);
            BufferedReader reader=new BufferedReader(new InputStreamReader(c.getInputStream(),StandardCharsets.ISO_8859_1));
            String line=reader.readLine();
            if(line==null||line.length()>3000)return;
            String[] parts=line.split(" ",3);
            if(parts.length<2)return;
            String method=parts[0];
            boolean get="GET".equals(method),head="HEAD".equals(method);
            if(!get&&!head){send(c,"405 Method Not Allowed","text/plain; charset=utf-8","Method not allowed".getBytes(StandardCharsets.UTF_8),false);return;}
            String path=parts[1].split("\\?",2)[0];
            String type;
            byte[] body;
            if(path.equals("/")||path.equals("/creator.html")){
                type="text/html; charset=utf-8";body=page;
            }else if(path.equals("/template.glb")){
                type="model/gltf-binary";body=template;
            }else if(path.equals("/health")){
                type="application/json; charset=utf-8";
                body=("{\"ok\":true,\"service\":\"REVVL Native 3D Character Engine\",\"version\":\"1.0\",\"mode\":\"on-device offline draft rig\",\"basic_glb_export\":true,\"joints\":22,\"animation_clips\":3,\"photo_to_exact_likeness\":false,\"face_reconstruction\":false}").getBytes(StandardCharsets.UTF_8);
            }else{
                send(c,"404 Not Found","text/plain; charset=utf-8","Not found".getBytes(StandardCharsets.UTF_8),!head);return;
            }
            send(c,"200 OK",type,body,!head);
        }catch(Exception e){Log.w(TAG,"Local request aborted",e);}
    }
    private static void send(Socket c,String status,String mime,byte[] body,boolean writeBody)throws Exception{
        OutputStream out=c.getOutputStream();
        String header="HTTP/1.1 "+status+"\r\nContent-Type: "+mime+
                "\r\nContent-Length: "+body.length+
                "\r\nCache-Control: no-store\r\nX-Content-Type-Options: nosniff\r\nReferrer-Policy: no-referrer\r\nConnection: close\r\n\r\n";
        out.write(header.getBytes(StandardCharsets.ISO_8859_1));
        if(writeBody)out.write(body);
        out.flush();
    }
    @Override public void onDestroy(){
        stopping=true;
        try{if(serverSocket!=null)serverSocket.close();}catch(Exception ignored){}
        workers.shutdownNow();
        super.onDestroy();
    }
    @Override public IBinder onBind(Intent i){return null;}
}
