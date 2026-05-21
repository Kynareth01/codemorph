FROM python:3.11-slim

WORKDIR /app

# Install Node.js for JS/TS validation
RUN apt-get update && \
    apt-get install -y --no-install-recommends nodejs npm && \
    rm -rf /var/lib/apt/lists/*

# Install TypeScript globally for validation
RUN npm install -g typescript

COPY pyproject.toml README.md LICENSE ./
COPY codemorph/ ./codemorph/

RUN pip install --no-cache-dir .

# Default workspace
WORKDIR /workspace
VOLUME ["/workspace"]

ENTRYPOINT ["codemorph"]
CMD ["--help"]
