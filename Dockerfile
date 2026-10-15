FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 DBT_SEND_ANONYMOUS_USAGE_STATS=false
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN python -m agent_ops.cli init
ENTRYPOINT ["python", "-m", "agent_ops.cli"]
CMD ["--help"]
