package com.mirantis.massdownloader.box;

import com.box.sdk.BoxAPIException;
import com.box.sdk.BoxConfig;
import com.box.sdk.BoxDeveloperEditionAPIConnection;
import com.box.sdk.BoxFile;
import com.box.sdk.BoxFolder;
import com.box.sdk.BoxItem;
import com.mirantis.massdownloader.config.AppConfig;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileReader;
import java.io.IOException;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.TimeUnit;

public class BoxClient implements AutoCloseable {

    private static final Logger LOGGER = LogManager.getLogger(BoxClient.class);
    private static final Duration RETRY_BACKOFF = Duration.ofSeconds(5);
    private static final int MAX_RETRIES = 3;
    private static final long LARGE_FILE_UPLOAD_THRESHOLD = 20L * 1024 * 1024;

    private final BoxDeveloperEditionAPIConnection apiConnection;
    private final BoxFolder rootFolder;
    private final Map<String, BoxFolder> folderCache;
    private final Map<String, Set<String>> folderFilesCache;
    private final Map<String, Object> folderLocks;
    private final Map<String, Object> fileLocks;

    public BoxClient(AppConfig config) throws IOException {
        String boxConfigPath = config.require("box.config.path");
        String rootFolderId = config.require("box.root.folder.id");
        String appUserId = config.optional("box.app.user.id", "");

        try (FileReader reader = new FileReader(new File(boxConfigPath))) {
            BoxConfig boxConfig = BoxConfig.readFrom(reader);
            this.apiConnection = BoxDeveloperEditionAPIConnection.getAppEnterpriseConnection(boxConfig);
            if (appUserId != null && !appUserId.isBlank()) {
                LOGGER.info("Impersonating Box app user {}", appUserId);
                this.apiConnection.asUser(appUserId);
            }
        }
        this.rootFolder = new BoxFolder(this.apiConnection, rootFolderId);
        this.folderCache = new ConcurrentHashMap<>();
        this.folderFilesCache = new ConcurrentHashMap<>();
        this.folderLocks = new ConcurrentHashMap<>();
        this.fileLocks = new ConcurrentHashMap<>();
        this.folderCache.put(rootFolderId, this.rootFolder);
        this.folderLocks.put(rootFolderId, new Object());

        validateRootFolder();
    }

    public boolean uploadIfMissing(File file, String targetName, List<String> folderPath) throws IOException {
        Objects.requireNonNull(file, "file");
        Objects.requireNonNull(targetName, "targetName");
        Objects.requireNonNull(folderPath, "folderPath");
        BoxFolder destination = ensureFolderPath(folderPath);
        String fileLockKey = destination.getID() + "|" + targetName;
        Object lock = this.fileLocks.computeIfAbsent(fileLockKey, key -> new Object());
        synchronized (lock) {
            if (fileExists(destination, targetName)) {
                LOGGER.info("File {} already exists in folder {}. Skipping upload.", targetName, destination.getID());
                return false;
            }
            executeWithRetry(() -> {
                try (FileInputStream stream = new FileInputStream(file)) {
                    BoxFile.Info info;
                    if (file.length() >= LARGE_FILE_UPLOAD_THRESHOLD) {
                        info = destination.uploadLargeFile(stream, targetName, file.length());
                    } else {
                        info = destination.uploadFile(stream, targetName);
                    }
                    LOGGER.info("Uploaded file {} to folder {} as {}", targetName, destination.getID(), info.getID());
                    String targetId = extractSalesforceId(targetName);
                    folderFilesCache
                            .computeIfAbsent(destination.getID(), id -> ConcurrentHashMap.newKeySet())
                            .add(targetId != null ? targetId : targetName);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    throw new IOException("Interrupted while uploading to Box", e);
                }
                return null;
            });
            return true;
        }
    }

    private BoxFolder ensureFolderPath(List<String> path) throws IOException {
        BoxFolder current = this.rootFolder;
        String cacheKey = current.getID();
        for (String segment : path) {
            if (segment == null || segment.isBlank()) {
                continue;
            }
            String nextKey = cacheKey + "/" + segment;
            Object lock = this.folderLocks.computeIfAbsent(nextKey, key -> new Object());
            synchronized (lock) {
                BoxFolder cached = this.folderCache.get(nextKey);
                if (cached != null) {
                    current = cached;
                    cacheKey = nextKey;
                    continue;
                }
                String desiredId = extractSalesforceId(segment);
                BoxFolder nextFolder = findChildFolder(current, segment, desiredId);
                if (nextFolder == null) {
                    BoxFolder folderRef = current;
                    String nameRef = segment;
                    nextFolder = executeWithRetry(() -> folderRef.createFolder(nameRef).getResource());
                    LOGGER.info("Created Box folder '{}' under {}", segment, current.getID());
                } else {
                    LOGGER.debug("Found existing folder '{}' under {}", segment, current.getID());
                }
                this.folderCache.put(nextKey, nextFolder);
                current = nextFolder;
                cacheKey = nextKey;
            }
        }
        return current;
    }

    private BoxFolder findChildFolder(BoxFolder parent, String desiredName, String desiredId) throws IOException {
        for (BoxItem.Info item : parent) {
            if (item instanceof BoxFolder.Info) {
                BoxFolder.Info folderInfo = (BoxFolder.Info) item;
                String existingId = extractSalesforceId(folderInfo.getName());
                boolean idMatches = desiredId != null && desiredId.equals(existingId);
                boolean nameMatches = desiredId == null && folderInfo.getName().equals(desiredName);
                if (idMatches || nameMatches) {
                    BoxFolder folder = folderInfo.getResource();
                    if (!folderInfo.getName().equals(desiredName)) {
                        renameFolder(folder, desiredName);
                    }
                    return folder;
                }
            }
        }
        return null;
    }

    private void renameFolder(BoxFolder folder, String desiredName) throws IOException {
        executeWithRetry(() -> {
            BoxFolder.Info info = folder.new Info();
            info.setName(desiredName);
            folder.updateInfo(info);
            return null;
        });
    }

    private boolean fileExists(BoxFolder folder, String fileName) throws IOException {
        String desiredId = extractSalesforceId(fileName);
        Set<String> identifiers = this.folderFilesCache.computeIfAbsent(folder.getID(), id -> loadFileIdentifiers(folder));
        String lookupKey = desiredId != null ? desiredId : fileName;
        if (identifiers.contains(lookupKey)) {
            ensureFileName(folder, desiredId, fileName);
            return true;
        }
        return false;
    }

    private void ensureFileName(BoxFolder folder, String desiredId, String desiredName) throws IOException {
        if (desiredId == null) {
            return;
        }
        for (BoxItem.Info item : folder) {
            if (item instanceof BoxFile.Info) {
                BoxFile.Info fileInfo = (BoxFile.Info) item;
                String existingId = extractSalesforceId(fileInfo.getName());
                if (desiredId.equals(existingId) && !fileInfo.getName().equals(desiredName)) {
                    BoxFile file = fileInfo.getResource();
                    renameFile(file, desiredName);
                }
            }
        }
    }

    private void renameFile(BoxFile file, String desiredName) throws IOException {
        executeWithRetry(() -> {
            BoxFile.Info info = file.new Info();
            info.setName(desiredName);
            file.updateInfo(info);
            return null;
        });
    }

    private Set<String> loadFileIdentifiers(BoxFolder folder) {
        Set<String> identifiers = ConcurrentHashMap.newKeySet();
        for (BoxItem.Info item : folder) {
            if (item instanceof BoxFile.Info) {
                String name = item.getName();
                String id = extractSalesforceId(name);
                identifiers.add(id != null ? id : name);
            }
        }
        return identifiers;
    }

    private String extractSalesforceId(String value) {
        if (value == null) {
            return null;
        }
        int start = value.lastIndexOf('[');
        int end = value.lastIndexOf(']');
        if (start >= 0 && end > start) {
            return value.substring(start + 1, end).trim();
        }
        return null;
    }

    private <T> T executeWithRetry(BoxOperation<T> operation) throws IOException {
        BoxAPIException lastException = null;
        for (int attempt = 0; attempt < MAX_RETRIES; attempt++) {
            try {
                return operation.execute();
            } catch (BoxAPIException apiException) {
                lastException = apiException;
                boolean retryable = apiException.getResponseCode() == 429 || apiException.getResponseCode() >= 500;
                if (!retryable || attempt == MAX_RETRIES - 1) {
                    break;
                }
                LOGGER.warn("Box API exception (attempt {}/{}). Retrying in {} seconds", attempt + 1, MAX_RETRIES,
                        RETRY_BACKOFF.toSeconds(), apiException);
                sleep(RETRY_BACKOFF);
            }
        }
        if (lastException != null) {
            throw new IOException("Box operation failed", lastException);
        }
        throw new IOException("Box operation failed for unknown reason");
    }

    private void validateRootFolder() throws IOException {
        executeWithRetry(() -> {
            BoxFolder.Info info = this.rootFolder.getInfo();
            LOGGER.info("Verified Box root folder '{}' ({})", info.getName(), this.rootFolder.getID());
            return info;
        });
    }

    private void sleep(Duration duration) {
        try {
            TimeUnit.MILLISECONDS.sleep(duration.toMillis());
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    @Override
    public void close() {
        // no-op: Box SDK manages underlying connections.
    }

    @FunctionalInterface
    private interface BoxOperation<T> {
        T execute() throws BoxAPIException, IOException;
    }
}


