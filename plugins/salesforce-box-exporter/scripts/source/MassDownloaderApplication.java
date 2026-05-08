package com.mirantis.massdownloader;

import com.mirantis.massdownloader.config.AppConfig;
import com.mirantis.massdownloader.config.ExportOptions;
import com.mirantis.massdownloader.model.FileRecord;
import com.mirantis.massdownloader.service.ExportOrchestrator;
import com.mirantis.massdownloader.service.ExportOrchestrator.ExportResult;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

import org.json.JSONArray;
import org.json.JSONObject;

public class MassDownloaderApplication {

    private static final Logger LOGGER = LogManager.getLogger(MassDownloaderApplication.class);

    public static void main(String[] args) {
        try {
            if (isHelpRequested(args)) {
                printUsage();
                return;
            }
            Map<String, String> params = parseArgs(args);
            AppConfig config = AppConfig.load(resolveConfigPath(params));
            ExportOptions options = buildOptions(params);
            ExportOrchestrator orchestrator = new ExportOrchestrator(config, options);
            ExportResult result = orchestrator.export();
            LOGGER.info("Export completed: {} files processed, {} uploaded, {} skipped, {} failed",
                    result.totalProcessed(), result.totalUploaded(), result.totalSkipped(), result.totalFailed());
            result.errorReport().ifPresent(path ->
                    LOGGER.warn("Error report written to {}", path.toAbsolutePath()));
            if (result.totalFailed() > 0) {
                System.exit(1);
            }
        } catch (Exception e) {
            LOGGER.fatal("Export failed", e);
            System.exit(1);
        }
    }

    private static boolean isHelpRequested(String[] args) {
        for (String arg : args) {
            if ("--help".equalsIgnoreCase(arg) || "-h".equalsIgnoreCase(arg)) {
                return true;
            }
        }
        return false;
    }

    private static String resolveConfigPath(Map<String, String> params) {
        if (params.containsKey("config")) {
            return params.get("config");
        }
        return System.getenv().getOrDefault("APP_CONFIG_FILE", "config/application.properties");
    }

    private static ExportOptions buildOptions(Map<String, String> params) {
        Instant modifiedSince = parseDate(params.get("since"), "--since");
        Instant modifiedUntil = parseUntilDate(params.get("until"), "--until");
        Instant createdSince = parseDate(params.get("created-since"), "--created-since");
        Instant createdUntil = parseUntilDate(params.get("created-until"), "--created-until");
        Path errorReportPath = params.containsKey("error-report") && !params.get("error-report").isBlank()
                ? Paths.get(params.get("error-report"))
                : null;

        Set<String> fileIds = new HashSet<>(parseIdSet(params.get("include-file-ids")));
        Set<String> accountIds = new HashSet<>(parseIdSet(params.get("include-account-ids")));
        Set<String> opportunityIds = new HashSet<>(parseIdSet(params.get("include-opportunity-ids")));
        Set<String> contractIds = new HashSet<>(parseIdSet(params.get("include-contract-ids")));
        Set<FileRecord.ParentType> types = new HashSet<>(parseTypes(params.get("include-types")));

        if (params.containsKey("retry-from-report")) {
            Path reportPath = Paths.get(params.get("retry-from-report"));
            ReportFilters filters = loadRetryFilters(reportPath);
            fileIds.addAll(filters.fileIds());
            accountIds.addAll(filters.accountIds());
            opportunityIds.addAll(filters.opportunityIds());
            contractIds.addAll(filters.contractIds());
            types.addAll(filters.types());
        }

        return new ExportOptions(modifiedSince, modifiedUntil, createdSince, createdUntil, errorReportPath,
                fileIds, accountIds, opportunityIds, contractIds, types);
    }

    private static Instant parseDate(String value, String optionName) {
        if (value == null || value.isBlank()) {
            return null;
        }
        try {
            LocalDate date = LocalDate.parse(value.trim());
            return date.atStartOfDay().toInstant(ZoneOffset.UTC);
        } catch (Exception e) {
            throw new IllegalArgumentException("Unable to parse " + optionName + " value. Use format YYYY-MM-DD", e);
        }
    }

    /**
     * Parses an upper-bound date (inclusive) by returning an Instant representing the start of the next day.
     * Comparisons can then use {@code !timestamp.isBefore(untilExclusive)} to enforce the upper bound inclusively.
     */
    private static Instant parseUntilDate(String value, String optionName) {
        if (value == null || value.isBlank()) {
            return null;
        }
        try {
            LocalDate date = LocalDate.parse(value.trim());
            LocalDate nextDay = date.plusDays(1);
            return nextDay.atStartOfDay().toInstant(ZoneOffset.UTC);
        } catch (Exception e) {
            throw new IllegalArgumentException("Unable to parse " + optionName + " value. Use format YYYY-MM-DD", e);
        }
    }

    private static Map<String, String> parseArgs(String[] args) {
        Map<String, String> params = new HashMap<>();
        for (String arg : args) {
            if (arg.startsWith("--")) {
                int idx = arg.indexOf('=');
                if (idx > 2) {
                    String key = arg.substring(2, idx);
                    String value = arg.substring(idx + 1);
                    params.put(key, value);
                } else {
                    params.put(arg.substring(2), "");
                }
            }
        }
        return params;
    }

    private static Set<String> parseIdSet(String raw) {
        if (raw == null || raw.isBlank()) {
            return Set.of();
        }
        Set<String> result = new HashSet<>();
        Arrays.stream(raw.split(","))
                .map(String::trim)
                .filter(s -> !s.isEmpty())
                .map(String::toUpperCase)
                .forEach(result::add);
        return result;
    }

    private static Set<FileRecord.ParentType> parseTypes(String raw) {
        if (raw == null || raw.isBlank()) {
            return Set.of();
        }
        Set<FileRecord.ParentType> result = new HashSet<>();
        Arrays.stream(raw.split(","))
                .map(String::trim)
                .filter(s -> !s.isEmpty())
                .forEach(value -> result.add(parseTypeValue(value)));
        return result;
    }

    private static FileRecord.ParentType parseTypeValue(String raw) {
        String normalized = raw.trim().toUpperCase(Locale.ROOT);
        if (normalized.endsWith("S")) {
            normalized = normalized.substring(0, normalized.length() - 1);
        }
        return switch (normalized) {
            case "ACCOUNT" -> FileRecord.ParentType.ACCOUNT;
            case "OPPORTUNITY" -> FileRecord.ParentType.OPPORTUNITY;
            case "CONTRACT" -> FileRecord.ParentType.CONTRACT;
            default -> throw new IllegalArgumentException("Unknown parent type: " + raw);
        };
    }

    private static ReportFilters loadRetryFilters(Path reportPath) {
        try {
            String content = Files.readString(reportPath);
            JSONArray array = new JSONArray(content);
            Set<String> fileIds = new HashSet<>();
            Set<String> accountIds = new HashSet<>();
            Set<String> opportunityIds = new HashSet<>();
            Set<String> contractIds = new HashSet<>();
            Set<FileRecord.ParentType> types = new HashSet<>();
            for (int i = 0; i < array.length(); i++) {
                JSONObject obj = array.getJSONObject(i);
                String typeValue = obj.optString("type", null);
                if (typeValue != null && !typeValue.isBlank()) {
                    FileRecord.ParentType parentType = parseTypeValue(typeValue);
                    types.add(parentType);
                    switch (parentType) {
                        case ACCOUNT -> extractIdFromFolder(obj.optString("folderPath", null)).ifPresent(accountIds::add);
                        case OPPORTUNITY -> {
                            extractIdFromFolder(obj.optString("folderPath", null)).ifPresent(opportunityIds::add);
                            extractAccountIdFromPath(obj.optString("folderPath", null)).ifPresent(accountIds::add);
                        }
                        case CONTRACT -> {
                            extractIdFromFolder(obj.optString("folderPath", null)).ifPresent(contractIds::add);
                            extractAccountIdFromPath(obj.optString("folderPath", null)).ifPresent(accountIds::add);
                        }
                    }
                }
                String downloadId = normalizeId(obj.optString("downloadId", null));
                if (downloadId != null) {
                    fileIds.add(downloadId);
                }
                String namingId = extractBracketId(obj.optString("targetFileName", null));
                if (namingId != null) {
                    fileIds.add(namingId);
                }
            }
            return new ReportFilters(fileIds, accountIds, opportunityIds, contractIds, types);
        } catch (Exception e) {
            throw new IllegalArgumentException("Unable to read error report from " + reportPath, e);
        }
    }

    private static java.util.Optional<String> extractIdFromFolder(String folderPath) {
        if (folderPath == null || folderPath.isBlank()) {
            return java.util.Optional.empty();
        }
        String[] segments = folderPath.split("/");
        if (segments.length == 0) {
            return java.util.Optional.empty();
        }
        return java.util.Optional.ofNullable(extractBracketId(segments[segments.length - 1]));
    }

    private static java.util.Optional<String> extractAccountIdFromPath(String folderPath) {
        if (folderPath == null || folderPath.isBlank()) {
            return java.util.Optional.empty();
        }
        String[] segments = folderPath.split("/");
        if (segments.length == 0) {
            return java.util.Optional.empty();
        }
        return java.util.Optional.ofNullable(extractBracketId(segments[0]));
    }

    private static String extractBracketId(String value) {
        if (value == null) {
            return null;
        }
        int start = value.lastIndexOf('[');
        int end = value.lastIndexOf(']');
        if (start >= 0 && end > start) {
            return normalizeId(value.substring(start + 1, end));
        }
        return null;
    }

    private static String normalizeId(String value) {
        if (value == null) {
            return null;
        }
        String trimmed = value.trim();
        return trimmed.isEmpty() ? null : trimmed.toUpperCase(Locale.ROOT);
    }

    private record ReportFilters(Set<String> fileIds,
                                 Set<String> accountIds,
                                 Set<String> opportunityIds,
                                 Set<String> contractIds,
                                 Set<FileRecord.ParentType> types) {
    }

    private static void printUsage() {
        System.out.println("Usage: java -jar exporter.jar [options]\n" +
                "Options:\n" +
                "  --help, -h                       Show this help message\n" +
                "  --config=PATH                    Path to application properties (default config/application.properties)\n" +
                "  --since=YYYY-MM-DD               Include files modified on or after this date (UTC)\n" +
                "  --until=YYYY-MM-DD               Include files modified on or before this date (UTC)\n" +
                "  --created-since=YYYY-MM-DD       Include files created on or after this date (UTC)\n" +
                "  --created-until=YYYY-MM-DD       Include files created on or before this date (UTC)\n" +
                "  --include-file-ids=ID1,ID2       Comma separated list of Attachment/ContentDocument ids to export\n" +
                "  --include-account-ids=ID1,...    Limit export to specific Account ids\n" +
                "  --include-opportunity-ids=...    Limit export to specific Opportunity ids\n" +
                "  --include-contract-ids=...       Limit export to specific Contract ids\n" +
                "  --include-types=account,...      Limit export to listed parent types (account, opportunity, contract)\n" +
                "  --retry-from-report=PATH         Read error report JSON and retry only listed entries\n" +
                "  --error-report=PATH              Write error report JSON to this path (default export-errors-<timestamp>.json)\n" +
                "Environment variables: APP_CONFIG_FILE overrides --config; SF_*, BOX_*, EXPORT_* override properties.\n");
    }
}


