ARG BUILD_FROM
FROM ${BUILD_FROM}

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Install snapcast-server and librespot from Alpine edge repos
# hadolint ignore=DL3018
RUN apk add --no-cache \
        pulseaudio \
        alsa-plugins-pulse \
        wget \
        unzip \
    && apk add --no-cache \
        --repository=http://dl-cdn.alpinelinux.org/alpine/edge/community/ \
        snapcast-server=0.35.0-r0 \
    && apk add --no-cache \
        --repository=http://dl-cdn.alpinelinux.org/alpine/edge/testing/ \
        librespot=0.8.0-r0 \
    && rm -rf /tmp/*

# Install snapweb from GitHub releases (not available as Alpine package)
ENV SNAPWEB_VERSION=0.9.3
RUN wget -q "https://github.com/snapcast/snapweb/releases/download/v${SNAPWEB_VERSION}/snapweb.zip" \
        -O /tmp/snapweb.zip \
    && mkdir -p /usr/share/snapserver/snapweb \
    && unzip -o /tmp/snapweb.zip -d /usr/share/snapserver/snapweb/ \
    && rm /tmp/snapweb.zip \
    && apk del --no-cache wget unzip

# Copy entrypoint
COPY run.sh /
RUN chmod a+x /run.sh

CMD ["/run.sh"]
