# ---- Build stage ----------------------------------------------------------
FROM hexpm/elixir:1.18.3-erlang-27.3-debian-bookworm-20250317-slim AS builder

ENV MIX_ENV=prod \
    LANG=C.UTF-8

WORKDIR /app

# Install hex + rebar.
RUN mix local.hex --force && mix local.rebar --force

# Fetch and compile deps first for better layer caching.
COPY mix.exs mix.exs
RUN mix deps.get --only prod
COPY config config
RUN mix deps.compile

# Compile app and assemble the release.
COPY lib lib
RUN mix compile
RUN mix release

# ---- Runtime stage --------------------------------------------------------
FROM debian:bookworm-slim AS runtime

# Runtime libs required by the BEAM + curl/wget for the compose healthcheck.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      curl \
      wget \
      libssl3 \
      libncurses6 \
      locales \
      ca-certificates && \
    sed -i '/en_US.UTF-8/s/^# //g' /etc/locale.gen && locale-gen && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

ENV LANG=en_US.UTF-8 \
    LANGUAGE=en_US:en \
    LC_ALL=en_US.UTF-8

WORKDIR /app

COPY --from=builder /app/_build/prod/rel/docs_loader ./

EXPOSE 8001

CMD ["bin/docs_loader", "start"]
