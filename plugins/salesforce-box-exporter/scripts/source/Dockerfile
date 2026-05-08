# syntax=docker/dockerfile:1.6

FROM maven:3.9.9-eclipse-temurin-17 AS build
WORKDIR /app
COPY pom.xml ./
RUN mvn -B -q dependency:go-offline
COPY src ./src
RUN mvn -B -q package

# Use eclipse-temurin:17-jre (Ubuntu Noble) as runtime base.
# Run apt-get upgrade to pull in all available security patches at build time
# (e.g. libpng CVE-2025-64505/65018/64720/64506, expat CVE-2025-66382).
# The image is rebuilt in CI so this stays current without pinning package versions.
FROM eclipse-temurin:17-jre
RUN apt-get update -qq \
    && apt-get upgrade -y --no-install-recommends \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/exporter
COPY --from=build /app/target/app /opt/exporter/app
COPY --from=build /app/src/main/resources/log4j2.xml ./log4j2.xml
# Run as a non-root user to reduce attack surface.
# UID/GID 10001 is arbitrary but outside the reserved range.
RUN groupadd --gid 10001 exporter \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin exporter \
    && chown -R exporter:exporter /opt/exporter
USER exporter
# Config (application.properties + box_config.json) must be mounted at runtime:
#   docker run -v /host/config:/opt/exporter/config ...
# Do NOT bake credentials into the image.
ENTRYPOINT ["/opt/exporter/app/bin/mass-exporter"]

