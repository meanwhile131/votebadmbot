FROM python:3.13-slim AS builder
RUN pip install pipenv
WORKDIR /app
COPY Pipfile Pipfile.lock ./
RUN pipenv install --deploy --system

FROM python:3.13-slim
WORKDIR /app

# Copy installed packages from builder stage
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin


RUN useradd -m appuser
RUN mkdir data && chmod 700 data && chown -R appuser data
COPY src src
USER appuser

CMD ["python", "src/main.py"]