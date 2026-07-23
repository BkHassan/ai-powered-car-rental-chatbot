FROM rasa/rasa:3.6.20-full

USER root
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY . .

# Train model at build time for reproducible deployments
RUN rasa train --fixed-model-name model --quiet

USER 1001

EXPOSE 5005

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
  CMD curl -f http://localhost:5005/status || exit 1

CMD ["run", "--enable-api", "--cors", "*", "--port", "5005", "--endpoints", "endpoints.yml"]
