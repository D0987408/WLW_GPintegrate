FROM python:3.12-slim
WORKDIR /app
COPY contracts /app/contracts
COPY components/person_a /app/components/person_a
RUN touch /app/components/__init__.py
ENV PYTHONPATH=/app
ENTRYPOINT ["python", "-m", "components.person_a.report_decompose"]
