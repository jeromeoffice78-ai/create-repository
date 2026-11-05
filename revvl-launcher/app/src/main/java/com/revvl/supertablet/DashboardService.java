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
 * Uses an independent Chrome origin on port 8788 to avoid the original port 8766.
 * It does not execute any Termux command, access app credentials, or bind to Wi-Fi.
 */
public final class DashboardService extends Service {
    public static final String DASHBOARD = "http://127.0.0.1:8788/REVVL_Super_Tablet_v2.html";
    private static final String TAG = "REVVL-DashboardService";
    private static final String CHANNEL = "revvl_dashboard";
    private static final int NOTIFICATION_ID = 8788;
    private final ExecutorService workers = Executors.newFixedThreadPool(3);
    private ServerSocket socket;
    private Thread acceptThread;
    private volatile boolean stopping = false;
    private byte[] page;
    private byte[] computePage;

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

    private void loadComputePage() {
        try (InputStream in = getAssets().open("REVVL_Compute_Control.html");
             ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buf = new byte[8192]; int n;
            while ((n = in.read(buf)) >= 0) out.write(buf, 0, n);
            computePage = out.toByteArray();
        } catch (Exception e) {
            Log.e(TAG, "Compute Center HTML is unavailable", e);
        }
    }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        if (page == null || page.length == 0) { stopSelf(); return START_NOT_STICKY; }
        if (computePage == null) loadComputePage();
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
            .setContentText("Dashboard available locally at 127.0.0.1:8788")
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
            s.bind(new InetSocketAddress(InetAddress.getByName("127.0.0.1"), 8788), 8);
            Log.i(TAG, "Started loopback dashboard on 8788");
            while (!stopping && !s.isClosed()) {
                Socket client = s.accept();
                workers.execute(() -> handle(client));
            }
        } catch (BindException alreadyRunning) {
            // If another app owns 8788, stop safely without opening untrusted content.
            Log.i(TAG, "Recovery port 8788 is in use; existing REVVL services are untouched");
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
            boolean compute = get && computePage != null &&
                ("/REVVL_Compute_Control.html".equals(parts[1]) ||
                 parts[1].startsWith("/REVVL_Compute_Control.html?"));
            boolean found = dashboard || compute;
            byte[] body = dashboard ? page : compute ? computePage : "Not found".getBytes(StandardCharsets.UTF_8);
            String status = found ? "200 OK" : "404 Not Found";
            String type = found ? "text/html; charset=utf-8" : "text/plain; charset=utf-8";
            OutputStream out = c.getOutputStream();
            String headers = "HTTP/1.1 " + status + "\r\nContent-Type: " + type +
              "\r\nContent-Length: " + body.length +
              "\r\nCache-Control: no-store\r\nX-REVVL-Server: REVVL-RECOVERY/3.6\r\nX-Frame-Options: SAMEORIGIN\r\nX-Content-Type-Options: nosniff\r\nReferrer-Policy: no-referrer\r\nConnection: close\r\n\r\n";
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
