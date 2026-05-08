package com.mirantis.massdownloader.util;

import java.text.Normalizer;
import java.util.regex.Pattern;

public final class NameFormatter {

    private static final int BOX_NAME_LIMIT = 255;
    private static final Pattern INVALID_CHARS = Pattern.compile("[\\\\/:*?\"<>|\n\r\t\f\u0000-\u001F]");

    private NameFormatter() {
    }

    public static String sanitize(String value) {
        if (value == null) {
            return "";
        }
        String normalized = Normalizer.normalize(value, Normalizer.Form.NFC);
        String sanitized = INVALID_CHARS.matcher(normalized).replaceAll("_");
        sanitized = sanitized.replaceAll("\\s+", " ").trim();
        return sanitized;
    }

    public static String formatFolderName(String rawName, String rawId) {
        String name = rawName != null ? sanitize(rawName) : "";
        String id = sanitizeId(rawId);
        if (name.isEmpty()) {
            // If no name, use just "[Id]"
            return "[" + id + "]";
        }
        String suffix = " [" + id + "]";
        int maxLength = Math.max(0, BOX_NAME_LIMIT - suffix.length());
        if (name.length() > maxLength) {
            name = name.substring(0, maxLength);
        }
        return name + suffix;
    }

    public static String formatFileName(String rawBaseName, String rawId, String rawExtension) {
        String base = rawBaseName != null ? sanitize(rawBaseName) : "";
        String extension = sanitizeExtension(rawExtension);
        String id = sanitizeId(rawId);
        if (base.isEmpty()) {
            // If no name, use just "[Id].extension"
            return "[" + id + "]" + extension;
        }
        String suffix = " [" + id + "]";
        int maxBaseLength = Math.max(0, BOX_NAME_LIMIT - suffix.length() - extension.length());
        if (base.length() > maxBaseLength) {
            base = base.substring(0, maxBaseLength);
        }
        return base + suffix + extension;
    }

    private static String sanitizeId(String rawId) {
        // Id should always be present for Salesforce objects. "NO_ID" is a fallback for data errors.
        if (rawId == null || rawId.isBlank()) {
            return "NO_ID";
        }
        String sanitized = INVALID_CHARS.matcher(rawId.trim()).replaceAll("_");
        return sanitized.isEmpty() ? "NO_ID" : sanitized;
    }

    private static String sanitizeExtension(String rawExtension) {
        if (rawExtension == null || rawExtension.isBlank()) {
            return "";
        }
        String value = rawExtension.startsWith(".") ? rawExtension.substring(1) : rawExtension;
        String sanitized = sanitize(value).replace(" ", "");
        return sanitized.isEmpty() ? "" : "." + sanitized;
    }
}


