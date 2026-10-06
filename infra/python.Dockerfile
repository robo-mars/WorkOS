FROM python:3.11-slim
WORKDIR /workspace
COPY agent-python/requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir -r /tmp/requirements.lock
COPY agent-python /workspace/agent-python
COPY mcp /workspace/mcp
COPY policy-data /workspace/policy-data
COPY scripts /workspace/scripts
ENV PYTHONPATH=/workspace/agent-python PYTHONUNBUFFERED=1
RUN useradd --uid 10001 --create-home workplace
USER workplace
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]
