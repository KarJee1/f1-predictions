FROM python:3.12-slim
WORKDIR /srv
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml .
COPY f1pred ./f1pred
RUN pip install --no-cache-dir .
COPY seed ./seed
ENV F1_SEED=/srv/seed F1_CACHE=/tmp/f1cache
CMD ["f1pred", "run"]
