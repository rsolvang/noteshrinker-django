FROM python:3.13-slim

WORKDIR /var/app

# Dependencies
RUN apt-get update && \
    apt-get install -y \
        libblas-dev \
        liblapack-dev \
        liblapacke-dev \
        gfortran \
        gcc \
        g++ \
        poppler-utils && \
    pip install --upgrade pip setuptools wheel && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY requirements_docker.txt ./
RUN pip install --no-cache-dir -r requirements_docker.txt

RUN pip wheel numpy
RUN pip install numpy

RUN pip wheel scipy
RUN pip install scipy

# Create non-root user for running the application
RUN useradd -m -u 1000 -s /bin/bash appuser && \
    chown -R appuser:appuser /var/app

# Project files
COPY --chown=appuser:appuser . .

# Run the migrations upfront because the sqlite database is stored in a file.
RUN python manage.py migrate

# Create media directories
RUN mkdir -p noteshrinker/media/pdf noteshrinker/media/png && \
    chown -R appuser:appuser noteshrinker/media

# Switch to non-root user
USER appuser

# Server
EXPOSE 8000
ENTRYPOINT ["python"]
CMD ["manage.py", "runserver", "0.0.0.0:8000"]
