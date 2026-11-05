package com.revvl.supertablet;

import android.app.Service;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Intent;
import android.graphics.Color;
import android.os.IBinder;
import android.os.Build;
import android.util.Log;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.InetSocketAddress;
import java.net.InetAddress;
import java.net.BindException;
import java.nio.charset.StandardCharsets;
import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.io.ByteArrayOutputStream;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * A loopback-only, user-started foreground server.
 * Preserves Chrome origin http://127.0.0.1:8766 for existing saved projects.
 * It does not execute any Termux command, access app credentials, or bind to Wi-Fi.
 */
public final class DashboardService extends Service {
    public static final String DASHBOARD = "http://127.0.0.1:8766/REVVL_Super_Tablet_v2.html";
    private static final String TAG = "REVVL-DashboardService";
    private static final String CHANNEL = "revvl_dashboard";
    private static final int NOTIFICATION_ID = 8766;
    private final ExecutorService workers = Executors.newFixedThreadPool(3);
    private ServerSocket socket;
    private Thread acceptThread;
    private volatile boolean stopping = false;
    private byte[] page;
    private byte[] bridgePage;

    @Override public void onCreate() {
        super.onCreate();
        try (InputStream in = getAssets().open("REVVL_Super_Tablet_v2.html");
             ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] b = new byte[8192];
            int n;
            while ((n = in.read(b)) >= 0) out.write(b, 0, n);
            page = out.toByteArray();
        } catch (Exception e) {
            Log.e(TAG, "Dashboard asset missing", e);
            stopSelf();
        }
    }

    private void loadBridge() {
        try (InputStream in = getAssets().open("REVVL_Nia_Device_Bridge.html");
             ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] b = new byte[4096]; int n;
            while ((n = in.read(b)) != -1) out.write(b, 0, n);
            bridgePage = out.toByteArray();
        } catch (Exception e) {
            Log.e(TAG, "Bridge asset missing", e);
        }
    }
    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        if (page == null || page.length == 0) { stopSelf(); return START_NOT_STICKY; }
        if (bridgePage == null) loadBridge();
        NotificationManager nm = getSystemService(NotificationManager.class);
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationChannel channel = new NotificationChannel(CHANNEL, "REVVL local dashboard", NotificationManager.IMPORTANCE_LOW);
            channel.setDescription("Keeps your Super Tablet dashboard available in Chrome");
            nm.createNotificationChannel(channel);
        }
        Intent open = new Intent(this, MainActivity.class);
        PendingIntent pi = PendingIntent.getActivity(this, 0, open, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        Notification notification = new Notification.Builder(this, CHANNEL)
            .setSmallIcon(android.R.drawable.ic_menu_view)
            .setContentTitle("REVVL Super Tablet")
            .setContentText("Dashboard available locally at 127.0.0.1:8766")
            .setColor(Color.rgb(101,228,187))
            .setContentIntent(pi)
            .setOngoing(true).build();
        try {
            startForeground(NOTIFICATION_ID, notification);
        } catch (RuntimeException e) {
            Log.e(TAG,"Cannot start foreground service",e);
            stopSelf();
            return START_NOT_STICKY;
        }
        if (acceptThread == null) {
            stopping = false;
            acceptThread = new Thread(this::serve, "revvl-http-server");
            acceptThread.start();
        }
        return START_STICKY;
    }

    private void serve() {
        try (ServerSocket s = new ServerSocket()) {
            socket = s;
            s.setReuseAddress(true);
            s.bind(new InetSocketAddress(InetAddress.getByName("127.0.0.1"), 8766), 8);
            Log.i(TAG, "Started loopback dashboard on 8766");
            while (!stopping && !s.isClosed()) {
                Socket client = s.accept();
                workers.execute(() -> handle(client));
            }
        } catch (BindException alreadyRunning) {
            // Termux already owns 8766; let it serve the unchanged original page.
            Log.i(TAG, "Port 8766 already served by Termux or another app");
            stopSelf();
        } catch (Exception e) {
            if (!stopping) Log.e(TAG,"Local server stopped",e);
            stopSelf();
        }
    }

    private void handle(Socket client) {
        try (Socket c = client) {
            c.setSoTimeout(2000);
            BufferedReader input = new BufferedReader(new InputStreamReader(c.getInputStream(), StandardCharsets.ISO_8859_1));
            String line = input.readLine();
            if (line == null) return;
            String[] parts = line.split(" ", 3);
            boolean get = parts.length > 1 && ("GET".equals(parts[0]) || "HEAD".equals(parts[0]));
            boolean dashboard = get && ("/".equals(parts[1]) || "/REVVL_Super_Tablet_v2.html".equals(parts[1]) || parts[1].startsWith("/REVVL_Super_Tablet_v2.html?"));
            boolean bridge = get && bridgePage != null &&
                ("/REVVL_Nia_Device_Bridge.html".equals(parts[1]) || parts[1].startsWith("/REVVL_Nia_Device_Bridge.html?"));
            byte[] body = dashboard ? page : bridge ? bridgePage : "Not found".getBytes(StandardCharsets.UTF_8);
            String status = dashboard || bridge ? "200 OK" : "404 Not Found";
            String type = dashboard || bridge ? "text/html; charset=utf-8" : "text/plain; charset=utf-8";
            OutputStream out = c.getOutputStream();
            String headers = "HTTP/1.1 " + status + "\r\nContent-Type: " + type +
              "\r\nContent-Length: " + body.length +
              "\r\nCache-Control: no-store\r\nX-Content-Type-Options: nosniff\r\nReferrer-Policy: no-referrer\r\nConnection: close\r\n\r\n";
            out.write(headers.getBytes(StandardCharsets.ISO_8859_1));
            if (get && !"HEAD".equals(parts[0])) out.write(body);
            out.flush();
        } catch (Exception e) {
            Log.w(TAG,"Could not serve request",e);
        }
    }

    @Override public void onDestroy() {
        stopping = true;
        try { if (socket != null) socket.close(); } catch (Exception ignored) {}
        workers.shutdownNow();
        super.onDestroy();
    }
    @Override public IBinder onBind(Intent intent) { return null; }
}
