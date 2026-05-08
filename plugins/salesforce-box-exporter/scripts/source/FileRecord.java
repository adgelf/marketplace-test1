package com.mirantis.massdownloader.model;

import com.mirantis.massdownloader.util.NameFormatter;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public final class FileRecord {

    public enum ParentType {
        ACCOUNT,
        OPPORTUNITY,
        CONTRACT
    }

    private final ParentType parentType;
    private final String parentId;
    private final String parentName;
    private final String accountId;
    private final String accountName;
    private final String downloadId;
    private final String namingId;
    private final String baseName;
    private final String extension;
    private final Instant lastModified;

    public FileRecord(ParentType parentType,
                      String parentId,
                      String parentName,
                      String accountId,
                      String accountName,
                      String downloadId,
                      String namingId,
                      String baseName,
                      String extension,
                      Instant lastModified) {
        this.parentType = Objects.requireNonNull(parentType, "parentType");
        this.parentId = Objects.requireNonNull(parentId, "parentId");
        this.parentName = parentName;
        this.accountId = accountId;
        this.accountName = accountName;
        this.downloadId = Objects.requireNonNull(downloadId, "downloadId");
        this.namingId = Objects.requireNonNull(namingId, "namingId");
        this.baseName = baseName;
        this.extension = extension == null ? "" : extension;
        this.lastModified = lastModified;
    }

    public ParentType getParentType() {
        return this.parentType;
    }

    public String getDownloadId() {
        return this.downloadId;
    }

    public String getTargetFileName() {
        return NameFormatter.formatFileName(this.baseName, this.namingId, this.extension);
    }

    public Instant getLastModified() {
        return this.lastModified;
    }

    public List<String> getBoxFolderPath() {
        List<String> path = new ArrayList<>();
        if (this.parentType == ParentType.ACCOUNT) {
            // Files directly in account folder: "Acc Name [Acc Id]"
            path.add(NameFormatter.formatFolderName(this.parentName, this.parentId));
            return path;
        }
        // For OPPORTUNITY and CONTRACT, always include account folder
        String accountFolder = resolveAccountFolder();
        if (accountFolder != null) {
            path.add(accountFolder);
        }
        // Add Opportunities or Contracts subfolder
        if (this.parentType == ParentType.OPPORTUNITY) {
            path.add("Opportunities");
            // Then add opportunity folder: "Opp Name [Opp Id]"
            path.add(NameFormatter.formatFolderName(this.parentName, this.parentId));
        } else if (this.parentType == ParentType.CONTRACT) {
            path.add("Contracts");
            // Then add contract folder: "Contract Name/Number [Contract Id]"
            path.add(NameFormatter.formatFolderName(this.parentName, this.parentId));
        }
        return path;
    }

    private String resolveAccountFolder() {
        // For OPPORTUNITY and CONTRACT, accountId should always be present (master-detail relationship)
        // Never use parentId as fallback - it would be Opportunity/Contract ID, not Account ID!
        String id = (this.accountId == null || this.accountId.isBlank()) ? null : this.accountId;
        String name = (this.accountName == null || this.accountName.isBlank()) ? null : this.accountName;
        if (id == null || id.isBlank()) {
            // AccountId is missing - this should not happen. Return null to skip account folder.
            // The caller should handle this case appropriately.
            return null;
        }
        if (name == null || name.isBlank()) {
            // Use just ID if name is missing
            return NameFormatter.formatFolderName(null, id);
        }
        return NameFormatter.formatFolderName(name, id);
    }
}


