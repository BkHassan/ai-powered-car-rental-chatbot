FROM rasa/rasa-sdk:3.6.2

USER root
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/actions

USER 1001

EXPOSE 5055

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD curl -f http://localhost:5055/health || exit 1

CMD ["start", "--actions", "actions"]
