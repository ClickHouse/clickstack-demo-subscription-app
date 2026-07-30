# ---------------------------------------------------------------------------
# Build stage: compile the app and assemble a Mix release.
# ---------------------------------------------------------------------------
FROM hexpm/elixir:1.18.3-erlang-27.3-debian-bookworm-20250317-slim AS build

# Build tooling for native deps (e.g. bandit's thousand_island, exporter).
RUN apt-get update -y \
    && apt-get install -y --no-install-recommends build-essential git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV MIX_ENV=prod

RUN mix local.hex --force \
    && mix local.rebar --force

# Fetch and compile dependencies first (cache friendly).
COPY mix.exs ./
RUN mix deps.get --only prod
RUN mix deps.compile

# Application config.
COPY config config

# Application source and assets.
COPY lib lib
COPY priv priv

RUN mix compile

# Runtime config + release assembly.
RUN mix release

# ---------------------------------------------------------------------------
# Runtime stage: slim Debian with only runtime libs + curl for healthcheck.
# ---------------------------------------------------------------------------
FROM debian:bookworm-slim AS app

RUN apt-get update -y \
    && apt-get install -y --no-install-recommends \
        curl \
        libssl3 \
        libncurses6 \
        locales \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# UTF-8 locale (Erlang/Elixir expect a sane locale).
RUN sed -i '/en_US.UTF-8/s/^# //g' /etc/locale.gen && locale-gen
ENV LANG=en_US.UTF-8 \
    LANGUAGE=en_US:en \
    LC_ALL=en_US.UTF-8

WORKDIR /app

# Non-root user.
RUN useradd --create-home --shell /bin/bash appuser
COPY --from=build --chown=appuser:appuser /app/_build/prod/rel/subscription_app ./
USER appuser

ENV FLASK_HOST=0.0.0.0 \
    FLASK_PORT=8000

EXPOSE 8000

CMD ["/app/bin/subscription_app", "start"]
