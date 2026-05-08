package com.mirantis.massdownloader.service;

import com.mirantis.massdownloader.config.ExportOptions;
import com.mirantis.massdownloader.model.FileRecord;
import com.mirantis.massdownloader.model.FileRecord.ParentType;
import com.mirantis.massdownloader.salesforce.SalesforceClient;
import com.mirantis.massdownloader.salesforce.SalesforceClient.SalesforceException;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
import org.json.JSONArray;
import org.json.JSONObject;

import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;

class SalesforceMetadataService {

    private static final Logger LOGGER = LogManager.getLogger(SalesforceMetadataService.class);

    private final SalesforceClient client;

    SalesforceMetadataService(SalesforceClient client) {
        this.client = client;
    }

    List<FileRecord> collectFileRecords(ExportOptions options) throws SalesforceException {
        List<FileRecord> records = new ArrayList<>();
        if (shouldProcessType(options, ParentType.ACCOUNT)) {
            records.addAll(fetchAccountAttachments(options));
            records.addAll(fetchAccountContentDocuments(options));
        }
        if (shouldProcessType(options, ParentType.OPPORTUNITY)) {
            records.addAll(fetchOpportunityAttachments(options));
            records.addAll(fetchOpportunityContentDocuments(options));
        }
        if (shouldProcessType(options, ParentType.CONTRACT)) {
            records.addAll(fetchContractAttachments(options));
            records.addAll(fetchContractContentDocuments(options));
        }
        LOGGER.info("Collected {} file descriptors from Salesforce", records.size());
        return records;
    }

    private List<FileRecord> fetchAccountAttachments(ExportOptions options) throws SalesforceException {
        String soql = "SELECT Id, Name, ParentId, Parent.Name, LastModifiedDate, CreatedDate "
                + "FROM Attachment WHERE ParentId IN (SELECT Id FROM Account)";
        return mapAttachments(this.client.query(soql), ParentType.ACCOUNT, options);
    }

    private List<FileRecord> fetchOpportunityAttachments(ExportOptions options) throws SalesforceException {
        String soql = "SELECT Id, Name, ParentId, "
                + "TYPEOF Parent WHEN Opportunity THEN Name, AccountId, Account.Name END, "
                + "LastModifiedDate, CreatedDate "
                + "FROM Attachment WHERE ParentId IN (SELECT Id FROM Opportunity)";
        return mapAttachments(this.client.query(soql), ParentType.OPPORTUNITY, options);
    }

    private List<FileRecord> fetchContractAttachments(ExportOptions options) throws SalesforceException {
        String soql = "SELECT Id, Name, ParentId, "
                + "TYPEOF Parent WHEN Contract THEN Name, ContractNumber, AccountId, Account.Name END, "
                + "LastModifiedDate, CreatedDate "
                + "FROM Attachment WHERE ParentId IN (SELECT Id FROM Contract)";
        return mapAttachments(this.client.query(soql), ParentType.CONTRACT, options);
    }

    private List<FileRecord> mapAttachments(JSONArray records, ParentType type, ExportOptions options) {
        List<FileRecord> result = new ArrayList<>();
        for (int i = 0; i < records.length(); i++) {
            JSONObject row = records.getJSONObject(i);
            String attachmentId = row.optString("Id", null);
            String name = row.optString("Name", "file");
            String parentId = row.optString("ParentId", null);
            JSONObject parent = row.optJSONObject("Parent");
            if (attachmentId == null || attachmentId.isBlank()) {
                LOGGER.warn("Skipping attachment with missing Id: {}", row);
                continue;
            }
            if (parentId == null || parentId.isBlank()) {
                LOGGER.warn("Skipping attachment {} with missing ParentId: {}", attachmentId, row);
                continue;
            }
            if (parent == null) {
                LOGGER.warn("Skipping attachment {} with missing Parent object: {}", attachmentId, row);
                continue;
            }
            Instant lastModified = parseInstant(row.optString("LastModifiedDate", null));
            Instant createdDate = parseInstant(row.optString("CreatedDate", null));
            String parentName = resolveName(type, parent);
            String accountId = null;
            String accountName = null;
            if (type == ParentType.ACCOUNT) {
                accountId = parentId;
                accountName = parentName;
            } else {
                // For OPPORTUNITY and CONTRACT, AccountId should always be present (master-detail relationship)
                // Try to get AccountId directly from parent first (in case it's returned as a direct field from TYPEOF)
                accountId = parent.optString("AccountId", null);
                if (accountId == null || accountId.isBlank()) {
                    // Fallback to nested Account object
                    JSONObject account = parent.optJSONObject("Account");
                    if (account != null) {
                        accountId = account.optString("Id", null);
                        accountName = account.optString("Name", null);
                    }
                } else {
                    // If AccountId was found directly, try to get Account.Name from nested object
                    JSONObject account = parent.optJSONObject("Account");
                    if (account != null) {
                        accountName = account.optString("Name", null);
                    }
                }
                // Warn if AccountId is still missing (should not happen for OPPORTUNITY/CONTRACT)
                if (accountId == null || accountId.isBlank()) {
                    LOGGER.warn("Missing AccountId for {} {} (parentId: {}). This is unexpected for master-detail relationships.", 
                            type, parentId, parentId);
                }
            }
            String[] fileParts = splitFileName(name);
            if (!matchesFilters(type, parentId, accountId, attachmentId, attachmentId, createdDate, lastModified, options)) {
                continue;
            }
            result.add(new FileRecord(type,
                    parentId,
                    parentName,
                    accountId,
                    accountName,
                    attachmentId,
                    attachmentId,
                    fileParts[0],
                    fileParts[1],
                    lastModified));
        }
        LOGGER.info("Fetched {} attachment records for {}", result.size(), type);
        return result;
    }

    private List<FileRecord> fetchAccountContentDocuments(ExportOptions options) throws SalesforceException {
        String soql = "SELECT Id, ContentDocumentId, "
                + "ContentDocument.LatestPublishedVersionId, "
                + "ContentDocument.LatestPublishedVersion.Title, ContentDocument.LatestPublishedVersion.FileExtension, "
                + "ContentDocument.LastModifiedDate, ContentDocument.LatestPublishedVersion.LastModifiedDate, "
                + "ContentDocument.CreatedDate, ContentDocument.LatestPublishedVersion.CreatedDate, "
                + "LinkedEntityId, LinkedEntity.Name "
                + "FROM ContentDocumentLink WHERE LinkedEntityId IN (SELECT Id FROM Account)";
        return mapContentDocuments(this.client.query(soql), ParentType.ACCOUNT, options);
    }

    private List<FileRecord> fetchOpportunityContentDocuments(ExportOptions options) throws SalesforceException {
        String soql = "SELECT Id, ContentDocumentId, "
                + "ContentDocument.LatestPublishedVersionId, "
                + "ContentDocument.LatestPublishedVersion.Title, ContentDocument.LatestPublishedVersion.FileExtension, "
                + "ContentDocument.LastModifiedDate, ContentDocument.LatestPublishedVersion.LastModifiedDate, "
                + "ContentDocument.CreatedDate, ContentDocument.LatestPublishedVersion.CreatedDate, "
                + "LinkedEntityId, TYPEOF LinkedEntity WHEN Opportunity THEN Name, AccountId, Account.Name END "
                + "FROM ContentDocumentLink WHERE LinkedEntityId IN (SELECT Id FROM Opportunity)";
        return mapContentDocuments(this.client.query(soql), ParentType.OPPORTUNITY, options);
    }

    private List<FileRecord> fetchContractContentDocuments(ExportOptions options) throws SalesforceException {
        String soql = "SELECT Id, ContentDocumentId, "
                + "ContentDocument.LatestPublishedVersionId, "
                + "ContentDocument.LatestPublishedVersion.Title, ContentDocument.LatestPublishedVersion.FileExtension, "
                + "ContentDocument.LastModifiedDate, ContentDocument.LatestPublishedVersion.LastModifiedDate, "
                + "ContentDocument.CreatedDate, ContentDocument.LatestPublishedVersion.CreatedDate, "
                + "LinkedEntityId, TYPEOF LinkedEntity WHEN Contract THEN Name, ContractNumber, AccountId, Account.Name END "
                + "FROM ContentDocumentLink WHERE LinkedEntityId IN (SELECT Id FROM Contract)";
        return mapContentDocuments(this.client.query(soql), ParentType.CONTRACT, options);
    }

    private List<FileRecord> mapContentDocuments(JSONArray records, ParentType type, ExportOptions options) {
        List<FileRecord> result = new ArrayList<>();
        for (int i = 0; i < records.length(); i++) {
            JSONObject row = records.getJSONObject(i);
            JSONObject contentDocument = row.optJSONObject("ContentDocument");
            if (contentDocument == null) {
                LOGGER.warn("Skipping content document without ContentDocument field: {}", row);
                continue;
            }
            String contentDocumentId = row.optString("ContentDocumentId", null);
            if (contentDocumentId == null || contentDocumentId.isBlank()) {
                LOGGER.warn("Skipping content document with missing ContentDocumentId: {}", row);
                continue;
            }
            String versionId = contentDocument.optString("LatestPublishedVersionId", null);
            JSONObject version = contentDocument.optJSONObject("LatestPublishedVersion");
            if (versionId == null || versionId.isBlank()) {
                LOGGER.warn("Skipping content document {} with missing LatestPublishedVersionId: {}", contentDocumentId, row);
                continue;
            }
            if (version == null) {
                LOGGER.warn("Skipping content document {} with missing LatestPublishedVersion object: {}", contentDocumentId, row);
                continue;
            }
            String title = version.optString("Title", "file");
            String extension = version.optString("FileExtension", "");
            Instant lastModified = parseInstant(version.optString("LastModifiedDate", null));
            if (lastModified == null) {
                lastModified = parseInstant(contentDocument.optString("LastModifiedDate", null));
            }
            Instant createdDate = parseInstant(version.optString("CreatedDate", null));
            if (createdDate == null) {
                createdDate = parseInstant(contentDocument.optString("CreatedDate", null));
            }
            String parentId = row.optString("LinkedEntityId", null);
            if (parentId == null || parentId.isBlank()) {
                LOGGER.warn("Skipping content document {} with missing LinkedEntityId: {}", contentDocumentId, row);
                continue;
            }
            JSONObject parent = row.optJSONObject("LinkedEntity");
            if (parent == null) {
                LOGGER.warn("Skipping content document {} with missing LinkedEntity object: {}", contentDocumentId, row);
                continue;
            }
            String parentName = resolveName(type, parent);
            String accountId = null;
            String accountName = null;
            if (type == ParentType.ACCOUNT) {
                accountId = parentId;
                accountName = parentName;
            } else {
                // For OPPORTUNITY and CONTRACT, AccountId should always be present (master-detail relationship)
                // Try to get AccountId directly from parent first (in case it's returned as a direct field from TYPEOF)
                accountId = parent.optString("AccountId", null);
                if (accountId == null || accountId.isBlank()) {
                    // Fallback to nested Account object
                    JSONObject account = parent.optJSONObject("Account");
                    if (account != null) {
                        accountId = account.optString("Id", null);
                        accountName = account.optString("Name", null);
                    }
                } else {
                    // If AccountId was found directly, try to get Account.Name from nested object
                    JSONObject account = parent.optJSONObject("Account");
                    if (account != null) {
                        accountName = account.optString("Name", null);
                    }
                }
                // Warn if AccountId is still missing (should not happen for OPPORTUNITY/CONTRACT)
                if (accountId == null || accountId.isBlank()) {
                    LOGGER.warn("Missing AccountId for {} {} (parentId: {}). This is unexpected for master-detail relationships.", 
                            type, parentId, parentId);
                }
            }
            if (!matchesFilters(type, parentId, accountId, versionId, contentDocumentId, createdDate, lastModified, options)) {
                continue;
            }
            result.add(new FileRecord(type,
                    parentId,
                    parentName,
                    accountId,
                    accountName,
                    versionId,
                    contentDocumentId,
                    title,
                    extension.isBlank() ? "" : "." + extension,
                    lastModified));
        }
        LOGGER.info("Fetched {} content document records for {}", result.size(), type);
        return result;
    }

    private static String[] splitFileName(String name) {
        if (name == null) {
            return new String[]{"file", ""};
        }
        int idx = name.lastIndexOf('.');
        if (idx > 0 && idx < name.length() - 1) {
            return new String[]{name.substring(0, idx), name.substring(idx)};
        }
        return new String[]{name, ""};
    }

    private static String resolveName(ParentType type, JSONObject parent) {
        String name = parent.optString("Name", null);
        if ((name == null || name.isBlank()) && type == ParentType.CONTRACT) {
            String contractNumber = parent.optString("ContractNumber", null);
            if (contractNumber != null && !contractNumber.isBlank()) {
                return contractNumber;
            }
        }
        if (name != null && !name.isBlank()) {
            return name;
        }
        return parent.optString("Id", "UNKNOWN");
    }

    private static Instant parseInstant(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        String normalized = value.trim();
        // Salesforce often returns offsets like +0000 or -0700 without colon; normalize to +00:00 form
        if (normalized.matches(".*[+-]\\d{4}$")) {
            int len = normalized.length();
            normalized = normalized.substring(0, len - 2) + ":" + normalized.substring(len - 2);
        }
        try {
            return OffsetDateTime.parse(normalized, DateTimeFormatter.ISO_OFFSET_DATE_TIME).toInstant();
        } catch (Exception primary) {
            try {
                DateTimeFormatter fallback = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss.SSSX", java.util.Locale.ROOT);
                return OffsetDateTime.parse(normalized, fallback).toInstant();
            } catch (Exception ignored) {
                LOGGER.debug("Unable to parse datetime '{}': {}", value, primary.getMessage());
                return null;
            }
        }
    }

    private boolean matchesFilters(ParentType type,
                                   String parentId,
                                   String accountId,
                                   String downloadId,
                                   String namingId,
                                   Instant createdDate,
                                   Instant lastModified,
                                   ExportOptions options) {
        if (options.hasTypeFilter() && !options.getAllowedTypes().contains(type)) {
            return false;
        }
        Instant modifiedSince = options.getModifiedSince().orElse(null);
        if (modifiedSince != null) {
            if (lastModified == null || lastModified.isBefore(modifiedSince)) {
                return false;
            }
        }
        Instant modifiedUntilExclusive = options.getModifiedUntilExclusive().orElse(null);
        if (modifiedUntilExclusive != null) {
            if (lastModified == null || !lastModified.isBefore(modifiedUntilExclusive)) {
                return false;
            }
        }
        Instant createdSince = options.getCreatedSince().orElse(null);
        if (createdSince != null) {
            if (createdDate == null || createdDate.isBefore(createdSince)) {
                return false;
            }
        }
        Instant createdUntilExclusive = options.getCreatedUntilExclusive().orElse(null);
        if (createdUntilExclusive != null) {
            if (createdDate == null || !createdDate.isBefore(createdUntilExclusive)) {
                return false;
            }
        }
        if (options.hasFileIdFilter()) {
            Set<String> fileIds = options.getFileIds();
            String download = normalizeId(downloadId);
            String naming = normalizeId(namingId);
            if ((download == null || !fileIds.contains(download))
                    && (naming == null || !fileIds.contains(naming))) {
                return false;
            }
        }

        switch (type) {
            case ACCOUNT -> {
                if (options.hasAccountFilter()) {
                    String parentNormalized = normalizeId(parentId);
                    if (parentNormalized == null || !options.getAccountIds().contains(parentNormalized)) {
                        return false;
                    }
                }
            }
            case OPPORTUNITY -> {
                if (options.hasOpportunityFilter()) {
                    String normalizedParent = normalizeId(parentId);
                    if (normalizedParent == null || !options.getOpportunityIds().contains(normalizedParent)) {
                        return false;
                    }
                }
                if (options.hasAccountFilter()) {
                    String normalizedAccount = normalizeId(accountId);
                    if (normalizedAccount == null || !options.getAccountIds().contains(normalizedAccount)) {
                        return false;
                    }
                }
            }
            case CONTRACT -> {
                if (options.hasContractFilter()) {
                    String normalizedParent = normalizeId(parentId);
                    if (normalizedParent == null || !options.getContractIds().contains(normalizedParent)) {
                        return false;
                    }
                }
                if (options.hasAccountFilter()) {
                    String normalizedAccount = normalizeId(accountId);
                    if (normalizedAccount == null || !options.getAccountIds().contains(normalizedAccount)) {
                        return false;
                    }
                }
            }
        }
        return true;
    }

    private boolean shouldProcessType(ExportOptions options, ParentType type) {
        return !options.hasTypeFilter() || options.getAllowedTypes().contains(type);
    }

    private static String normalizeId(String value) {
        if (value == null) {
            return null;
        }
        String trimmed = value.trim();
        return trimmed.isEmpty() ? null : trimmed.toUpperCase();
    }
}


