package com.mirantis.massdownloader.config;

import com.mirantis.massdownloader.model.FileRecord.ParentType;

import java.nio.file.Path;
import java.time.Instant;
import java.util.Collections;
import java.util.Optional;
import java.util.Set;

public class ExportOptions {

    private final Instant modifiedSince;
    private final Instant modifiedUntilExclusive;
    private final Instant createdSince;
    private final Instant createdUntilExclusive;
    private final Path errorReportPath;
    private final Set<String> fileIds;
    private final Set<String> accountIds;
    private final Set<String> opportunityIds;
    private final Set<String> contractIds;
    private final Set<ParentType> allowedTypes;

    public ExportOptions(Instant modifiedSince,
                         Instant modifiedUntilExclusive,
                         Instant createdSince,
                         Instant createdUntilExclusive,
                         Path errorReportPath,
                         Set<String> fileIds,
                         Set<String> accountIds,
                         Set<String> opportunityIds,
                         Set<String> contractIds,
                         Set<ParentType> allowedTypes) {
        this.modifiedSince = modifiedSince;
        this.modifiedUntilExclusive = modifiedUntilExclusive;
        this.createdSince = createdSince;
        this.createdUntilExclusive = createdUntilExclusive;
        this.errorReportPath = errorReportPath;
        this.fileIds = fileIds == null ? Collections.emptySet() : Collections.unmodifiableSet(fileIds);
        this.accountIds = accountIds == null ? Collections.emptySet() : Collections.unmodifiableSet(accountIds);
        this.opportunityIds = opportunityIds == null ? Collections.emptySet() : Collections.unmodifiableSet(opportunityIds);
        this.contractIds = contractIds == null ? Collections.emptySet() : Collections.unmodifiableSet(contractIds);
        this.allowedTypes = allowedTypes == null ? Collections.emptySet() : Collections.unmodifiableSet(allowedTypes);
    }

    public Optional<Instant> getModifiedSince() {
        return Optional.ofNullable(this.modifiedSince);
    }

    public Optional<Instant> getModifiedUntilExclusive() {
        return Optional.ofNullable(this.modifiedUntilExclusive);
    }

    public Optional<Instant> getCreatedSince() {
        return Optional.ofNullable(this.createdSince);
    }

    public Optional<Instant> getCreatedUntilExclusive() {
        return Optional.ofNullable(this.createdUntilExclusive);
    }

    public Optional<Path> getErrorReportPath() {
        return Optional.ofNullable(this.errorReportPath);
    }

    public Set<String> getFileIds() {
        return this.fileIds;
    }

    public Set<String> getAccountIds() {
        return this.accountIds;
    }

    public Set<String> getOpportunityIds() {
        return this.opportunityIds;
    }

    public Set<String> getContractIds() {
        return this.contractIds;
    }

    public Set<ParentType> getAllowedTypes() {
        return this.allowedTypes;
    }

    public boolean hasFileIdFilter() {
        return !this.fileIds.isEmpty();
    }

    public boolean hasAccountFilter() {
        return !this.accountIds.isEmpty();
    }

    public boolean hasOpportunityFilter() {
        return !this.opportunityIds.isEmpty();
    }

    public boolean hasContractFilter() {
        return !this.contractIds.isEmpty();
    }

    public boolean hasTypeFilter() {
        return !this.allowedTypes.isEmpty();
    }
}


