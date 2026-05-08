package com.mirantis.massdownloader.service;

import com.mirantis.massdownloader.box.BoxClient;
import com.mirantis.massdownloader.config.AppConfig;
import com.mirantis.massdownloader.config.ExportOptions;
import com.mirantis.massdownloader.model.FileRecord;
import com.mirantis.massdownloader.salesforce.SalesforceClient;
import com.mirantis.massdownloader.salesforce.SalesforceClient.SalesforceException;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardOpenOption;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.TimeUnit;
import java.util.stream.Collectors;

public class ExportOrchestrator {

    private static final Logger LOGGER = LogManager.getLogger(ExportOrchestrator.class);

    private final AppConfig config;
    private final ExportOptions options;

    public ExportOrchestrator(AppConfig config, ExportOptions options) {
        this.config = config;
        this.options = options;
    }

    public ExportResult export() throws Exception {
        SalesforceClient salesforceClient = new SalesforceClient(this.config);
        BoxClient boxClient = new BoxClient(this.config);
        try {
            SalesforceMetadataService metadataService = new SalesforceMetadataService(salesforceClient);
            List<FileRecord> records = metadataService.collectFileRecords(this.options);
            ProcessingStats stats = processRecords(records, salesforceClient, boxClient);
            Path reportPath = writeErrorReport(stats);
            return new ExportResult(stats.totalProcessed(), stats.totalUploaded(), stats.totalSkipped(), stats.totalFailed(), reportPath);
        } finally {
            salesforceClient.close();
            boxClient.close();
        }
    }

    private ProcessingStats processRecords(List<FileRecord> records,
                                           SalesforceClient salesforceClient,
                                           BoxClient boxClient) throws InterruptedException {
        int workerCount = Math.max(1, this.config.optionalInt("export.worker.threads", Math.min(4, Runtime.getRuntime().availableProcessors())));
        LOGGER.info("Processing {} records with {} worker threads", records.size(), workerCount);
        ExecutorService executor = Executors.newFixedThreadPool(workerCount);
        ProcessingStats stats = new ProcessingStats();
        File tempDir = this.config.optionalDirectory("export.temp.dir", new File(System.getProperty("java.io.tmpdir")));
        try {
            Files.createDirectories(tempDir.toPath());
        } catch (IOException e) {
            throw new RuntimeException("Unable to create temp directory: " + tempDir, e);
        }
        try {
            for (FileRecord record : records) {
                executor.submit(new FileTask(record, salesforceClient, boxClient, stats, tempDir));
            }
        } finally {
            executor.shutdown();
            boolean finished = executor.awaitTermination(7, TimeUnit.DAYS);
            if (!finished) {
                LOGGER.warn("Executor did not finish within timeout");
            }
        }
        return stats;
    }

    private Path writeErrorReport(ProcessingStats stats) {
        if (stats.failures.isEmpty()) {
            return null;
        }
        Path reportPath = this.options.getErrorReportPath()
                .orElseGet(() -> Paths.get("export-errors-" + System.currentTimeMillis() + ".json"));
        try {
            if (reportPath.getParent() != null) {
                Files.createDirectories(reportPath.getParent());
            }
            String payload = stats.failures.stream()
                    .map(FailedRecord::toJson)
                    .collect(Collectors.joining(",\n  ", "[\n  ", "\n]"));
            Files.writeString(reportPath, payload, StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING);
            return reportPath;
        } catch (IOException e) {
            LOGGER.error("Unable to write error report to {}", reportPath, e);
            return null;
        }
    }

    private static class FileTask implements Runnable {

        private final FileRecord record;
        private final SalesforceClient salesforceClient;
        private final BoxClient boxClient;
        private final ProcessingStats stats;
        private final File tempDir;

        FileTask(FileRecord record,
                 SalesforceClient salesforceClient,
                 BoxClient boxClient,
                 ProcessingStats stats,
                 File tempDir) {
            this.record = record;
            this.salesforceClient = salesforceClient;
            this.boxClient = boxClient;
            this.stats = stats;
            this.tempDir = tempDir;
        }

        @Override
        public void run() {
            this.stats.incrementProcessed();
            Path tempFile = null;
            try {
                tempFile = Files.createTempFile(this.tempDir.toPath(), "sf_export_", ".tmp");
                this.salesforceClient.downloadFile(this.record.getDownloadId(), tempFile);
                boolean uploaded = this.boxClient.uploadIfMissing(tempFile.toFile(), this.record.getTargetFileName(), this.record.getBoxFolderPath());
                if (uploaded) {
                    this.stats.incrementUploaded();
                } else {
                    this.stats.incrementSkipped();
                }
            } catch (SalesforceException e) {
                LOGGER.error("Failed to download {} due to Salesforce error", this.record.getDownloadId(), e);
                this.stats.incrementFailed();
                this.stats.addFailure(new FailedRecord(this.record, "Salesforce download error: " + e.getMessage()));
            } catch (Exception e) {
                LOGGER.error("Failed to upload file {}", this.record.getTargetFileName(), e);
                this.stats.incrementFailed();
                this.stats.addFailure(new FailedRecord(this.record, "Upload error: " + e.getMessage()));
            } finally {
                if (tempFile != null) {
                    try {
                        Files.deleteIfExists(tempFile);
                    } catch (IOException ignored) {
                    }
                }
            }
        }
    }

    public record ExportResult(int totalProcessed,
                               int totalUploaded,
                               int totalSkipped,
                               int totalFailed,
                               Path errorReportPath) {

        public java.util.Optional<Path> errorReport() {
            return java.util.Optional.ofNullable(this.errorReportPath);
        }
    }

    private static class ProcessingStats {
        private final java.util.concurrent.atomic.AtomicInteger processed = new java.util.concurrent.atomic.AtomicInteger();
        private final java.util.concurrent.atomic.AtomicInteger uploaded = new java.util.concurrent.atomic.AtomicInteger();
        private final java.util.concurrent.atomic.AtomicInteger skipped = new java.util.concurrent.atomic.AtomicInteger();
        private final java.util.concurrent.atomic.AtomicInteger failed = new java.util.concurrent.atomic.AtomicInteger();
        private final ConcurrentLinkedQueue<FailedRecord> failures = new ConcurrentLinkedQueue<>();

        void incrementProcessed() {
            this.processed.incrementAndGet();
        }

        void incrementUploaded() {
            this.uploaded.incrementAndGet();
        }

        void incrementSkipped() {
            this.skipped.incrementAndGet();
        }

        void incrementFailed() {
            this.failed.incrementAndGet();
        }

        int totalProcessed() {
            return this.processed.get();
        }

        int totalUploaded() {
            return this.uploaded.get();
        }

        int totalSkipped() {
            return this.skipped.get();
        }

        int totalFailed() {
            return this.failed.get();
        }

        void addFailure(FailedRecord failure) {
            this.failures.add(failure);
        }
    }

    private static class FailedRecord {
        private final FileRecord record;
        private final String reason;

        FailedRecord(FileRecord record, String reason) {
            this.record = record;
            this.reason = reason == null ? "" : reason;
        }

        String toJson() {
            String folderPath = String.join("/", this.record.getBoxFolderPath()).replace("\"", "\\\"");
            String escapedReason = this.reason.replace("\"", "\\\"");
            String escapedFileName = this.record.getTargetFileName().replace("\"", "\\\"");
            String lastModified = this.record.getLastModified() == null ? "" : this.record.getLastModified().toString();
            return String.format("{\"type\":\"%s\",\"downloadId\":\"%s\",\"targetFileName\":\"%s\",\"folderPath\":\"%s\",\"lastModified\":\"%s\",\"reason\":\"%s\"}",
                    this.record.getParentType(),
                    this.record.getDownloadId(),
                    escapedFileName,
                    folderPath,
                    lastModified,
                    escapedReason);
        }
    }
}


