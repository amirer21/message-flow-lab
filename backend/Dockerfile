FROM python:3.12-slim
WORKDIR /lab
COPY backend/requirements.txt /lab/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app /lab/app
COPY backend/tests /lab/tests
COPY workers /lab/workers
COPY scripts /lab/scripts
ENV PYTHONPATH=/lab
RUN useradd --create-home lab && mkdir /lab/data && chown lab:lab /lab/data
USER lab
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
