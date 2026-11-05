package com.revvl.supertablet;

import org.json.JSONObject;
import org.json.JSONArray;
import javax.net.ssl.HttpsURLConnection;
import java.net.InetAddress;
import java.net.Inet4Address;
import java.net.Inet6Address;
import java.net.Socket;
import java.net.URL;
import java.net.URI;
import java.security.cert.X509Certificate;
import java.security.cert.Certificate;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.Locale;
import java.util.regex.Pattern;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Deliberately bounded, read-only, user-initiated security diagnostics.
 * No shell execution, authentication attempts, scanning ranges, or exploits.
 * Only public DNS hostnames are accepted for remote checks. Local health checks
 * are restricted to a fixed list of REVVL service ports.
 */
public final class SecurityTools {
    private SecurityTools(){}
    private static final Pattern DOMAIN=Pattern.compile("(?i)^(?=.{4,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\\.)+[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?$");
    private static final AtomicLong LAST_REQUEST=new AtomicLong(0);
    private static final String[] SECURITY_HEADERS={
        "Strict-Transport-Security","Content-Security-Policy","X-Content-Type-Options",
        "Referrer-Policy","Permissions-Policy","X-Frame-Options"
    };
    private static String host(String supplied) throws Exception {
        if(supplied==null)throw new Exception("Enter an authorized website hostname.");
        String name=supplied.trim().toLowerCase(Locale.US);
        if(name.startsWith("https://"))name=name.substring(8);
        if(name.endsWith("/"))name=name.substring(0,name.length()-1);
        if(!DOMAIN.matcher(name).matches() || name.contains("/") || name.contains("@")
            || name.endsWith(".local") || name.endsWith(".localhost") || name.endsWith(".internal")
            || name.endsWith(".lan") || name.endsWith(".home") || name.endsWith(".test")
            || name.endsWith(".invalid"))throw new Exception("Use a public domain, such as example.com. IPs, ports, paths and local names are blocked.");
        InetAddress[] records=InetAddress.getAllByName(name);
        if(records.length==0)throw new Exception("Domain has no DNS addresses.");
        for(InetAddress addr:records)if(!isPublicAddress(addr))
            throw new Exception("Domain resolves to a private, reserved, or local address. This tool only tests public websites.");
        return name;
    }
    private static boolean isPublicAddress(InetAddress a){
        if(a.isAnyLocalAddress()||a.isLoopbackAddress()||a.isSiteLocalAddress()
            ||a.isLinkLocalAddress()||a.isMulticastAddress())return false;
        byte[] b=a.getAddress();
        if(a instanceof Inet4Address){
            int x=b[0]&255,y=b[1]&255,z=b[2]&255;
            if(x==0||x==10||x==127||x>=224||x==169&&y==254
                ||x==100&&y>=64&&y<=127||x==172&&y>=16&&y<=31
                ||x==192&&(y==168||y==0||y==0&&z==0||y==0&&z==2)
                ||x==198&&(y==18||y==19||y==51&&z==100)
                ||x==203&&y==0&&z==113
                ||x==192&&y==0&&z==2||x==192&&y==88&&z==99
                ||x==255)return false;
        }else if(a instanceof Inet6Address){
            int x=b[0]&255;
            if((x&0xfe)==0xfc || (x==0x20&&(b[1]&255)==0x01&&(b[2]&255)==0x0d&&(b[3]&255)==0xb8))return false;
        }
        return true;
    }
    public static JSONObject run(JSONObject request)throws Exception {
        String tool=request.optString("tool","");
        if(!tool.equals("dns")&&!tool.equals("tls")&&!tool.equals("headers")&&!tool.equals("local"))
            throw new Exception("Unknown or unsupported tool.");
        long now=System.currentTimeMillis();
        long previous=LAST_REQUEST.get();
        if(now-previous<750)throw new Exception("Please wait a moment between scans.");
        LAST_REQUEST.set(now);
        JSONObject out=new JSONObject().put("tool",tool).put("executed_at", Instant.now().toString())
            .put("mode","read_only").put("source","REVVL Android localhost service");
        if(tool.equals("local")){
            JSONArray ports=new JSONArray();
            int[] allowed={8770,8788,8767};
            String[] labels={"3D Character Engine","Recovery dashboard","Optional AI bridge"};
            for(int i=0;i<allowed.length;i++){
                boolean reachable;
                try(Socket socket=new Socket()){
                    socket.connect(new java.net.InetSocketAddress("127.0.0.1",allowed[i]),800);
                    reachable=true;
                }catch(Exception e){reachable=false;}
                ports.put(new JSONObject().put("name",labels[i]).put("port",allowed[i]).put("reachable",reachable));
            }
            return out.put("services",ports).put("explanation","A reachable port proves only that a listener exists, not that all service features work.");
        }
        String target=host(request.optString("target",""));
        out.put("target",target);
        if(tool.equals("dns")){
            JSONArray rows=new JSONArray();
            for(InetAddress a:InetAddress.getAllByName(target)){
                if(!isPublicAddress(a))throw new Exception("Non-public DNS answer rejected.");
                rows.put(new JSONObject().put("type",a instanceof Inet4Address?"A":"AAAA").put("address",a.getHostAddress()));
            }
            return out.put("records",rows).put("explanation","Public DNS addresses, not proof of vulnerabilities.");
        }
        HttpsURLConnection conn=null;
        try{
            URL url=new URL("https://"+target+"/");
            conn=(HttpsURLConnection)url.openConnection();
            conn.setInstanceFollowRedirects(false);
            conn.setConnectTimeout(4500);
            conn.setReadTimeout(4500);
            conn.setRequestMethod("HEAD");
            conn.setUseCaches(false);
            conn.setRequestProperty("User-Agent","REVVL-Security-Toolbox/1.0 (owner-authorized passive check)");
            int status=conn.getResponseCode();
            out.put("https_status",status);
            if(tool.equals("headers")){
                JSONObject checked=new JSONObject();
                int present=0;
                for(String key:SECURITY_HEADERS){
                    String value=conn.getHeaderField(key);
                    if(value!=null&&!value.isEmpty())present++;
                    checked.put(key,value==null?JSONObject.NULL:value.substring(0,Math.min(350,value.length())));
                }
                return out.put("security_headers",checked).put("present",present)
                    .put("checked",SECURITY_HEADERS.length)
                    .put("explanation","A missing header is a review item, not evidence of an exploitable vulnerability. HEAD responses may differ from GET.");
            }
            Certificate[] chain=conn.getServerCertificates();
            if(chain.length==0||!(chain[0] instanceof X509Certificate))throw new Exception("No X.509 server certificate returned.");
            X509Certificate cert=(X509Certificate)chain[0];
            byte[] fingerprint=MessageDigest.getInstance("SHA-256").digest(cert.getEncoded());
            StringBuilder sb=new StringBuilder();
            for(byte b:fingerprint)sb.append(String.format(Locale.US,"%02x",b&255));
            return out.put("subject",cert.getSubjectX500Principal().getName())
                .put("issuer",cert.getIssuerX500Principal().getName())
                .put("not_before",cert.getNotBefore().toInstant().toString())
                .put("not_after",cert.getNotAfter().toInstant().toString())
                .put("sha256_fingerprint",sb.toString())
                .put("days_until_expiry",(cert.getNotAfter().getTime()-System.currentTimeMillis())/86400000L)
                .put("explanation","Certificate details from an HTTPS connection with platform certificate validation.");
        }finally{if(conn!=null)conn.disconnect();}
    }
}
