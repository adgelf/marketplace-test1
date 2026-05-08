package com.mirantis.massdownloader.salesforce;

import com.mirantis.massdownloader.config.AppConfig;
import org.apache.http.HttpEntity;
import org.apache.http.HttpStatus;
import org.apache.http.client.config.RequestConfig;
import org.apache.http.client.methods.CloseableHttpResponse;
import org.apache.http.client.methods.HttpGet;
import org.apache.http.client.methods.HttpPost;
import org.apache.http.client.entity.UrlEncodedFormEntity;
import org.apache.http.impl.client.CloseableHttpClient;
import org.apache.http.impl.client.HttpClients;
import org.apache.http.message.BasicHeader;
import org.apache.http.message.BasicNameValuePair;
import org.apache.http.util.EntityUtils;
import org.json.JSONArray;
import org.json.JSONObject;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Semaphore;

public class SalesforceClient {

    private static final Logger LOGGER = LogManager.getLogger(SalesforceClient.class);

    private final CloseableHttpClient httpClient;
    private final AppConfig config;
    private volatile String accessToken;
    private volatile String instanceUrl;
    private volatile Instant tokenExpiry;
    private final Semaphore tokenSemaphore;

    public SalesforceClient(AppConfig config) {
        this.config = config;
        RequestConfig requestConfig = RequestConfig.custom()
                .setConnectTimeout(120_000)
                .setConnectionRequestTimeout(120_000)
                .setSocketTimeout(120_000)
                .build();
        this.httpClient = HttpClients.custom()
                .setDefaultRequestConfig(requestConfig)
                .disableContentCompression()
                .build();
        this.tokenSemaphore = new Semaphore(1);
    }

    public void close() {
        try {
            this.httpClient.close();
        } catch (IOException e) {
            LOGGER.warn("Unable to close Salesforce HTTP client", e);
        }
    }

    public JSONArray query(String soql) throws SalesforceException {
        ensureAuthenticated();
        List<JSONObject> records = new ArrayList<>();
        String nextUrl = buildQueryUrl(soql);
        while (nextUrl != null) {
            HttpGet httpGet = new HttpGet(nextUrl);
            httpGet.addHeader(new BasicHeader("Authorization", this.accessToken));
            try (CloseableHttpResponse response = this.httpClient.execute(httpGet)) {
                int statusCode = response.getStatusLine().getStatusCode();
                String body = EntityUtils.toString(response.getEntity());
                if (statusCode == HttpStatus.SC_UNAUTHORIZED) {
                    LOGGER.warn("Salesforce query unauthorized, refreshing token");
                    invalidateToken();
                    ensureAuthenticated();
                    nextUrl = buildQueryUrl(soql);
                    continue;
                }
                if (statusCode != HttpStatus.SC_OK) {
                    throw new SalesforceException("Query failed with code " + statusCode + ": " + body);
                }
                JSONObject payload = new JSONObject(body);
                JSONArray chunk = payload.getJSONArray("records");
                for (int i = 0; i < chunk.length(); i++) {
                    records.add(chunk.getJSONObject(i));
                }
                nextUrl = payload.optString("nextRecordsUrl", null);
                if (nextUrl != null && !nextUrl.isEmpty()) {
                    nextUrl = this.instanceUrl + nextUrl;
                } else {
                    nextUrl = null;
                }
            } catch (IOException e) {
                throw new SalesforceException("Error executing query", e);
            }
        }
        JSONArray result = new JSONArray();
        result.putAll(records);
        return result;
    }

    public void downloadFile(String fileId, Path target) throws SalesforceException {
        ensureAuthenticated();
        String apiBase = "/services/data/v" + this.config.require("sf.salesforce.api.version");
        String path;
        if (fileId.startsWith("068")) {
            path = apiBase + "/sobjects/ContentVersion/" + fileId + "/VersionData";
        } else if (fileId.startsWith("00P")) {
            path = apiBase + "/sobjects/Attachment/" + fileId + "/Body";
        } else {
            throw new SalesforceException("Unsupported file id prefix for " + fileId);
        }
        HttpGet httpGet = new HttpGet(this.instanceUrl + path);
        httpGet.addHeader(new BasicHeader("Authorization", this.accessToken));
        try (CloseableHttpResponse response = this.httpClient.execute(httpGet)) {
            int statusCode = response.getStatusLine().getStatusCode();
            if (statusCode == HttpStatus.SC_UNAUTHORIZED) {
                invalidateToken();
                ensureAuthenticated();
                downloadFile(fileId, target);
                return;
            }
            if (statusCode != HttpStatus.SC_OK) {
                String body = EntityUtils.toString(response.getEntity());
                throw new SalesforceException("Failed to download file " + fileId + ": " + body);
            }
            HttpEntity entity = response.getEntity();
            try (InputStream stream = entity.getContent()) {
                Files.copy(stream, target, StandardCopyOption.REPLACE_EXISTING);
            }
        } catch (IOException e) {
            throw new SalesforceException("Error downloading file " + fileId, e);
        }
    }

    private String buildQueryUrl(String soql) {
        String version = this.config.require("sf.salesforce.api.version");
        String encoded = java.net.URLEncoder.encode(soql, java.nio.charset.StandardCharsets.UTF_8);
        return this.instanceUrl + "/services/data/v" + version + "/query?q=" + encoded;
    }

    private void ensureAuthenticated() throws SalesforceException {
        if (this.accessToken != null && this.tokenExpiry != null && Instant.now().isBefore(this.tokenExpiry)) {
            return;
        }
        this.tokenSemaphore.acquireUninterruptibly();
        try {
            if (this.accessToken != null && this.tokenExpiry != null && Instant.now().isBefore(this.tokenExpiry)) {
                return;
            }
            authenticate();
        } finally {
            this.tokenSemaphore.release();
        }
    }

    private void authenticate() throws SalesforceException {
        String tokenUrl = this.config.require("sf.oauth.base-url");
        HttpPost post = new HttpPost(tokenUrl);
        List<BasicNameValuePair> form = new ArrayList<>();
        form.add(new BasicNameValuePair("grant_type", "password"));
        form.add(new BasicNameValuePair("client_id", this.config.require("sf.client.id")));
        form.add(new BasicNameValuePair("client_secret", this.config.require("sf.client.secret")));
        form.add(new BasicNameValuePair("username", this.config.require("sf.username")));
        String password = this.config.require("sf.password") + this.config.require("sf.security.token");
        form.add(new BasicNameValuePair("password", password));
        try {
            post.setEntity(new UrlEncodedFormEntity(form, java.nio.charset.StandardCharsets.UTF_8));
            try (CloseableHttpResponse response = this.httpClient.execute(post)) {
                int statusCode = response.getStatusLine().getStatusCode();
                String body = EntityUtils.toString(response.getEntity());
                if (statusCode != HttpStatus.SC_OK) {
                    throw new SalesforceException("Authentication failed: " + body);
                }
                JSONObject payload = new JSONObject(body);
                this.accessToken = payload.getString("token_type") + " " + payload.getString("access_token");
                String instance = payload.getString("instance_url");
                this.instanceUrl = instance;
                long expiresIn = payload.optLong("expires_in", 3600);
                this.tokenExpiry = Instant.now().plusSeconds(Math.max(300, expiresIn - 120));
                LOGGER.info("Authenticated with Salesforce, instance {}", instance);
            }
        } catch (IOException e) {
            throw new SalesforceException("Authentication error", e);
        }
    }

    private void invalidateToken() {
        this.accessToken = null;
        this.tokenExpiry = null;
    }

    public static class SalesforceException extends Exception {
        public SalesforceException(String message) {
            super(message);
        }

        public SalesforceException(String message, Throwable cause) {
            super(message, cause);
        }
    }
}


