FROM python:3.12-slim
LABEL org.opencontainers.image.description="replay-qa: a generic tool-calling A2A agent on agent-env's model endpoint"
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONUNBUFFERED=1
RUN pip install "agentenv-framework-protocol[agent]==0.1.349" "openai==2.54.0" "mcp==1.30.0" \
 && useradd --uid 10001 --create-home agent
COPY agent.py /app/agent.py
USER agent
EXPOSE 8000
CMD ["python", "/app/agent.py"]
