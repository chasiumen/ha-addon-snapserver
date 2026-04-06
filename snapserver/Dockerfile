ARG BUILD_FROM
FROM ${BUILD_FROM}

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Install snapcast-server, librespot, and snapweb from Alpine edge repos
# hadolint ignore=DL3018
RUN apk add --no-cache \
        pulseaudio \
        alsa-plugins-pulse \
    && apk add --no-cache \
        --repository=http://dl-cdn.alpinelinux.org/alpine/edge/community/ \
        snapcast-server=0.35.0-r0 \
    && apk add --no-cache \
        --repository=http://dl-cdn.alpinelinux.org/alpine/edge/testing/ \
        librespot=0.8.0-r0 \
    && apk add --no-cache \
        --repository=http://dl-cdn.alpinelinux.org/alpine/edge/community/ \
        snapweb=0.9.2-r0 \
    && rm -rf /tmp/*

# Copy entrypoint
COPY run.sh /
RUN chmod a+x /run.sh

CMD ["/run.sh"]
