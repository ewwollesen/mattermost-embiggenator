FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml .
COPY embiggenator/ embiggenator/

RUN pip install --no-cache-dir .

ENTRYPOINT ["embiggenator"]
CMD ["--help"]
