package com.mirantis.massdownloader.config;

import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Properties;

public final class AppConfig {

    private final Properties properties;

    private AppConfig(Properties properties) {
        this.properties = properties;
    }

    public static AppConfig load(String path) throws IOException {
        Properties props = new Properties();
        if (path != null && !path.isEmpty()) {
            Path configPath = Path.of(path);
            if (!Files.exists(configPath)) {
                throw new IOException("Configuration file not found: " + path);
            }
            try (InputStream stream = new FileInputStream(configPath.toFile())) {
                props.load(stream);
            }
        }
        overlayEnvironment(props);
        return new AppConfig(props);
    }

    private static void overlayEnvironment(Properties props) {
        Map<String, String> env = System.getenv();
        for (Map.Entry<String, String> entry : env.entrySet()) {
            String key = normalizeEnvKey(entry.getKey());
            if (key != null) {
                props.setProperty(key, entry.getValue());
            }
        }
    }

    private static String normalizeEnvKey(String envKey) {
        if (!envKey.startsWith("SF_") && !envKey.startsWith("BOX_") && !envKey.startsWith("EXPORT_")) {
            return null;
        }
        return envKey.toLowerCase(Locale.ROOT).replace('_', '.');
    }

    public String require(String key) {
        String value = this.properties.getProperty(key);
        if (value == null || value.isEmpty()) {
            throw new IllegalArgumentException("Missing required configuration property: " + key);
        }
        return value;
    }

    public String optional(String key, String defaultValue) {
        return this.properties.getProperty(key, defaultValue);
    }

    public int optionalInt(String key, int defaultValue) {
        String raw = this.properties.getProperty(key);
        if (raw == null || raw.isBlank()) {
            return defaultValue;
        }
        return Integer.parseInt(raw.trim());
    }

    public File optionalDirectory(String key, File defaultDir) {
        String raw = this.properties.getProperty(key);
        if (raw == null || raw.isBlank()) {
            return defaultDir;
        }
        return new File(raw.trim());
    }

    public Properties asProperties() {
        Properties copy = new Properties();
        copy.putAll(this.properties);
        return copy;
    }

    public String get(String key) {
        return this.properties.getProperty(key);
    }
}


